"""Health check models."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class HealthCheckResult(BaseModel):
    """Result of a single health check."""

    service_name: str
    healthy: bool
    status_code: int | None = None
    response_time_ms: float
    error_message: str | None = None
    endpoint: str
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    retry_count: int = 0


class HealthCheckConfig(BaseModel):
    """Configuration for a health check."""

    service_name: str
    endpoint: str
    expected_status: int = 200
    timeout_seconds: float = 10.0
    max_retries: int = 3
    retry_delay_seconds: float = 0.5


__all__ = ["HealthCheckResult", "HealthCheckConfig"]
