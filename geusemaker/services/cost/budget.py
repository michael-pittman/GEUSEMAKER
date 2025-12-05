"""Budget evaluation helpers."""

from __future__ import annotations

from decimal import Decimal

from geusemaker.models.cost import BudgetStatus, CostEstimate


class BudgetService:
    """Compare estimates to user-provided budgets."""

    def check_budget(self, estimate: CostEstimate, budget: Decimal | None) -> BudgetStatus | None:
        if budget is None:
            return None

        percentage = float((estimate.monthly_cost / budget) * Decimal("100")) if budget else 0.0
        if percentage >= 100:
            status = "exceeded"
            message = "Estimated monthly cost exceeds budget. Deployment blocked unless forced."
        elif percentage >= 80:
            status = "warning"
            message = "Estimated monthly cost exceeds 80% of budget."
        else:
            status = "ok"
            message = "Estimated monthly cost is within budget."

        return BudgetStatus(
            budget_limit=budget,
            estimated_monthly=estimate.monthly_cost,
            percentage_of_budget=percentage,
            status=status,  # type: ignore[arg-type]
            message=message,
        )


__all__ = ["BudgetService"]
