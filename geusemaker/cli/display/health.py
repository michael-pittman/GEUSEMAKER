"""Rich display helpers for health checks."""

from __future__ import annotations

from rich.table import Table

from geusemaker.models.health import HealthCheckResult


def render_health_results(results: list[HealthCheckResult]) -> Table:
    """Render health results as a table."""
    table = Table(title="Service Health", show_lines=False)
    table.add_column("Service", no_wrap=True)
    table.add_column("Status", no_wrap=True, style="bold")
    table.add_column("Latency (ms)", justify="right")
    table.add_column("Endpoint")
    table.add_column("Details")

    for result in results:
        status = "[green]HEALTHY[/green]" if result.healthy else "[red]UNHEALTHY[/red]"
        detail = result.error_message or "-"
        table.add_row(
            result.service_name,
            status,
            f"{result.response_time_ms:.1f}",
            result.endpoint,
            detail,
        )
    return table


__all__ = ["render_health_results"]
