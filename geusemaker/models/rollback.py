"""Models for rollback operations."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RollbackResult(BaseModel):
    """Outcome of a rollback."""

    success: bool
    trigger: str
    changes_reverted: list[str] = Field(default_factory=list)
    duration_seconds: float = 0.0
    health_status: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None


__all__ = ["RollbackResult"]
