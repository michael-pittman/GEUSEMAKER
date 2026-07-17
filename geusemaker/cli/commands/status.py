"""Status command implementation."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import click
from rich.console import Group
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
from geusemaker.infra import AWSClientFactory, StateManager
from geusemaker.services.ec2 import EC2Service
from geusemaker.services.health import HealthCheckClient
from geusemaker.services.health.services import NGINX_ROUTES
from geusemaker.services.instance_resolver import InstanceResolver


@click.command("status")
@click.argument("stack_name")
@click.option(
    "--state-dir",
    type=click.Path(file_okay=False, dir_okay=True, resolve_path=True),
    help="Optional state directory (default ~/.geusemaker).",
)
@output_option()
def status(stack_name: str, state_dir: str | None, output: str) -> None:
    """
    Show deployment status including EC2 state and service health.

    Displays:
    - EC2 instance state (running/stopped/terminated)
    - Service health checks (n8n, Ollama, Qdrant, Crawl4AI, PostgreSQL)
    - Last state update timestamp
    - Deployment configuration summary
    """
    output_format = OutputFormat(output.lower())
    state_manager = StateManager(base_path=Path(state_dir) if state_dir else None)

    # Load deployment state
    state = asyncio.run(state_manager.load_deployment(stack_name))
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

    # Get EC2 instance status
    client_factory = AWSClientFactory()
    ec2_service = EC2Service(client_factory, region=state.config.region)

    try:
        active_instance = InstanceResolver(client_factory, region=state.config.region).resolve(state)
        state_manager.save_deployment_sync(state)
        instance_desc = ec2_service.describe_instance(active_instance.instance_id)
        instance_state = instance_desc.get("State", {}).get("Name", "unknown")
        instance_type = instance_desc.get("InstanceType", state.config.instance_type)
        public_ip = instance_desc.get("PublicIpAddress")
        private_ip = instance_desc.get("PrivateIpAddress", state.private_ip)
    except RuntimeError as exc:
        # Instance might be terminated or not exist
        instance_state = "not_found"
        instance_type = state.config.instance_type
        public_ip = state.public_ip
        private_ip = state.private_ip
        if output_format == OutputFormat.TEXT:
            console.print(
                f"{EMOJI['warning']} Warning: Could not retrieve instance status: {exc}",
                verbosity="warning",
            )

    # Check service health if instance is running
    health_status = {}
    if instance_state == "running" and (public_ip or private_ip):
        host = public_ip or private_ip
        health_status = asyncio.run(_check_services(host))
        # PostgreSQL is intentionally not exposed outside the instance (no host
        # port, no SG rule); n8n's health implies its database is reachable.
        health_status["PostgreSQL"] = "internal"
    else:
        # Instance not running, mark all services as unavailable
        for service_name in ["n8n", "Qdrant", "Ollama", "Crawl4AI", "PostgreSQL"]:
            health_status[service_name] = "unavailable"

    # Output results
    if output_format == OutputFormat.TEXT:
        _display_status_text(stack_name, state, instance_state, instance_type, public_ip, private_ip, health_status)
    else:
        _emit_status_json(
            stack_name,
            state,
            instance_state,
            instance_type,
            public_ip,
            private_ip,
            health_status,
            output_format,
        )


async def _check_services(host: str) -> dict[str, str]:
    """Probe all services through NGINX path routes inside one event loop.

    A single loop matters: httpx.AsyncClient binds to the loop it first runs
    on, so per-service asyncio.run() calls fail from the second check onward.
    """
    client = HealthCheckClient()
    services = [
        ("n8n", NGINX_ROUTES["n8n"]),
        ("Qdrant", NGINX_ROUTES["qdrant"]),
        ("Ollama", NGINX_ROUTES["ollama"]),
        ("Crawl4AI", NGINX_ROUTES["crawl4ai"]),
    ]

    async def _probe(name: str, path: str) -> tuple[str, str]:
        try:
            result = await client.check_http(f"http://{host}{path}", timeout_seconds=5)
            return name, "healthy" if result.healthy else "unhealthy"
        except Exception:  # noqa: BLE001
            return name, "unreachable"

    results = await asyncio.gather(*(_probe(name, path) for name, path in services))
    return dict(results)


def _display_status_text(
    stack_name: str,
    state: Any,
    instance_state: str,
    instance_type: str,
    public_ip: str | None,
    private_ip: str,
    health_status: dict[str, str],
) -> None:
    """Display status in Rich text format."""
    # Instance status table
    instance_table = Table(show_header=False, box=None, padding=(0, 2))
    instance_table.add_column("Property", style="cyan")
    instance_table.add_column("Value")

    # Colorize instance state
    state_colors = {
        "running": "green",
        "stopped": "yellow",
        "stopping": "yellow",
        "terminated": "red",
        "terminating": "red",
        "pending": "yellow",
        "not_found": "red",
    }
    state_color = state_colors.get(instance_state, "white")

    instance_table.add_row("Instance ID", state.instance_id)
    instance_table.add_row("State", f"[{state_color}]{instance_state}[/{state_color}]")
    instance_table.add_row("Instance Type", instance_type)
    instance_table.add_row("Public IP", public_ip or "N/A")
    instance_table.add_row("Private IP", private_ip)
    instance_table.add_row("VPC ID", state.vpc_id)
    instance_table.add_row("Region", state.config.region)
    instance_table.add_row("Tier", state.config.tier)
    instance_table.add_row("Last Updated", str(state.updated_at))

    # Service health table
    health_table = Table(show_header=True, box=None)
    health_table.add_column("Service", style="cyan")
    health_table.add_column("Route")
    health_table.add_column("Status")

    service_routes = {
        "n8n": NGINX_ROUTES["n8n"],
        "Qdrant": NGINX_ROUTES["qdrant"],
        "Ollama": NGINX_ROUTES["ollama"],
        "Crawl4AI": NGINX_ROUTES["crawl4ai"],
        "PostgreSQL": "(not exposed)",
    }

    for service_name, route in service_routes.items():
        status_text = health_status.get(service_name, "unknown")
        status_colors = {
            "healthy": "green",
            "unhealthy": "red",
            "unreachable": "yellow",
            "unavailable": "dim",
            "internal": "dim",
        }
        status_color = status_colors.get(status_text, "white")
        status_icon = {
            "healthy": "✓",
            "unhealthy": "✗",
            "unreachable": "⚠",
            "unavailable": "—",
            "internal": "•",
        }
        icon = status_icon.get(status_text, "?")

        health_table.add_row(
            service_name,
            route,
            f"[{status_color}]{icon} {status_text}[/{status_color}]",
        )

    # Display grouped panels
    console.print(
        Panel(
            Group(
                Panel(instance_table, title="Instance Status", border_style="blue"),
                Panel(health_table, title="Service Health", border_style="green"),
            ),
            title=f"{EMOJI['info']} Status: {stack_name}",
            border_style="cyan",
        ),
        verbosity="info",
    )


def _emit_status_json(
    stack_name: str,
    state: Any,
    instance_state: str,
    instance_type: str,
    public_ip: str | None,
    private_ip: str,
    health_status: dict[str, str],
    output_format: OutputFormat,
) -> None:
    """Emit status in JSON/YAML format."""
    data = {
        "stack_name": stack_name,
        "instance": {
            "instance_id": state.instance_id,
            "state": instance_state,
            "instance_type": instance_type,
            "public_ip": public_ip,
            "private_ip": private_ip,
        },
        "vpc": {
            "vpc_id": state.vpc_id,
            "subnet_ids": state.subnet_ids,
            "security_group_id": state.security_group_id,
        },
        "storage": {
            "efs_id": state.efs_id,
            "efs_mount_target_id": state.efs_mount_target_id,
        },
        "health": health_status,
        "config": {
            "region": state.config.region,
            "tier": state.config.tier,
            "instance_type": state.config.instance_type,
            "use_spot": state.config.use_spot,
        },
        "updated_at": str(state.updated_at),
    }

    payload = build_response(status="ok", message="Status retrieved successfully", data=data)
    emit_result(payload, output_format)


__all__ = ["status"]
