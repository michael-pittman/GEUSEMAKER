"""Table helpers for interactive flows."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from rich.panel import Panel
from rich.table import Table

from geusemaker.cli import console
from geusemaker.cli.branding import EMOJI
from geusemaker.cli.components.theme import THEME, is_tty
from geusemaker.cli.display import discovery as discovery_tables
from geusemaker.models.cost import ComponentCost, CostEstimate
from geusemaker.models.deployment import DeploymentConfig
from geusemaker.models.discovery import (
    EFSInfo,
    KeyPairInfo,
    SecurityGroupInfo,
    SubnetInfo,
    VPCInfo,
)


def resource_table(
    vpcs: list[VPCInfo] | None = None,
    subnets: list[SubnetInfo] | None = None,
    security_groups: list[SecurityGroupInfo] | None = None,
    efs_filesystems: list[EFSInfo] | None = None,
    key_pairs: list[KeyPairInfo] | None = None,
) -> None:
    """Render discovery tables with consistent styling."""
    if vpcs:
        console.print(discovery_tables.vpc_table(vpcs))
    if subnets:
        console.print(discovery_tables.subnet_table(subnets))
    if security_groups:
        console.print(discovery_tables.security_group_table(security_groups))
    if efs_filesystems:
        console.print(discovery_tables.efs_table(efs_filesystems))
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


def deployment_summary_table(
    config: DeploymentConfig,
    cost_estimate: float | None = None,
    instance_selection_reason: str | None = None,
) -> None:
    """Display a comprehensive deployment summary before confirmation."""
    table = Table(
        title=f"{EMOJI['info']} Deployment Summary",
        header_style=f"bold {THEME.primary}",
        expand=True,
        show_lines=True,
    )
    table.add_column("Resource", style=THEME.accent)
    table.add_column("Configuration", justify="left")
    table.add_column("Status", justify="center")

    # Deployment details
    table.add_row(
        "[bold]Stack Name[/bold]",
        config.stack_name,
        "",
    )
    table.add_row(
        "[bold]Region[/bold]",
        config.region,
        "",
    )
    table.add_row(
        "[bold]Tier[/bold]",
        config.tier,
        "",
    )

    # Compute
    compute_details = f"{config.instance_type} ({'spot' if config.use_spot else 'on-demand'})"
    if instance_selection_reason:
        compute_details += f"\n[dim]Auto-selected: {instance_selection_reason}[/dim]"
    if config.ami_id:
        compute_details += f"\nAMI: {config.ami_id}"
    else:
        compute_details += f"\nOS: {config.os_type} ({config.architecture})"
    table.add_row(
        "[bold]Compute[/bold]",
        compute_details,
        "",
    )

    # Network resources
    vpc_status = (
        f"[green]{EMOJI['check']} reuse[/green]" if config.vpc_id else f"[yellow]{EMOJI['info']} create[/yellow]"
    )
    vpc_details = config.vpc_id if config.vpc_id else "New VPC will be created"
    if config.attach_internet_gateway:
        vpc_details += "\nInternet Gateway will be attached"
    table.add_row(
        "[bold]VPC[/bold]",
        vpc_details,
        vpc_status,
    )

    subnet_status = (
        f"[green]{EMOJI['check']} reuse[/green]" if config.subnet_id else f"[yellow]{EMOJI['info']} create[/yellow]"
    )
    subnet_details = config.subnet_id if config.subnet_id else "New subnet will be created"
    if config.storage_subnet_id and config.storage_subnet_id != config.subnet_id:
        subnet_details += f"\nStorage: {config.storage_subnet_id}"
    table.add_row(
        "[bold]Subnet[/bold]",
        subnet_details,
        subnet_status,
    )

    sg_status = (
        f"[green]{EMOJI['check']} reuse[/green]"
        if config.security_group_id
        else f"[yellow]{EMOJI['info']} create[/yellow]"
    )
    sg_details = (
        config.security_group_id if config.security_group_id else "New security group (ports: 22, 80, 443, 2049, 5678)"
    )
    table.add_row(
        "[bold]Security Group[/bold]",
        sg_details,
        sg_status,
    )

    # Storage
    table.add_row(
        "[bold]EFS Storage[/bold]",
        "New EFS filesystem (generalPurpose mode)",
        f"[yellow]{EMOJI['info']} create[/yellow]",
    )

    # IAM
    table.add_row(
        "[bold]IAM Role[/bold]",
        f"{config.stack_name}-efs-mount-role (EFS mount permissions)",
        f"[yellow]{EMOJI['info']} create[/yellow]",
    )

    # SSH Key
    key_status = (
        f"[green]{EMOJI['check']} reuse[/green]" if config.keypair_name else f"[yellow]{EMOJI['info']} create[/yellow]"
    )
    key_details = config.keypair_name if config.keypair_name else "New key pair will be created"
    table.add_row(
        "[bold]SSH Key Pair[/bold]",
        key_details,
        key_status,
    )

    # Cost estimate if available
    if cost_estimate is not None:
        table.add_row(
            "[bold]Estimated Cost[/bold]",
            f"${cost_estimate:.2f} / month",
            "",
        )

    console.print(table)

    # Summary message
    new_resources = []
    reused_resources = []

    if not config.vpc_id:
        new_resources.append("VPC")
    else:
        reused_resources.append("VPC")

    if not config.subnet_id:
        new_resources.append("Subnet")
    else:
        reused_resources.append("Subnet")

    if not config.security_group_id:
        new_resources.append("Security Group")
    else:
        reused_resources.append("Security Group")

    if not config.keypair_name:
        new_resources.append("SSH Key Pair")
    else:
        reused_resources.append("SSH Key Pair")

    new_resources.extend(["EFS", "IAM Role", "EC2 Instance"])

    summary_parts = []
    if new_resources:
        summary_parts.append(f"Will create: {', '.join(new_resources)}")
    if reused_resources:
        summary_parts.append(f"Will reuse: {', '.join(reused_resources)}")

    summary_text = " | ".join(summary_parts)
    console.print(Panel(summary_text, border_style=THEME.info, title="Resource Plan"))


def _fmt(value: Decimal) -> str:
    return f"${value.quantize(Decimal('0.0001'))}"


__all__ = ["resource_table", "resource_recommendations_panel", "cost_preview_table", "deployment_summary_table"]
