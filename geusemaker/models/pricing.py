"""Pricing-related data models."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SpotPrice(BaseModel):
    """Spot price entry for a specific AZ and instance type."""

    model_config = ConfigDict(populate_by_name=True)

    instance_type: str
    availability_zone: str
    price_per_hour: Decimal = Field(..., gt=0)
    timestamp: datetime
    region: str


class OnDemandPrice(BaseModel):
    """On-demand pricing details."""

    model_config = ConfigDict(populate_by_name=True)

    instance_type: str
    price_per_hour: Decimal = Field(..., gt=0)
    region: str
    operating_system: Literal["Linux", "Windows"] = "Linux"
    currency: str = "USD"


class EFSPricing(BaseModel):
    """EFS storage pricing (per GB-month)."""

    region: str
    standard_gb_month: Decimal
    ia_gb_month: Decimal
    throughput_mibps: Decimal | None = None


class ALBPricing(BaseModel):
    """ALB hourly and LCU pricing."""

    region: str
    hourly_price: Decimal
    lcu_price: Decimal


class CloudFrontPricing(BaseModel):
    """CloudFront pricing for data transfer and requests."""

    price_class: str
    data_transfer_gb: Decimal
    requests_per_10k: Decimal


class PricingResult(BaseModel):
    """Metadata wrapper for pricing lookups."""

    source: Literal["live", "cached", "estimated"]
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    notes: str | None = None


__all__ = [
    "SpotPrice",
    "OnDemandPrice",
    "EFSPricing",
    "ALBPricing",
    "CloudFrontPricing",
    "PricingResult",
]
