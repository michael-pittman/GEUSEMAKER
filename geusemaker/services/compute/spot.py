"""Spot instance selection and analysis."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from statistics import pstdev
from typing import TYPE_CHECKING, Any

from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from geusemaker.cli import console
from geusemaker.cli.branding import EMOJI
from geusemaker.infra import AWSClientFactory
from geusemaker.models.compute import InstanceSelection, SavingsComparison, SpotAnalysis
from geusemaker.models.deployment import DeploymentConfig
from geusemaker.services.base import BaseService
from geusemaker.services.pricing import PricingService

if TYPE_CHECKING:
    from geusemaker.services.ec2 import EC2Service


class SpotSelectionService(BaseService):
    """Analyze spot markets and choose the best placement."""

    def __init__(
        self,
        client_factory: AWSClientFactory,
        pricing_service: PricingService,
        region: str = "us-east-1",
        capacity_ttl_seconds: int = 120,
        ec2_client: Any | None = None,
        ec2_service: EC2Service | None = None,
    ):
        super().__init__(client_factory, region)
        self._pricing_service = pricing_service
        self._capacity_cache: dict[str, tuple[datetime, bool]] = {}
        self._capacity_ttl = timedelta(seconds=capacity_ttl_seconds)
        self._ec2_client = ec2_client
        self._ec2_service = ec2_service
        self._ami_cache: dict[tuple[str, str, str], str] = {}  # Cache (os_type, ami_type, region) -> ami_id

    def analyze_spot_prices(self, instance_type: str, region: str) -> SpotAnalysis:
        """Return spot analysis including recommended AZ and stability."""
        spot_prices = self._pricing_service.get_spot_prices(instance_type, region)
        on_demand = self._pricing_service.get_on_demand_price(instance_type, region)

        prices_by_az: dict[str, Decimal] = {}
        for price in spot_prices:
            if price.availability_zone not in prices_by_az:
                prices_by_az[price.availability_zone] = price.price_per_hour

        # Get spot placement scores for availability prediction
        placement_scores = self.get_spot_placement_scores(instance_type, region)

        lowest_az = None
        lowest_price = on_demand.price_per_hour
        for az, price in prices_by_az.items():
            if price < lowest_price:
                lowest_price = price
                lowest_az = az

        stability_scores = self._stability_scores(instance_type, region, prices_by_az)
        stability = max(stability_scores.values()) if stability_scores else 0.0
        savings_pct = float(
            max(
                Decimal(0),
                (on_demand.price_per_hour - lowest_price) / on_demand.price_per_hour,
            )
            * 100,
        )

        return SpotAnalysis(
            instance_type=instance_type,
            region=region,
            prices_by_az=prices_by_az,
            recommended_az=lowest_az,
            lowest_price=lowest_price,
            price_stability_score=stability,
            on_demand_price=on_demand.price_per_hour,
            savings_percentage=savings_pct,
            placement_scores_by_az=placement_scores,
        )

    def _get_ami_for_dryrun(self, region: str, os_type: str = "amazon-linux-2023", ami_type: str = "base") -> str:
        """Get a valid AMI ID for dry-run checks (cached)."""
        cache_key = (os_type, ami_type, region)
        if cache_key in self._ami_cache:
            return self._ami_cache[cache_key]

        # Use EC2Service if available, otherwise fallback to placeholder
        if self._ec2_service:
            try:
                ami_id = self._ec2_service.select_ami(
                    os_type=os_type,
                    ami_type=ami_type,
                    architecture="x86_64",
                )
                self._ami_cache[cache_key] = ami_id
                return ami_id
            except Exception as exc:  # noqa: BLE001
                # Log and fallback to placeholder if AMI selection fails
                import logging

                logging.getLogger(__name__).debug(f"AMI selection failed for dry-run check: {exc}. Using fallback AMI.")

        # Fallback: use a placeholder AMI ID (less accurate but won't fail)
        return "ami-0c55b159cbfafe1f0"  # Generic Amazon Linux 2 AMI (always exists but may be deprecated)

    def check_spot_capacity(self, instance_type: str, az: str | None, region: str) -> bool:
        """Use a dry-run spot request to validate capacity with real AMI ID."""
        if not az:
            return False

        cache_key = f"{instance_type}:{az}"
        cached = self._capacity_cache.get(cache_key)
        if cached and datetime.now(UTC) - cached[0] < self._capacity_ttl:
            return cached[1]

        # Get a valid AMI ID for more accurate dry-run validation
        ami_id = self._get_ami_for_dryrun(region)

        client = self._ec2(region)
        try:
            client.run_instances(
                InstanceType=instance_type,
                ImageId=ami_id,
                DryRun=True,
                InstanceMarketOptions={"MarketType": "spot"},
                Placement={"AvailabilityZone": az},
                MinCount=1,
                MaxCount=1,
            )
        except ClientError as exc:  # type: ignore[catching-any]
            if exc.response.get("Error", {}).get("Code") == "DryRunOperation":
                result = True
            elif "InsufficientInstanceCapacity" in str(exc):
                result = False
            else:
                result = False
        else:
            result = True

        self._capacity_cache[cache_key] = (datetime.now(UTC), result)
        return result

    def get_spot_placement_scores(
        self,
        instance_type: str,
        region: str,
        target_capacity: int = 1,
    ) -> dict[str, float]:
        """Get spot placement scores for all AZs to predict availability.

        Uses the AWS Spot Placement Scores API to predict spot instance availability.
        Scores range from 1-10, with higher scores indicating better availability.

        Args:
            instance_type: EC2 instance type (e.g., "g4dn.xlarge")
            region: AWS region
            target_capacity: Number of instances needed (default: 1)

        Returns:
            Dictionary mapping AZ names to placement scores (1-10 scale)
            Empty dict if API call fails

        """
        client = self._ec2(region)
        try:
            response = client.get_spot_placement_scores(
                InstanceTypes=[instance_type],
                TargetCapacity=target_capacity,
                SingleAvailabilityZone=True,
            )

            scores_by_az: dict[str, float] = {}
            for score_data in response.get("SpotPlacementScores", []):
                # API returns either AvailabilityZoneId or AvailabilityZone
                az = score_data.get("AvailabilityZone") or score_data.get("AvailabilityZoneId")
                score = float(score_data.get("Score", 0.0))

                if az and score > 0:
                    scores_by_az[az] = score

            return scores_by_az

        except ClientError as exc:
            # Gracefully handle API failures - don't block deployment
            console.print(
                f"{EMOJI['warning']} Could not fetch spot placement scores: {exc}",
                verbosity="debug",
            )
            return {}

    def select_instance_type(self, config: DeploymentConfig) -> InstanceSelection:
        """Select spot or on-demand placement honoring user preference."""
        analysis = self.analyze_spot_prices(config.instance_type, config.region)
        on_demand_price = analysis.on_demand_price

        if not config.use_spot:
            return self._selection(
                instance_type=config.instance_type,
                az=None,
                price=on_demand_price,
                on_demand_price=on_demand_price,
                is_spot=False,
                selection_reason="User requested on-demand",
                fallback_reason=None,
                source="live",
            )

        # Check if spot prices are too high overall
        if analysis.lowest_price >= on_demand_price * Decimal("0.8"):
            fallback_reason = "Spot price >= 80% of on-demand"
            console.print(
                f"{EMOJI['info']} Spot price too high: ${analysis.lowest_price:.4f}/hr "
                f"(${on_demand_price:.4f}/hr on-demand = {float(analysis.lowest_price / on_demand_price * 100):.1f}% of on-demand cost). "
                "Falling back to on-demand.",
                verbosity="info",
            )
            return self._selection(
                instance_type=config.instance_type,
                az=None,
                price=on_demand_price,
                on_demand_price=on_demand_price,
                is_spot=False,
                selection_reason="Falling back to on-demand",
                fallback_reason=fallback_reason,
                source="estimated",
            )

        # Check if spot prices are too volatile
        if analysis.price_stability_score < 0.5:
            fallback_reason = "Spot price volatility too high"
            console.print(
                f"{EMOJI['info']} Spot price unstable: stability score {analysis.price_stability_score:.2f} < 0.5 threshold. "
                f"Falling back to on-demand for reliability.",
                verbosity="info",
            )
            return self._selection(
                instance_type=config.instance_type,
                az=None,
                price=on_demand_price,
                on_demand_price=on_demand_price,
                is_spot=False,
                selection_reason="Falling back to on-demand",
                fallback_reason=fallback_reason,
                source="estimated",
            )

        # Try all AZs with good prices, sorted by price and placement score
        # Filter to AZs with reasonable prices (< 80% of on-demand)
        viable_azs = [
            (az, price)
            for az, price in analysis.prices_by_az.items()
            if price < on_demand_price * Decimal("0.8")
        ]

        if not viable_azs:
            # No viable AZs found - fall back to on-demand
            console.print(
                f"{EMOJI['info']} No spot AZs with good prices found. Falling back to on-demand.",
                verbosity="info",
            )
            return self._selection(
                instance_type=config.instance_type,
                az=None,
                price=on_demand_price,
                on_demand_price=on_demand_price,
                is_spot=False,
                selection_reason="Falling back to on-demand",
                fallback_reason="No viable spot AZs",
                source="estimated",
            )

        # Sort AZs by: 1) placement score (if available), 2) price
        def az_score(az_price_tuple: tuple[str, Decimal]) -> tuple[float, Decimal]:
            az, price = az_price_tuple
            # Higher placement score is better (negate for sorting)
            placement_score = analysis.placement_scores_by_az.get(az, 5.0)  # Default to mid-range
            return (-placement_score, price)  # Sort by placement score desc, then price asc

        viable_azs.sort(key=az_score)

        # Try each viable AZ in order until we find one with capacity
        selected_az = None
        selected_price = None
        unavailable_azs: list[str] = []

        for az, price in viable_azs:
            placement_score = analysis.placement_scores_by_az.get(az, 0.0)
            console.print(
                f"{EMOJI['info']} Checking spot capacity for {config.instance_type} in {az}: "
                f"${price:.4f}/hr (placement score: {placement_score:.1f})",
                verbosity="debug",
            )

            if self.check_spot_capacity(config.instance_type, az, config.region):
                # Found an AZ with capacity!
                selected_az = az
                selected_price = price
                break

            # This AZ has no capacity, try next
            unavailable_azs.append(az)
            console.print(
                f"{EMOJI['warning']} Spot capacity unavailable for {config.instance_type} in {az}. "
                "Trying next AZ...",
                verbosity="debug",
            )

        # If no AZ has capacity, fall back to on-demand
        if selected_az is None or selected_price is None:
            fallback_reason = f"Spot capacity unavailable in all {len(viable_azs)} viable AZs: {', '.join(unavailable_azs)}"
            console.print(
                f"{EMOJI['info']} {fallback_reason}. Falling back to on-demand.",
                verbosity="info",
            )
            return self._selection(
                instance_type=config.instance_type,
                az=None,
                price=on_demand_price,
                on_demand_price=on_demand_price,
                is_spot=False,
                selection_reason="Falling back to on-demand",
                fallback_reason=fallback_reason,
                source="estimated",
            )

        # Successfully selected spot instance - log the decision
        savings_pct = float((on_demand_price - selected_price) / on_demand_price * 100)
        placement_score = analysis.placement_scores_by_az.get(selected_az, 0.0)
        selection_reason = f"Best available spot price with capacity (placement score: {placement_score:.1f})"

        console.print(
            f"{EMOJI['check']} Spot instance selected in {selected_az}: "
            f"${selected_price:.4f}/hr (vs ${on_demand_price:.4f}/hr on-demand = {savings_pct:.1f}% savings). "
            f"Stability score: {analysis.price_stability_score:.2f}, placement score: {placement_score:.1f}",
            verbosity="info",
        )

        if unavailable_azs:
            console.print(
                f"{EMOJI['info']} Checked {len(unavailable_azs)} other AZ(s) with no capacity: {', '.join(unavailable_azs)}",
                verbosity="debug",
            )

        return self._selection(
            instance_type=config.instance_type,
            az=selected_az,
            price=selected_price,
            on_demand_price=on_demand_price,
            is_spot=True,
            selection_reason=selection_reason,
            fallback_reason=None,
            source="live",
        )

    def _selection(
        self,
        instance_type: str,
        az: str | None,
        price: Decimal,
        on_demand_price: Decimal,
        is_spot: bool,
        selection_reason: str,
        fallback_reason: str | None,
        source: str,
    ) -> InstanceSelection:
        hourly_savings = (on_demand_price - price) if on_demand_price > price else Decimal("0.0")
        monthly_savings = hourly_savings * Decimal("730")
        comparison = SavingsComparison(
            on_demand_hourly=on_demand_price,
            selected_hourly=price,
            hourly_savings=hourly_savings,
            monthly_savings=monthly_savings,
            savings_percentage=float(
                (hourly_savings / on_demand_price * Decimal("100")) if on_demand_price else Decimal("0"),
            ),
        )
        return InstanceSelection(
            instance_type=instance_type,
            availability_zone=az,
            is_spot=is_spot,
            price_per_hour=price,
            selection_reason=selection_reason,
            fallback_reason=fallback_reason,
            savings_vs_on_demand=comparison,
            pricing_source=source,  # type: ignore[arg-type]
        )

    def _stability_scores(
        self,
        instance_type: str,
        region: str,
        prices_by_az: dict[str, Decimal],
    ) -> dict[str, float]:
        history = self._fetch_history(instance_type, region)
        scores: dict[str, float] = {}
        for az, samples in history.items():
            if len(samples) < 2:
                scores[az] = 1.0
                continue
            mean_price = sum(samples) / Decimal(len(samples))
            if mean_price == 0:
                scores[az] = 0.0
                continue
            variance = Decimal(pstdev(samples)) / mean_price
            scores[az] = max(0.0, float(1 - variance))
        # Fill missing AZs from current prices
        for az in prices_by_az:
            scores.setdefault(az, 1.0)
        return scores

    def _fetch_history(self, instance_type: str, region: str) -> dict[str, list[Decimal]]:
        """Fetch 24h history for stability scoring, with a safe fallback."""
        client = self._ec2(region)
        start_time = datetime.now(UTC) - timedelta(hours=24)
        try:
            resp = client.describe_spot_price_history(
                InstanceTypes=[instance_type],
                ProductDescriptions=["Linux/UNIX"],
                StartTime=start_time,
                MaxResults=200,
            )
            history = resp.get("SpotPriceHistory", [])
        except ClientError:
            history = []

        grouped: dict[str, list[Decimal]] = {}
        for entry in history:
            az = entry.get("AvailabilityZone")
            price = Decimal(str(entry.get("SpotPrice", "0")))
            grouped.setdefault(az, []).append(price)
        return grouped

    def _ec2(self, region: str) -> Any:
        if self._ec2_client:
            return self._ec2_client
        return self._client_factory.get_client("ec2", region=region)


__all__ = ["SpotSelectionService"]
