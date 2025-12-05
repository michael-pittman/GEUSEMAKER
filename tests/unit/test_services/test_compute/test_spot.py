from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from geusemaker.models.deployment import DeploymentConfig
from geusemaker.models.pricing import OnDemandPrice, SpotPrice
from geusemaker.services.compute import SpotSelectionService


class StubPricingService:
    def __init__(self, spot_price: Decimal, on_demand: Decimal) -> None:
        self._spot_price = spot_price
        self._on_demand = on_demand

    def get_spot_prices(self, instance_type: str, region: str) -> list[SpotPrice]:  # noqa: ARG002
        return [
            SpotPrice(
                instance_type=instance_type,
                availability_zone=f"{region}a",
                price_per_hour=self._spot_price,
                timestamp=datetime.now(UTC),
                region=region,
            ),
        ]

    def get_on_demand_price(self, instance_type: str, region: str, operating_system: str = "Linux") -> OnDemandPrice:  # noqa: ARG002
        return OnDemandPrice(
            instance_type=instance_type,
            price_per_hour=self._on_demand,
            region=region,
            operating_system=operating_system,  # type: ignore[arg-type]
        )


class FakeEC2:
    def __init__(self, code: str = "DryRunOperation") -> None:
        self.code = code

    def describe_spot_price_history(self, **_: object) -> dict:
        return {"SpotPriceHistory": []}

    def run_instances(self, **_: object) -> dict:
        if self.code:
            raise ClientError({"Error": {"Code": self.code}}, "RunInstances")
        return {}


class FakeFactory:
    def __init__(self, ec2_client: FakeEC2) -> None:
        self._ec2 = ec2_client

    def get_client(self, service_name: str, region: str = "us-east-1") -> object:  # noqa: ARG002
        if service_name == "ec2":
            return self._ec2
        raise KeyError(service_name)


def _config(use_spot: bool = True) -> DeploymentConfig:
    return DeploymentConfig(
        stack_name="test",
        tier="dev",
        region="us-east-1",
        instance_type="t3.medium",
        use_spot=use_spot,
    )


def test_spot_selected_when_cheapest_and_capacity_available() -> None:
    pricing = StubPricingService(spot_price=Decimal("0.012"), on_demand=Decimal("0.0416"))
    ec2 = FakeEC2(code="DryRunOperation")
    factory = FakeFactory(ec2_client=ec2)
    service = SpotSelectionService(factory, pricing_service=pricing, region="us-east-1", ec2_client=ec2)

    selection = service.select_instance_type(_config())
    assert selection.is_spot is True
    assert selection.availability_zone == "us-east-1a"
    assert selection.savings_vs_on_demand.hourly_savings > 0


def test_fallback_to_on_demand_when_spot_expensive() -> None:
    pricing = StubPricingService(spot_price=Decimal("0.04"), on_demand=Decimal("0.0416"))
    ec2 = FakeEC2(code="DryRunOperation")
    factory = FakeFactory(ec2_client=ec2)
    service = SpotSelectionService(factory, pricing_service=pricing, region="us-east-1", ec2_client=ec2)

    selection = service.select_instance_type(_config())
    assert selection.is_spot is False
    assert selection.fallback_reason is not None


def test_fallback_when_capacity_unavailable() -> None:
    pricing = StubPricingService(spot_price=Decimal("0.012"), on_demand=Decimal("0.0416"))
    ec2 = FakeEC2(code="InsufficientInstanceCapacity")
    factory = FakeFactory(ec2_client=ec2)
    service = SpotSelectionService(factory, pricing_service=pricing, region="us-east-1", ec2_client=ec2)

    selection = service.select_instance_type(_config())
    assert selection.is_spot is False
    assert selection.fallback_reason == "Spot capacity unavailable"
