"""Rich display helpers for validation results."""

from __future__ import annotations

from rich.table import Table

from geusemaker.models.validation import ValidationCheck, ValidationReport


def _status_label(check: ValidationCheck) -> str:
    if check.passed:
        return "[green]PASS[/green]"
    if check.severity == "warning":
        return "[yellow]WARN[/yellow]"
    return "[red]FAIL[/red]"


def render_validation_report(report: ValidationReport) -> Table:
    """Render validation results as a Rich table."""
    table = Table(title="Pre-Deployment Validation", show_lines=False)
    table.add_column("Status", style="bold", no_wrap=True)
    table.add_column("Check", no_wrap=True)
    table.add_column("Message")
    table.add_column("Remediation")

    for check in report.checks:
        table.add_row(
            _status_label(check),
            check.check_name,
            _message_with_details(check),
            check.remediation or "-",
        )

    return table


def _message_with_details(check: ValidationCheck) -> str:
    if check.details:
        return f"{check.message} ({check.details})"
    return check.message


__all__ = ["render_validation_report"]
