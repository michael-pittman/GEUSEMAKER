"""Spot instance selection and analysis."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from statistics import pstdev
from typing import Any

from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from geusemaker.infra import AWSClientFactory
from geusemaker.models.compute import InstanceSelection, SavingsComparison, SpotAnalysis
from geusemaker.models.deployment import DeploymentConfig
from geusemaker.services.base import BaseService
from geusemaker.services.pricing import PricingService


class SpotSelectionService(BaseService):
    """Analyze spot markets and choose the best placement."""

    def __init__(
        self,
        client_factory: AWSClientFactory,
        pricing_service: PricingService,
        region: str = "us-east-1",
        capacity_ttl_seconds: int = 120,
        ec2_client: Any | None = None,
    ):
        super().__init__(client_factory, region)
        self._pricing_service = pricing_service
        self._capacity_cache: dict[str, tuple[datetime, bool]] = {}
        self._capacity_ttl = timedelta(seconds=capacity_ttl_seconds)
        self._ec2_client = ec2_client

    def analyze_spot_prices(self, instance_type: str, region: str) -> SpotAnalysis:
        """Return spot analysis including recommended AZ and stability."""
        spot_prices = self._pricing_service.get_spot_prices(instance_type, region)
        on_demand = self._pricing_service.get_on_demand_price(instance_type, region)

        prices_by_az: dict[str, Decimal] = {}
        for price in spot_prices:
            if price.availability_zone not in prices_by_az:
                prices_by_az[price.availability_zone] = price.price_per_hour

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
        )

    def check_spot_capacity(self, instance_type: str, az: str | None, region: str) -> bool:
        """Use a dry-run spot request to validate capacity."""
        if not az:
            return False

        cache_key = f"{instance_type}:{az}"
        cached = self._capacity_cache.get(cache_key)
        if cached and datetime.now(UTC) - cached[0] < self._capacity_ttl:
            return cached[1]

        client = self._ec2(region)
        try:
            client.run_instances(
                InstanceType=instance_type,
                ImageId="ami-dry-run",
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

        fallback_reason: str | None = None
        selected_price = analysis.lowest_price
        selected_az = analysis.recommended_az
        selection_reason = "Lowest spot price with stability weighting"

        if analysis.lowest_price >= on_demand_price * Decimal("0.8"):
            fallback_reason = "Spot price >= 80% of on-demand"
        elif analysis.price_stability_score < 0.5:
            fallback_reason = "Spot price volatility too high"
        elif not self.check_spot_capacity(config.instance_type, analysis.recommended_az, config.region):
            fallback_reason = "Spot capacity unavailable"

        if fallback_reason:
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
