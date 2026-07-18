from decimal import Decimal

import pytest

from geusemaker.cli.output.verbosity import (
    VerbosityLevel,
    set_machine_output,
    set_verbosity,
)
from geusemaker.models import CostTracking, DeploymentConfig


@pytest.fixture(autouse=True)
def _reset_cli_output_state() -> None:
    """Isolate the process-global CLI output state between tests.

    ``--output json|yaml`` flips the module-level ``machine_output`` contextvar
    (via an eager Click callback) and never resets it, and ``--silent`` sets the
    verbosity contextvar; without this fixture a command test that sets either
    would leak into later tests and divert/suppress their console output,
    causing order-dependent failures.
    """
    set_verbosity(VerbosityLevel.NORMAL)
    set_machine_output(False)
    yield
    set_verbosity(VerbosityLevel.NORMAL)
    set_machine_output(False)


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
