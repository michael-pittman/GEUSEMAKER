"""Models for deployment update operations."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class UpdateRequest(BaseModel):
    """User request to update a deployment."""

    deployment_name: str
    instance_type: str | None = None
    container_images: dict[str, str] | None = None
    force: bool = False


class UpdateResult(BaseModel):
    """Outcome of an update operation."""

    success: bool
    changes_applied: list[str] = Field(default_factory=list)
    previous_state: dict[str, Any] = Field(default_factory=dict)
    new_state: dict[str, Any] = Field(default_factory=dict)
    duration_seconds: float = 0.0
    warnings: list[str] = Field(default_factory=list)


__all__ = ["UpdateRequest", "UpdateResult"]
