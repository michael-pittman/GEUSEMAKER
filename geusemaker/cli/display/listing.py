"""Rich display helpers for deployment listing and inspection."""

from __future__ import annotations

from rich.table import Table

from geusemaker.models import DeploymentState


def render_deployment_list(states: list[DeploymentState]) -> Table:
    """Render a list of deployments."""
    table = Table(title="Deployments", show_lines=False)
    table.add_column("Name", style="bold")
    table.add_column("Status")
    table.add_column("Tier")
    table.add_column("Region")
    table.add_column("Compute Subnets")
    table.add_column("Storage Subnet")
    table.add_column("Created")
    table.add_column("Cost/mo")
    table.add_column("n8n URL")

    for state in states:
        table.add_row(
            state.stack_name,
            state.status,
            state.config.tier,
            state.config.region,
            ", ".join(state.subnet_ids),
            state.storage_subnet_id or "-",
            state.created_at.isoformat(),
            str(state.cost.estimated_monthly_cost),
            state.n8n_url or "-",
        )
    return table


def render_inspection(state: DeploymentState) -> Table:
    """Render a single deployment inspection."""
    table = Table(title=f"Deployment: {state.stack_name}", show_lines=False)
    table.add_column("Field")
    table.add_column("Value")

    rows = [
        ("Status", state.status),
        ("Tier", state.config.tier),
        ("Region", state.config.region),
        ("Created", state.created_at.isoformat()),
        ("Updated", state.updated_at.isoformat()),
        ("VPC", state.vpc_id),
        ("Compute Subnets", ", ".join(state.subnet_ids)),
        ("Storage Subnet", state.storage_subnet_id or "-"),
        ("Security Group", state.security_group_id),
        ("EFS", state.efs_id),
        ("Mount Target", state.efs_mount_target_id),
        ("EFS Subnet", state.storage_subnet_id or "-"),
        ("Instance", state.instance_id),
        ("Key Pair", state.keypair_name),
        ("Public IP", state.public_ip or "-"),
        ("Private IP", state.private_ip),
        ("n8n URL", state.n8n_url),
        ("Est. Monthly Cost", str(state.cost.estimated_monthly_cost)),
    ]
    for field, value in rows:
        table.add_row(field, str(value))
    return table


__all__ = ["render_deployment_list", "render_inspection"]
