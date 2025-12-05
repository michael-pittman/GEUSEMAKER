"""Compute and spot selection data models."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SavingsComparison(BaseModel):
    """Spot vs on-demand savings snapshot."""

    on_demand_hourly: Decimal
    selected_hourly: Decimal
    hourly_savings: Decimal
    monthly_savings: Decimal
    savings_percentage: float


class SpotAnalysis(BaseModel):
    """Spot market analysis for an instance type."""

    model_config = ConfigDict(populate_by_name=True)

    instance_type: str
    region: str
    prices_by_az: dict[str, Decimal]
    recommended_az: str | None
    lowest_price: Decimal
    price_stability_score: float
    on_demand_price: Decimal
    savings_percentage: float
    analysis_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class InstanceSelection(BaseModel):
    """Final compute selection for a deployment."""

    instance_type: str
    availability_zone: str | None
    is_spot: bool
    price_per_hour: Decimal
    selection_reason: str
    fallback_reason: str | None = None
    savings_vs_on_demand: SavingsComparison
    pricing_source: Literal["live", "cached", "estimated"] = "live"


__all__ = ["SavingsComparison", "SpotAnalysis", "InstanceSelection"]
