"""Cost report generation."""

from __future__ import annotations

import json
from decimal import Decimal

from geusemaker.models.cost import BudgetStatus, CostEstimate, CostSnapshot


class CostReportService:
    """Generate structured cost reports for deployments."""

    def build_report(
        self,
        estimate: CostEstimate,
        runtime_hours: float = 0.0,
        budget_status: BudgetStatus | None = None,
        cost_history: list[CostSnapshot] | None = None,
    ) -> dict:
        """Return a dictionary with key cost metrics."""
        total_cost_to_date = estimate.hourly_cost * Decimal(str(runtime_hours))
        return {
            "deployment": estimate.deployment_name,
            "tier": estimate.tier,
            "estimated_at": estimate.estimated_at.isoformat(),
            "hourly_cost": str(estimate.hourly_cost),
            "monthly_cost": str(estimate.monthly_cost),
            "runtime_hours": runtime_hours,
            "cost_to_date": str(total_cost_to_date),
            "budget": budget_status.model_dump() if budget_status else None,
            "history": [snap.model_dump() for snap in cost_history or []],
        }

    def snapshot(self, estimate: CostEstimate, runtime_hours: float) -> CostSnapshot:
        """Create a cost snapshot for history tracking."""
        total_cost = estimate.hourly_cost * Decimal(str(runtime_hours))
        return CostSnapshot(
            hourly_cost=estimate.hourly_cost,
            total_cost_to_date=total_cost,
            runtime_hours=runtime_hours,
        )

    def to_json(self, report: dict) -> str:
        """Serialize a report dictionary to JSON."""
        return json.dumps(report, separators=(",", ":"), default=str)


__all__ = ["CostReportService"]
