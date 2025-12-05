"""Cost estimation and budget models."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ComponentCost(BaseModel):
    """Cost for a single resource component."""

    resource_type: str
    description: str
    hourly_cost: Decimal
    monthly_cost: Decimal
    unit_price: Decimal
    unit: str
    quantity: float


class CostBreakdown(BaseModel):
    """Breakdown of deployment costs by resource."""

    compute: ComponentCost
    storage: ComponentCost
    networking: ComponentCost
    data_transfer: ComponentCost
    load_balancer: ComponentCost | None = None
    cdn: ComponentCost | None = None
    total: ComponentCost | None = None


class CostComparison(BaseModel):
    """Spot vs on-demand comparison."""

    spot_hourly: Decimal
    on_demand_hourly: Decimal
    spot_monthly: Decimal
    on_demand_monthly: Decimal
    hourly_savings: Decimal
    monthly_savings: Decimal
    savings_percentage: float


class CostEstimate(BaseModel):
    """Full deployment cost estimate."""

    model_config = ConfigDict(populate_by_name=True)

    deployment_name: str
    tier: Literal["dev", "automation", "gpu"]
    hourly_cost: Decimal
    monthly_cost: Decimal
    breakdown: CostBreakdown
    comparison: CostComparison
    estimated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    pricing_source: Literal["live", "cached", "estimated"] = "live"

    def to_json(self) -> str:
        """Return a JSON string representation suitable for export."""
        return json.dumps(self.model_dump(mode="json"), default=str, separators=(",", ":"))


class BudgetStatus(BaseModel):
    """Result of comparing estimate to a budget."""

    budget_limit: Decimal
    estimated_monthly: Decimal
    percentage_of_budget: float
    status: Literal["ok", "warning", "exceeded"]
    message: str


class CostSnapshot(BaseModel):
    """Historical cost checkpoint."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    hourly_cost: Decimal
    total_cost_to_date: Decimal
    runtime_hours: float


class ResourceTags(BaseModel):
    """Standardized deployment tags."""

    deployment: str
    tier: str
    created_at: str
    created_by: str = "geusemaker"

    def to_aws(self) -> list[dict[str, str]]:
        """Return AWS tag dicts."""
        return [
            {"Key": "geusemaker:deployment", "Value": self.deployment},
            {"Key": "geusemaker:tier", "Value": self.tier},
            {"Key": "geusemaker:created-at", "Value": self.created_at},
            {"Key": "geusemaker:created-by", "Value": self.created_by},
        ]


__all__ = [
    "BudgetStatus",
    "ComponentCost",
    "CostBreakdown",
    "CostComparison",
    "CostEstimate",
    "CostSnapshot",
    "ResourceTags",
]
