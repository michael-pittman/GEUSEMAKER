from __future__ import annotations

from decimal import Decimal

from geusemaker.infra import AWSClientFactory
from geusemaker.models.compute import InstanceSelection, SavingsComparison
from geusemaker.models.cost import CostEstimate
from geusemaker.models.deployment import DeploymentConfig
from geusemaker.models.pricing import (
    ALBPricing,
    CloudFrontPricing,
    EFSPricing,
    OnDemandPrice,
)
from geusemaker.services.cost import CostEstimator


class StubPricingService:
    def __init__(self) -> None:
        self.on_demand = OnDemandPrice(
            instance_type="t3.medium",
            price_per_hour=Decimal("0.0416"),
            region="us-east-1",
            operating_system="Linux",  # type: ignore[arg-type]
        )

    def get_efs_pricing(self, region: str) -> EFSPricing:  # noqa: ARG002
        return EFSPricing(
            region="us-east-1",
            standard_gb_month=Decimal("0.30"),
            ia_gb_month=Decimal("0.025"),
            throughput_mibps=None,
        )

    def get_alb_pricing(self, region: str) -> ALBPricing:  # noqa: ARG002
        return ALBPricing(region="us-east-1", hourly_price=Decimal("0.0225"), lcu_price=Decimal("0.008"))

    def get_cloudfront_pricing(self, price_class: str = "PriceClass_100") -> CloudFrontPricing:  # noqa: ARG002
        return CloudFrontPricing(
            price_class="PriceClass_100",
            data_transfer_gb=Decimal("0.085"),
            requests_per_10k=Decimal("0.0075"),
        )


class StubSpotSelector:
    def __init__(self, selection: InstanceSelection) -> None:
        self.selection = selection

    def select_instance_type(self, config: DeploymentConfig) -> InstanceSelection:  # noqa: ARG002
        return self.selection


def _selection() -> InstanceSelection:
    comparison = SavingsComparison(
        on_demand_hourly=Decimal("0.0416"),
        selected_hourly=Decimal("0.02"),
        hourly_savings=Decimal("0.0216"),
        monthly_savings=Decimal("15.768"),
        savings_percentage=51.9,
    )
    return InstanceSelection(
        instance_type="t3.medium",
        availability_zone="us-east-1a",
        is_spot=True,
        price_per_hour=Decimal("0.02"),
        selection_reason="test",
        savings_vs_on_demand=comparison,
        fallback_reason=None,
        pricing_source="live",  # type: ignore[arg-type]
    )


def test_cost_estimate_includes_components() -> None:
    config = DeploymentConfig(
        stack_name="stack",
        tier="automation",
        region="us-east-1",
        instance_type="t3.medium",
        use_spot=True,
        enable_alb=True,
    )
    pricing = StubPricingService()
    selection = _selection()
    estimator = CostEstimator(
        client_factory=AWSClientFactory(),
        pricing_service=pricing,  # type: ignore[arg-type]
        region="us-east-1",
        spot_selector=StubSpotSelector(selection),  # type: ignore[arg-type]
    )

    estimate: CostEstimate = estimator.estimate_deployment_cost(
        config=config,
        storage_gb=50,
        data_transfer_gb=10,
        cloudfront_requests=0,
        alb_lcus=1,
        hours_per_month=100,
    )

    assert estimate.breakdown.compute.hourly_cost == Decimal("0.02")
    assert estimate.breakdown.storage.monthly_cost == Decimal("15.0")
    assert estimate.breakdown.load_balancer is not None
    assert estimate.comparison.savings_percentage > 0
