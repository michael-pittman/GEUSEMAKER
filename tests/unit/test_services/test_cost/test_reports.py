from __future__ import annotations

from decimal import Decimal

from geusemaker.models.cost import (
    ComponentCost,
    CostBreakdown,
    CostComparison,
    CostEstimate,
)
from geusemaker.services.cost import CostReportService


def _estimate() -> CostEstimate:
    compute = ComponentCost(
        resource_type="compute",
        description="test",
        hourly_cost=Decimal("0.10"),
        monthly_cost=Decimal("73"),
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
        spot_monthly=Decimal("73"),
        on_demand_monthly=Decimal("90"),
        hourly_savings=Decimal("0.02"),
        monthly_savings=Decimal("17"),
        savings_percentage=18.8,
    )
    return CostEstimate(
        deployment_name="stack",
        tier="dev",
        hourly_cost=Decimal("0.10"),
        monthly_cost=Decimal("73"),
        breakdown=breakdown,
        comparison=comparison,
    )


def test_report_and_json_export() -> None:
    report_service = CostReportService()
    estimate = _estimate()
    report = report_service.build_report(estimate, runtime_hours=10.0)
    assert report["deployment"] == "stack"
    assert "hourly_cost" in report
    json_body = report_service.to_json(report)
    assert '"deployment":"stack"' in json_body
