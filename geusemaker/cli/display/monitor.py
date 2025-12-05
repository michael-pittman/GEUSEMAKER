"""Rich display for monitoring."""

from __future__ import annotations

from datetime import UTC, datetime

from rich.console import Group
from rich.panel import Panel
from rich.table import Table

from geusemaker.models.monitoring import MonitoringState


def render_monitor_state(state: MonitoringState) -> Panel:
    """Render current monitoring snapshot."""
    meta = Table.grid(expand=True)
    meta.add_column()
    meta.add_column(justify="right")
    meta.add_row(
        f"[bold]Monitoring since:[/bold] {state.started_at.astimezone().strftime('%Y-%m-%d %H:%M:%S')}",
        (
            f"[bold]Checks:[/bold] {state.total_checks}    "
            f"[bold]Interval:[/bold] {state.check_interval_seconds}s    "
            f"[bold]Overall uptime:[/bold] {state.overall_uptime_percentage:.1f}%"
        ),
    )

    table = Table(show_lines=False, expand=True)
    table.add_column("Service", no_wrap=True)
    table.add_column("Status", no_wrap=True, style="bold")
    table.add_column("Uptime %", justify="right")
    table.add_column("Avg Latency (ms)", justify="right")
    table.add_column("Last Check")

    now = datetime.now(UTC)
    if not state.service_metrics:
        table.add_row("-", "-", "-", "-", "-")
    else:
        for metrics in state.service_metrics.values():
            status = "[green]HEALTHY[/green]" if metrics.last_status == "healthy" else "[red]UNHEALTHY[/red]"
            last_check = f"{(now - metrics.last_check_at).total_seconds():.0f}s ago" if metrics.last_check_at else "-"
            table.add_row(
                metrics.service_name,
                status,
                f"{metrics.uptime_percentage:.1f}",
                f"{metrics.average_response_time_ms:.1f}",
                last_check,
            )

    return Panel(
        Group(meta, table),
        title=f"Health Monitor: {state.deployment_name}",
        border_style="cyan",
    )


__all__ = ["render_monitor_state"]
