"""Rich renderers for cost information."""

from __future__ import annotations

from decimal import Decimal

from rich.panel import Panel
from rich.table import Table

from geusemaker.cli import console
from geusemaker.cli.branding import EMOJI
from geusemaker.models.cost import BudgetStatus, CostEstimate, CostSnapshot


def _fmt_money(value: Decimal) -> str:
    return f"${value.quantize(Decimal('0.0001'))}"


def render_cost_estimate(estimate: CostEstimate) -> None:
    """Render a cost estimate with hourly and monthly breakdowns."""
    table = Table(
        title=f"{EMOJI['money']} Cost Estimate for {estimate.deployment_name}",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Resource")
    table.add_column("Hourly")
    table.add_column("Monthly")
    table.add_column("Details")

    breakdown = estimate.breakdown
    for component in [
        breakdown.compute,
        breakdown.storage,
        breakdown.data_transfer,
        breakdown.load_balancer,
        breakdown.cdn,
    ]:
        if component is None:
            continue
        table.add_row(
            component.resource_type,
            _fmt_money(component.hourly_cost),
            _fmt_money(component.monthly_cost),
            component.description,
        )

    table.add_row(
        "total",
        _fmt_money(estimate.hourly_cost),
        _fmt_money(estimate.monthly_cost),
        "Total estimated cost",
        end_section=True,
    )
    console.print(table)

    comparison = estimate.comparison
    console.print(
        Panel(
            f"Spot vs On-demand savings: "
            f"[green]{comparison.savings_percentage:.1f}%[/green] "
            f"(${comparison.monthly_savings:.2f} / month)",
            border_style="green",
        ),
    )


def render_budget_status(status: BudgetStatus | None) -> None:
    """Display budget warnings or confirmations."""
    if status is None:
        return

    style = "green"
    icon = EMOJI["check"]
    if status.status == "warning":
        style = "yellow"
        icon = EMOJI["warning"]
    elif status.status == "exceeded":
        style = "red"
        icon = EMOJI["error"]

    console.print(
        Panel(
            f"{icon} {status.message}\n"
            f"Estimated: {_fmt_money(status.estimated_monthly)} / "
            f"Budget: {_fmt_money(status.budget_limit)} "
            f"({status.percentage_of_budget:.1f}%)",
            border_style=style,
        ),
    )


def render_cost_history(history: list[CostSnapshot]) -> None:
    """Render cost history snapshots."""
    if not history:
        return
    table = Table(title=f"{EMOJI['chart']} Cost History", header_style="bold magenta")
    table.add_column("Timestamp")
    table.add_column("Runtime Hours")
    table.add_column("Hourly Cost")
    table.add_column("Total to Date")

    for snap in history:
        table.add_row(
            snap.timestamp.isoformat(),
            f"{snap.runtime_hours:.1f}",
            _fmt_money(snap.hourly_cost),
            _fmt_money(snap.total_cost_to_date),
        )
    console.print(table)


__all__ = ["render_cost_estimate", "render_budget_status", "render_cost_history"]
