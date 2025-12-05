"""Show deployment information in a single command."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import click
from rich.panel import Panel
from rich.table import Table

from geusemaker.cli import console
from geusemaker.cli.branding import EMOJI
from geusemaker.cli.output import (
    OutputFormat,
    build_response,
    emit_result,
    output_option,
)
from geusemaker.infra.state import StateManager
from geusemaker.services.health import HealthCheckClient, check_all_services


@click.command("info")
@click.argument("stack_name")
@output_option()
@click.option(
    "--state-dir",
    type=click.Path(file_okay=False, dir_okay=True, resolve_path=True),
    help="Optional state directory (default ~/.geusemaker).",
)
@click.option("--host", help="Override host/IP for endpoint and health checks.")
@click.option("--skip-health", is_flag=True, default=False, help="Skip live health checks.")
def info(stack_name: str, output: str, state_dir: str | None, host: str | None, skip_health: bool) -> None:
    """Display endpoints, credentials, health, cost, and SSH info."""
    manager = StateManager(base_path=Path(state_dir) if state_dir else None)
    state = asyncio.run(manager.load_deployment(stack_name))
    output_format = OutputFormat(output.lower())
    if state is None:
        payload = build_response(
            status="error",
            message=f"Deployment '{stack_name}' not found.",
            error_code="not_found",
        )
        if output_format == OutputFormat.TEXT:
            console.print(f"{EMOJI['error']} Deployment '{stack_name}' not found.", verbosity="error")
        else:
            emit_result(payload, output_format)
        raise SystemExit(1)

    resolved_host = host or state.public_ip or state.private_ip
    display_host = resolved_host or "unknown"
    endpoints = {
        "n8n": f"http://{display_host}:5678",
        "ollama": f"http://{display_host}:11434",
        "qdrant": f"http://{display_host}:6333",
        "crawl4ai": f"http://{display_host}:11235",
    }
    ssh_info = {
        "user": "ec2-user",
        "key_pair": state.keypair_name,
        "command": f"ssh -i <path-to-{state.keypair_name or 'keypair'}.pem> ec2-user@{display_host}",
    }
    cost_info = {
        "hourly": float(state.cost.spot_price_per_hour or state.cost.on_demand_price_per_hour),
        "monthly": float(state.cost.estimated_monthly_cost),
        "is_spot": state.cost.is_spot,
        "budget_limit": float(state.config.budget_limit) if state.config.budget_limit else None,
    }

    health_summary: dict[str, Any] | None = None
    if not skip_health and resolved_host:
        try:
            results = asyncio.run(check_all_services(HealthCheckClient(), host=resolved_host))
            health_summary = {
                "overall": "healthy" if all(r.healthy for r in results) else "degraded",
                "services": [r.model_dump() for r in results],
            }
        except Exception as exc:  # noqa: BLE001
            health_summary = {"overall": "unknown", "error": str(exc)}

    data = {
        "stack_name": state.stack_name,
        "status": state.status,
        "region": state.config.region,
        "tier": state.config.tier,
        "host": display_host,
        "endpoints": endpoints,
        "credentials": {
            "ssh_user": "ec2-user",
            "key_pair": state.keypair_name,
            "notes": "Rotate default credentials after first login.",
        },
        "ssh": ssh_info,
        "cost": cost_info,
        "health": health_summary,
        "next_steps": _next_steps(state.status),
    }

    if output_format == OutputFormat.TEXT:
        console.print(_render_text_info(data), verbosity="result")
    else:
        emit_result(build_response(status="ok", data=data, message="Deployment info"), output_format)


def _render_text_info(data: dict[str, Any]) -> Panel:
    header = Table.grid(padding=(0, 1))
    header.add_column(justify="left", style="bold cyan")
    header.add_column(justify="left")
    header.add_row("Stack", data["stack_name"])
    header.add_row("Status", data["status"])
    header.add_row("Region", data["region"])
    header.add_row("Tier", data["tier"])

    endpoints_table = Table(title="Service Endpoints", show_lines=False)
    endpoints_table.add_column("Service", style="bold")
    endpoints_table.add_column("URL")
    for name, url in data["endpoints"].items():
        endpoints_table.add_row(name, url)

    ssh_table = Table(title="SSH Access", show_lines=False)
    ssh_table.add_column("Field")
    ssh_table.add_column("Value")
    ssh = data["ssh"]
    ssh_table.add_row("User", ssh["user"])
    ssh_table.add_row("Key Pair", ssh["key_pair"] or "-")
    ssh_table.add_row("Command", ssh["command"])

    cost_table = Table(title="Cost", show_lines=False)
    cost_table.add_column("Metric")
    cost_table.add_column("Value")
    cost = data["cost"]
    cost_table.add_row("Hourly", f"${cost['hourly']:.4f}")
    cost_table.add_row("Monthly", f"${cost['monthly']:.2f}")
    cost_table.add_row("Mode", "spot" if cost["is_spot"] else "on-demand")
    cost_table.add_row("Budget", f"${cost['budget_limit']:.2f}" if cost["budget_limit"] else "Not set")

    health_table = Table(title="Health", show_lines=False)
    health_table.add_column("Service")
    health_table.add_column("Status")
    if data["health"] and data["health"].get("services"):
        for svc in data["health"]["services"]:
            health_table.add_row(svc["service_name"], "healthy" if svc["healthy"] else "unhealthy")
    elif data["health"] and data["health"].get("error"):
        health_table.add_row("overall", data["health"]["error"])
    else:
        health_table.add_row("overall", "Skipped")

    next_steps = "\n".join(f"- {step}" for step in data["next_steps"])
    body = Table.grid(padding=1)
    body.add_row(endpoints_table)
    body.add_row(ssh_table)
    body.add_row(cost_table)
    body.add_row(health_table)
    body.add_row(next_steps)
    return Panel(body, title=f"{EMOJI['info']} {data['stack_name']}", subtitle="Deployment info", expand=False)


def _next_steps(status: str) -> list[str]:
    if status in {"creating", "updating"}:
        return ["Wait for deployment to finish, then run `geusemaker health ...`", "Review costs and budgets."]
    if status == "running":
        return [
            "Change default credentials and rotate keys.",
            "Enable monitoring via `geusemaker monitor start <stack>`.",
            "Schedule backups if needed.",
        ]
    if status == "failed":
        return ["Inspect logs and validation reports.", "Consider rollback or redeploy."]
    return ["Review deployment details and plan next actions."]


__all__ = ["info"]
