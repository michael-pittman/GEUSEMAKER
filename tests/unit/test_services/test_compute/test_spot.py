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
    def __init__(self, code: str = "DryRunOperation", placement_scores: dict[str, float] | None = None) -> None:
        self.code = code
        self.placement_scores = placement_scores or {}

    def describe_spot_price_history(self, **_: object) -> dict:
        return {"SpotPriceHistory": []}

    def run_instances(self, **_: object) -> dict:
        if self.code:
            raise ClientError({"Error": {"Code": self.code}}, "RunInstances")
        return {}

    def get_spot_placement_scores(
        self,
        InstanceTypes: list[str],  # noqa: ARG002, N803
        TargetCapacity: int,  # noqa: ARG002, N803
        SingleAvailabilityZone: bool,  # noqa: ARG002, N803
    ) -> dict:
        """Mock spot placement scores API."""
        scores = [
            {"AvailabilityZone": az, "Score": score}
            for az, score in self.placement_scores.items()
        ]
        return {"SpotPlacementScores": scores}


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
    assert selection.fallback_reason is not None
    assert "Spot capacity unavailable" in selection.fallback_reason


def test_get_spot_placement_scores_returns_scores_by_az() -> None:
    """Test that get_spot_placement_scores returns placement scores for AZs."""
    pricing = StubPricingService(spot_price=Decimal("0.012"), on_demand=Decimal("0.0416"))
    ec2 = FakeEC2(
        code="DryRunOperation",
        placement_scores={"us-east-1a": 8.5, "us-east-1b": 6.2, "us-east-1c": 9.1},
    )
    factory = FakeFactory(ec2_client=ec2)
    service = SpotSelectionService(factory, pricing_service=pricing, region="us-east-1", ec2_client=ec2)

    scores = service.get_spot_placement_scores("t3.medium", "us-east-1")

    assert len(scores) == 3
    assert scores["us-east-1a"] == 8.5
    assert scores["us-east-1b"] == 6.2
    assert scores["us-east-1c"] == 9.1


def test_placement_scores_included_in_analysis() -> None:
    """Test that spot analysis includes placement scores."""
    pricing = StubPricingService(spot_price=Decimal("0.012"), on_demand=Decimal("0.0416"))
    ec2 = FakeEC2(
        code="DryRunOperation",
        placement_scores={"us-east-1a": 7.5},
    )
    factory = FakeFactory(ec2_client=ec2)
    service = SpotSelectionService(factory, pricing_service=pricing, region="us-east-1", ec2_client=ec2)

    analysis = service.analyze_spot_prices("t3.medium", "us-east-1")

    assert "us-east-1a" in analysis.placement_scores_by_az
    assert analysis.placement_scores_by_az["us-east-1a"] == 7.5


def test_multi_az_checking_uses_secondary_when_primary_unavailable() -> None:
    """Test that service tries multiple AZs before falling back to on-demand."""

    class MultiAZPricingService:
        def get_spot_prices(self, instance_type: str, region: str) -> list[SpotPrice]:  # noqa: ARG002
            return [
                SpotPrice(
                    instance_type=instance_type,
                    availability_zone=f"{region}a",
                    price_per_hour=Decimal("0.010"),  # Cheapest
                    timestamp=datetime.now(UTC),
                    region=region,
                ),
                SpotPrice(
                    instance_type=instance_type,
                    availability_zone=f"{region}b",
                    price_per_hour=Decimal("0.012"),  # Second cheapest
                    timestamp=datetime.now(UTC),
                    region=region,
                ),
            ]

        def get_on_demand_price(
            self, instance_type: str, region: str, operating_system: str = "Linux"  # noqa: ARG002
        ) -> OnDemandPrice:
            return OnDemandPrice(
                instance_type=instance_type,
                price_per_hour=Decimal("0.0416"),
                region=region,
                operating_system=operating_system,  # type: ignore[arg-type]
            )

    class MultiAZEC2(FakeEC2):
        def __init__(self) -> None:
            super().__init__(code="DryRunOperation", placement_scores={"us-east-1a": 3.0, "us-east-1b": 8.0})
            self.az_calls: list[str] = []

        def run_instances(self, **kwargs: object) -> dict:
            # Track which AZ is being checked
            placement = kwargs.get("Placement", {})
            az = placement.get("AvailabilityZone") if isinstance(placement, dict) else None
            if az:
                self.az_calls.append(str(az))

            # First AZ (us-east-1a) fails, second AZ (us-east-1b) succeeds
            if az == "us-east-1a":
                raise ClientError({"Error": {"Code": "InsufficientInstanceCapacity"}}, "RunInstances")

            # us-east-1b succeeds
            return super().run_instances(**kwargs)

    pricing = MultiAZPricingService()
    ec2 = MultiAZEC2()
    factory = FakeFactory(ec2_client=ec2)
    service = SpotSelectionService(factory, pricing_service=pricing, region="us-east-1", ec2_client=ec2)

    selection = service.select_instance_type(_config())

    # Should select us-east-1b (secondary AZ with higher placement score and capacity)
    assert selection.is_spot is True
    assert selection.availability_zone == "us-east-1b"
    assert selection.price_per_hour == Decimal("0.012")

    # Verify that both AZs were checked
    assert "us-east-1a" in ec2.az_calls or "us-east-1b" in ec2.az_calls
