"""Monitoring models for continuous health checks."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class ServiceMetrics(BaseModel):
    """Aggregated metrics for a service."""

    service_name: str
    total_checks: int = 0
    successful_checks: int = 0
    failed_checks: int = 0
    uptime_percentage: float = 0.0
    last_check_at: datetime | None = None
    last_status: Literal["healthy", "unhealthy", "unknown"] = "unknown"
    consecutive_failures: int = 0
    average_response_time_ms: float = 0.0
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    disk_percent: float = 0.0
    last_resource_check: datetime | None = None

    def record(self, healthy: bool, response_time_ms: float) -> None:
        self.total_checks += 1
        if healthy:
            self.successful_checks += 1
            self.consecutive_failures = 0
        else:
            self.failed_checks += 1
            self.consecutive_failures += 1
        self.last_status = "healthy" if healthy else "unhealthy"
        self.last_check_at = datetime.now(UTC)
        # incremental average to avoid large memory usage
        self.average_response_time_ms += (response_time_ms - self.average_response_time_ms) / self.total_checks
        self.uptime_percentage = (self.successful_checks / self.total_checks) * 100.0 if self.total_checks else 0.0


class MonitoringState(BaseModel):
    """Overall monitoring state for a deployment."""

    deployment_name: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    check_interval_seconds: int = 60
    total_checks: int = 0
    service_metrics: dict[str, ServiceMetrics] = Field(default_factory=dict)

    @property
    def overall_uptime_percentage(self) -> float:
        """Average uptime across all services."""
        if not self.service_metrics:
            return 0.0
        return sum(m.uptime_percentage for m in self.service_metrics.values()) / len(self.service_metrics)


class HealthEvent(BaseModel):
    """Event emitted during monitoring."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    service_name: str
    event_type: Literal["check", "status_change", "alert"]
    previous_status: Literal["healthy", "unhealthy", "unknown"] | None = None
    new_status: Literal["healthy", "unhealthy", "unknown"]
    details: str | None = None


__all__ = ["ServiceMetrics", "MonitoringState", "HealthEvent"]
