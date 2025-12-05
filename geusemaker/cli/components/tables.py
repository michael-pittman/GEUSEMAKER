"""Table helpers for interactive flows."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from rich.panel import Panel
from rich.table import Table

from geusemaker.cli import console
from geusemaker.cli.components.theme import THEME, is_tty
from geusemaker.cli.display import discovery as discovery_tables
from geusemaker.models.cost import ComponentCost, CostEstimate
from geusemaker.models.discovery import (
    KeyPairInfo,
    SecurityGroupInfo,
    SubnetInfo,
    VPCInfo,
)


def resource_table(
    vpcs: list[VPCInfo] | None = None,
    subnets: list[SubnetInfo] | None = None,
    security_groups: list[SecurityGroupInfo] | None = None,
    key_pairs: list[KeyPairInfo] | None = None,
) -> None:
    """Render discovery tables with consistent styling."""
    if vpcs:
        console.print(discovery_tables.vpc_table(vpcs))
    if subnets:
        console.print(discovery_tables.subnet_table(subnets))
    if security_groups:
        console.print(discovery_tables.security_group_table(security_groups))
    if key_pairs:
        console.print(discovery_tables.key_pair_table(key_pairs))


def resource_recommendations_panel(lines: Iterable[str]) -> None:
    """Display resource recommendations as a panel."""
    text = "\n".join(f"• {line}" for line in lines)
    if not is_tty():
        console.print(text)
        return
    console.print(Panel(text, border_style=THEME.accent, title="Recommendations"))


def cost_preview_table(estimate: CostEstimate) -> None:
    """Render a compact cost preview for confirmation."""
    table = Table(
        title="Estimated Cost",
        header_style=f"bold {THEME.primary}",
        expand=True,
        show_lines=False,
    )
    table.add_column("Resource")
    table.add_column("Hourly", justify="right")
    table.add_column("Monthly", justify="right")
    table.add_column("Details")

    def _row(component: ComponentCost | None) -> None:
        if component is None:
            return
        table.add_row(
            component.resource_type,
            _fmt(component.hourly_cost),
            _fmt(component.monthly_cost),
            component.description,
        )

    breakdown = estimate.breakdown
    _row(breakdown.compute)
    _row(breakdown.storage)
    _row(breakdown.data_transfer)
    _row(breakdown.load_balancer)
    _row(breakdown.cdn)
    if breakdown.total:
        table.add_row(
            "[bold]total[/bold]",
            _fmt(breakdown.total.hourly_cost),
            _fmt(breakdown.total.monthly_cost),
            breakdown.total.description,
        )
    console.print(table)
    summary = (
        f"Spot savings: {estimate.comparison.savings_percentage:.1f}% "
        f"(${estimate.comparison.monthly_savings:.2f} / month)"
    )
    console.print(Panel(summary, border_style=THEME.success))


def _fmt(value: Decimal) -> str:
    return f"${value.quantize(Decimal('0.0001'))}"


__all__ = ["resource_table", "resource_recommendations_panel", "cost_preview_table"]
