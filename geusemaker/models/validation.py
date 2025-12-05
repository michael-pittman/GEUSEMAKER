"""Validation models for pre-deployment checks."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class ValidationCheck(BaseModel):
    """Outcome of a single validation check."""

    check_name: str
    passed: bool
    message: str
    details: str | None = None
    remediation: str | None = None
    severity: Literal["error", "warning", "info"] = "error"


class ValidationSummary(BaseModel):
    """Summary statistics for a validation report."""

    total_checks: int
    passed: int
    failed: int
    warnings: int
    overall_status: Literal["healthy", "degraded", "unhealthy"]
    validation_duration_seconds: float | None = None


class ValidationReport(BaseModel):
    """Aggregated validation results."""

    checks: list[ValidationCheck] = Field(default_factory=list)
    validated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    deployment_name: str | None = None
    deployment_tier: str | None = None
    validation_duration_seconds: float | None = None

    @property
    def errors(self) -> int:
        return sum(1 for check in self.checks if not check.passed and check.severity == "error")

    @property
    def warnings(self) -> int:
        return sum(1 for check in self.checks if not check.passed and check.severity == "warning")

    @property
    def passed(self) -> bool:
        return self.errors == 0

    def add(self, check: ValidationCheck) -> None:
        self.checks.append(check)

    def summary(self) -> ValidationSummary:
        failed = self.errors
        warn = self.warnings
        status: Literal["healthy", "degraded", "unhealthy"]
        if failed == 0 and warn == 0:
            status = "healthy"
        elif failed == 0 and warn > 0:
            status = "degraded"
        else:
            status = "unhealthy"
        return ValidationSummary(
            total_checks=len(self.checks),
            passed=len(self.checks) - failed - warn,
            failed=failed,
            warnings=warn,
            overall_status=status,
            validation_duration_seconds=self.validation_duration_seconds,
        )


__all__ = ["ValidationCheck", "ValidationReport", "ValidationSummary"]
