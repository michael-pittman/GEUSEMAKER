"""Models for orphan detection and cleanup."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from geusemaker.models.destruction import DeletedResource


class OrphanedResource(BaseModel):
    """Resource tagged for GeuseMaker with no active deployment."""

    resource_type: str
    resource_id: str
    name: str | None
    region: str
    deployment_tag: str
    created_at: datetime
    age_days: int
    estimated_monthly_cost: Decimal
    tags: dict[str, str] = Field(default_factory=dict)


class CleanupReport(BaseModel):
    """Summary of a cleanup run."""

    scanned_regions: list[str]
    orphans_found: int
    orphans_deleted: int
    orphans_preserved: int
    estimated_monthly_savings: Decimal
    deleted_resources: list[DeletedResource] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


__all__ = ["CleanupReport", "OrphanedResource"]
