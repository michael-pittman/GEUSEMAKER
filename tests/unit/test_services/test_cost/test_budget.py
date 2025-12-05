from __future__ import annotations

from decimal import Decimal

from geusemaker.models.cost import (
    ComponentCost,
    CostBreakdown,
    CostComparison,
    CostEstimate,
)
from geusemaker.services.cost import BudgetService


def _estimate(monthly: Decimal) -> CostEstimate:
    compute = ComponentCost(
        resource_type="compute",
        description="test",
        hourly_cost=Decimal("0.10"),
        monthly_cost=monthly,
        unit_price=Decimal("0.10"),
        unit="hour",
        quantity=1,
    )
    breakdown = CostBreakdown(
        compute=compute,
        storage=compute,
        networking=compute,
        data_transfer=compute,
        load_balancer=None,
        cdn=None,
        total=compute,
    )
    comparison = CostComparison(
        spot_hourly=Decimal("0.10"),
        on_demand_hourly=Decimal("0.12"),
        spot_monthly=monthly,
        on_demand_monthly=monthly + Decimal("10"),
        hourly_savings=Decimal("0.02"),
        monthly_savings=Decimal("10"),
        savings_percentage=16.6,
    )
    return CostEstimate(
        deployment_name="stack",
        tier="dev",
        hourly_cost=Decimal("0.10"),
        monthly_cost=monthly,
        breakdown=breakdown,
        comparison=comparison,
    )


def test_budget_ok_and_warning_and_exceeded() -> None:
    service = BudgetService()
    estimate = _estimate(Decimal("100"))

    ok_status = service.check_budget(estimate, Decimal("300"))
    assert ok_status is not None
    assert ok_status.status == "ok"

    warn_status = service.check_budget(estimate, Decimal("110"))
    assert warn_status is not None
    assert warn_status.status == "warning"

    exceeded = service.check_budget(estimate, Decimal("90"))
    assert exceeded is not None
    assert exceeded.status == "exceeded"
