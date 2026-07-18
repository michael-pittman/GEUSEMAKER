"""Unit tests for AZ-alignment logic in ``stages.networking.resolve_networking``.

The stub VPC service (see conftest) provides public subnets in ``us-east-1a``
(``subnet-public-1``) and ``us-east-1b`` (``subnet-public-2``) and a private
subnet in ``us-east-1c`` (``subnet-private-1``). These tests assert that a spot
selection pins compute + storage to the selected AZ, and fails fast when a
pinned subnet contradicts it.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from geusemaker.models import DeploymentConfig
from geusemaker.models.compute import InstanceSelection, SavingsComparison
from geusemaker.orchestration.errors import OrchestrationError
from geusemaker.orchestration.stages import resolve_networking
from tests.unit.test_orchestration.conftest import StubVPCService


def _selection(az: str | None, *, is_spot: bool = True) -> InstanceSelection:
    return InstanceSelection(
        instance_type="t3.medium",
        availability_zone=az,
        is_spot=is_spot,
        price_per_hour=Decimal("0.012"),
        selection_reason="test",
        savings_vs_on_demand=SavingsComparison(
            on_demand_hourly=Decimal("0.0416"),
            selected_hourly=Decimal("0.012"),
            hourly_savings=Decimal("0.0296"),
            monthly_savings=Decimal("21.6"),
            savings_percentage=71.0,
        ),
    )


def _config(**overrides: object) -> DeploymentConfig:
    base: dict[str, object] = {
        "stack_name": "test",
        "tier": "dev",
        "region": "us-east-1",
        "instance_type": "t3.medium",
    }
    base.update(overrides)
    return DeploymentConfig(**base)  # type: ignore[arg-type]


def test_spot_az_pins_compute_and_storage_subnets() -> None:
    result = resolve_networking(StubVPCService(), _config(), _selection("us-east-1b"))

    assert result["chosen_public_subnet_id"] == "subnet-public-2"
    assert result["chosen_public_subnet_az"] == "us-east-1b"
    # Storage defaults to the compute subnet -> same AZ as the spot instance.
    assert result["chosen_storage_subnet_id"] == "subnet-public-2"


def test_pinned_subnet_in_wrong_az_fails_fast() -> None:
    # subnet-public-1 is in us-east-1a, but the spot price was selected in us-east-1b.
    config = _config(subnet_id="subnet-public-1")

    with pytest.raises(OrchestrationError, match="selected spot price"):
        resolve_networking(StubVPCService(), config, _selection("us-east-1b"))


def test_pinned_subnet_matching_spot_az_is_accepted() -> None:
    config = _config(subnet_id="subnet-public-1")

    result = resolve_networking(StubVPCService(), config, _selection("us-east-1a"))

    assert result["chosen_public_subnet_id"] == "subnet-public-1"
    assert result["chosen_public_subnet_az"] == "us-east-1a"


def test_no_public_subnet_in_spot_az_fails_fast() -> None:
    with pytest.raises(OrchestrationError, match="No public subnet in us-east-1z"):
        resolve_networking(StubVPCService(), _config(), _selection("us-east-1z"))


def test_pinned_storage_subnet_in_wrong_az_fails_fast() -> None:
    # subnet-private-1 is in us-east-1c; the spot instance is in us-east-1a.
    config = _config(storage_subnet_id="subnet-private-1")

    with pytest.raises(OrchestrationError, match="must be in the selected spot AZ us-east-1a"):
        resolve_networking(StubVPCService(), config, _selection("us-east-1a"))


def test_on_demand_selection_imposes_no_az_constraint() -> None:
    # is_spot=False with a mismatched pinned subnet must NOT raise (no priced AZ).
    config = _config(subnet_id="subnet-public-1")

    result = resolve_networking(StubVPCService(), config, _selection("us-east-1b", is_spot=False))

    assert result["chosen_public_subnet_id"] == "subnet-public-1"
