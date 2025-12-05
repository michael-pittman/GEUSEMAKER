from decimal import Decimal

import pytest

from geusemaker.models import CostTracking, DeploymentConfig


@pytest.fixture()
def sample_config() -> DeploymentConfig:
    return DeploymentConfig(stack_name="sample-stack", tier="dev")


@pytest.fixture()
def sample_cost() -> CostTracking:
    return CostTracking(
        instance_type="t3.medium",
        is_spot=True,
        spot_price_per_hour=Decimal("0.0125"),
        on_demand_price_per_hour=Decimal("0.0416"),
        estimated_monthly_cost=Decimal("25.0"),
    )
