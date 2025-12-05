"""Models for deployment destruction."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DeletedResource(BaseModel):
    """Resource that was deleted."""

    resource_type: str
    resource_id: str
    deleted_at: datetime
    deletion_time_seconds: float


class PreservedResource(BaseModel):
    """Resource intentionally preserved."""

    resource_type: str
    resource_id: str
    reason: str


class DestructionResult(BaseModel):
    """Outcome of destroying a deployment."""

    success: bool
    deleted_resources: list[DeletedResource] = Field(default_factory=list)
    preserved_resources: list[PreservedResource] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    duration_seconds: float = 0.0
    archived_state_path: str | None = None


__all__ = ["DeletedResource", "PreservedResource", "DestructionResult"]
