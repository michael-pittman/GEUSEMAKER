"""Validation reporting helpers."""

from __future__ import annotations

import json
from datetime import datetime

import yaml
from rich.panel import Panel
from rich.table import Table

from geusemaker.models.validation import ValidationReport, ValidationSummary


def build_summary(report: ValidationReport) -> ValidationSummary:
    """Return a summary model for a report."""
    return report.summary()


def export_json(report: ValidationReport) -> str:
    """Export a validation report to JSON."""
    return json.dumps(report.model_dump(), default=_default, indent=2)


def export_yaml(report: ValidationReport) -> str:
    """Export a validation report to YAML."""
    return yaml.safe_dump(report.model_dump(), default_flow_style=False)


def render_report(report: ValidationReport) -> Panel:
    """Render a detailed report for Rich output."""
    summary = report.summary()
    table = Table(title="Validation Results", show_lines=False)
    table.add_column("Status", style="bold", no_wrap=True)
    table.add_column("Check")
    table.add_column("Details")
    table.add_column("Remediation")

    for check in report.checks:
        status = _status_label(check.passed, check.severity)
        detail = check.message
        if check.details:
            detail = f"{detail} ({check.details})"
        table.add_row(status, check.check_name, detail, check.remediation or "-")

    header = (
        f"Deployment: {report.deployment_name or 'n/a'}\n"
        f"Tier: {report.deployment_tier or 'n/a'}\n"
        f"Validated: {report.validated_at} "
        f"(took {summary.validation_duration_seconds or 0:.2f}s)\n"
        f"Summary: {summary.passed} passed, {summary.failed} failed, "
        f"{summary.warnings} warning(s) — Status: {summary.overall_status.upper()}"
    )

    return Panel(table, title="Validation Report", subtitle=header, expand=False)


def _status_label(passed: bool, severity: str) -> str:
    if passed:
        return "[green]PASS[/green]"
    if severity == "warning":
        return "[yellow]WARN[/yellow]"
    return "[red]FAIL[/red]"


def _default(obj: object) -> object:
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


__all__ = ["build_summary", "export_json", "export_yaml", "render_report"]
