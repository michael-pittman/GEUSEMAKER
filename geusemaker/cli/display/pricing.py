"""Render pricing and savings information."""

from __future__ import annotations

from rich.panel import Panel
from rich.table import Table

from geusemaker.cli import console
from geusemaker.cli.branding import EMOJI
from geusemaker.models.compute import InstanceSelection, SpotAnalysis


def render_pricing_summary(selection: InstanceSelection, analysis: SpotAnalysis | None = None) -> None:
    """Render a concise pricing and savings summary."""
    table = Table(title=f"{EMOJI['money']} Pricing Summary", header_style="bold green")
    table.add_column("Type")
    table.add_column("AZ")
    table.add_column("Hourly")
    table.add_column("Savings vs OD")

    table.add_row(
        "Spot" if selection.is_spot else "On-demand",
        selection.availability_zone or "-",
        f"${selection.price_per_hour:.4f}",
        f"{selection.savings_vs_on_demand.savings_percentage:.1f}%",
    )

    console.print(table)

    if analysis:
        az = analysis.recommended_az or "n/a"
        detail = (
            f"Recommended AZ: {az}\n"
            f"Lowest spot: ${analysis.lowest_price:.4f} | On-demand: ${analysis.on_demand_price:.4f}\n"
            f"Stability score: {analysis.price_stability_score:.2f}"
        )
        console.print(Panel(detail, border_style="blue"))


__all__ = ["render_pricing_summary"]
