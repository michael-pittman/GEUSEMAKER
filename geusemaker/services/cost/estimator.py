"""Cost estimation service."""

from __future__ import annotations

from decimal import Decimal

from geusemaker.infra import AWSClientFactory
from geusemaker.models.compute import InstanceSelection
from geusemaker.models.cost import (
    ComponentCost,
    CostBreakdown,
    CostComparison,
    CostEstimate,
)
from geusemaker.models.deployment import DeploymentConfig
from geusemaker.services.compute import SpotSelectionService
from geusemaker.services.pricing import PricingService

DATA_TRANSFER_GB_PRICE = Decimal("0.09")
DEFAULT_HOURS_PER_MONTH = Decimal("730")


class CostEstimator:
    """Compute hourly and monthly cost estimates for deployments."""

    def __init__(
        self,
        client_factory: AWSClientFactory,
        pricing_service: PricingService,
        region: str = "us-east-1",
        spot_selector: SpotSelectionService | None = None,
    ):
        self._pricing_service = pricing_service
        self._spot_selector = spot_selector or SpotSelectionService(
            client_factory=client_factory,
            pricing_service=pricing_service,
            region=region,
        )
        self._region = region

    def estimate_deployment_cost(
        self,
        config: DeploymentConfig,
        storage_gb: float = 100.0,
        data_transfer_gb: float = 100.0,
        cloudfront_requests: int = 1_000_000,
        alb_lcus: float = 1.0,
        hours_per_month: int = 730,
        selection: InstanceSelection | None = None,
    ) -> CostEstimate:
        """Return a complete cost estimate for a deployment config."""
        selection = selection or self._spot_selector.select_instance_type(config)
        compute_cost = self.calculate_ec2_cost(
            instance_type=config.instance_type,
            is_spot=selection.is_spot,
            price_per_hour=selection.price_per_hour,
            hours=hours_per_month,
        )

        efs_pricing = self._pricing_service.get_efs_pricing(config.region)
        storage_cost = self.calculate_efs_cost(storage_gb, efs_pricing, hours_per_month)

        alb_cost = None
        if config.enable_alb or config.tier in ("automation", "gpu"):
            alb_pricing = self._pricing_service.get_alb_pricing(config.region)
            alb_cost = self.calculate_alb_cost(alb_pricing, alb_lcus, hours_per_month)

        cf_cost = None
        if config.enable_cdn or config.tier == "gpu":
            cf_pricing = self._pricing_service.get_cloudfront_pricing()
            cf_cost = self.calculate_cloudfront_cost(
                data_transfer_gb,
                cloudfront_requests,
                cf_pricing,
                hours_per_month,
            )

        data_transfer_cost = self.calculate_data_transfer_cost(
            data_transfer_gb=data_transfer_gb,
            hours=hours_per_month,
        )

        total_hourly = (
            compute_cost.hourly_cost
            + storage_cost.hourly_cost
            + data_transfer_cost.hourly_cost
            + (alb_cost.hourly_cost if alb_cost else Decimal("0"))
            + (cf_cost.hourly_cost if cf_cost else Decimal("0"))
        )
        total_monthly = (
            compute_cost.monthly_cost
            + storage_cost.monthly_cost
            + data_transfer_cost.monthly_cost
            + (alb_cost.monthly_cost if alb_cost else Decimal("0"))
            + (cf_cost.monthly_cost if cf_cost else Decimal("0"))
        )

        comparison = CostComparison(
            spot_hourly=selection.price_per_hour
            if selection.is_spot
            else selection.savings_vs_on_demand.selected_hourly,
            on_demand_hourly=selection.savings_vs_on_demand.on_demand_hourly,
            spot_monthly=(selection.price_per_hour * Decimal(hours_per_month)).quantize(Decimal("0.0001"))
            if selection.is_spot
            else selection.savings_vs_on_demand.on_demand_hourly * Decimal(hours_per_month),
            on_demand_monthly=selection.savings_vs_on_demand.on_demand_hourly * Decimal(hours_per_month),
            hourly_savings=selection.savings_vs_on_demand.hourly_savings,
            monthly_savings=selection.savings_vs_on_demand.monthly_savings,
            savings_percentage=selection.savings_vs_on_demand.savings_percentage,
        )

        breakdown = CostBreakdown(
            compute=compute_cost,
            storage=storage_cost,
            networking=data_transfer_cost,
            data_transfer=data_transfer_cost,
            load_balancer=alb_cost,
            cdn=cf_cost,
            total=ComponentCost(
                resource_type="total",
                description="Total estimated cost",
                hourly_cost=total_hourly,
                monthly_cost=total_monthly,
                unit_price=total_hourly,
                unit="hour",
                quantity=1,
            ),
        )

        return CostEstimate(
            deployment_name=config.stack_name,
            tier=config.tier,
            hourly_cost=total_hourly,
            monthly_cost=total_monthly,
            breakdown=breakdown,
            comparison=comparison,
            pricing_source=selection.pricing_source,  # type: ignore[arg-type]
        )

    def calculate_ec2_cost(
        self,
        instance_type: str,
        is_spot: bool,
        price_per_hour: Decimal,
        hours: int = 730,
    ) -> ComponentCost:
        monthly_cost = price_per_hour * Decimal(hours)
        return ComponentCost(
            resource_type="compute",
            description=f"{'Spot' if is_spot else 'On-demand'} {instance_type}",
            hourly_cost=price_per_hour,
            monthly_cost=monthly_cost,
            unit_price=price_per_hour,
            unit="per hour",
            quantity=1,
        )

    def calculate_efs_cost(
        self,
        storage_gb: float,
        pricing,
        hours_per_month: int,
    ) -> ComponentCost:
        monthly_cost = Decimal(str(storage_gb)) * pricing.standard_gb_month
        hourly_cost = monthly_cost / Decimal(hours_per_month)
        return ComponentCost(
            resource_type="storage",
            description="EFS storage (standard)",
            hourly_cost=hourly_cost,
            monthly_cost=monthly_cost,
            unit_price=pricing.standard_gb_month,
            unit="per GB-month",
            quantity=float(storage_gb),
        )

    def calculate_alb_cost(
        self,
        pricing,
        expected_lcus: float,
        hours_per_month: int,
    ) -> ComponentCost:
        hourly_cost = pricing.hourly_price + pricing.lcu_price * Decimal(str(expected_lcus))
        monthly_cost = hourly_cost * Decimal(hours_per_month)
        return ComponentCost(
            resource_type="load_balancer",
            description="Application Load Balancer",
            hourly_cost=hourly_cost,
            monthly_cost=monthly_cost,
            unit_price=pricing.lcu_price,
            unit="per LCU-hour",
            quantity=expected_lcus,
        )

    def calculate_cloudfront_cost(
        self,
        data_transfer_gb: float,
        requests: int,
        pricing,
        hours_per_month: int,
    ) -> ComponentCost:
        monthly_transfer = Decimal(str(data_transfer_gb)) * pricing.data_transfer_gb
        monthly_requests = (Decimal(requests) / Decimal(10_000)) * pricing.requests_per_10k
        monthly_cost = monthly_transfer + monthly_requests
        hourly_cost = monthly_cost / Decimal(hours_per_month)
        return ComponentCost(
            resource_type="cdn",
            description="CloudFront data + requests",
            hourly_cost=hourly_cost,
            monthly_cost=monthly_cost,
            unit_price=pricing.data_transfer_gb,
            unit="per GB",
            quantity=data_transfer_gb,
        )

    def calculate_data_transfer_cost(
        self,
        data_transfer_gb: float,
        hours: int,
    ) -> ComponentCost:
        monthly_cost = Decimal(str(data_transfer_gb)) * DATA_TRANSFER_GB_PRICE
        hourly_cost = monthly_cost / Decimal(hours)
        return ComponentCost(
            resource_type="data_transfer",
            description="Data transfer out",
            hourly_cost=hourly_cost,
            monthly_cost=monthly_cost,
            unit_price=DATA_TRANSFER_GB_PRICE,
            unit="per GB",
            quantity=data_transfer_gb,
        )


__all__ = ["CostEstimator"]
