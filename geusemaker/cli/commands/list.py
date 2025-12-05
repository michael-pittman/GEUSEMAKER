"""List deployments from state."""

from __future__ import annotations

import asyncio
from pathlib import Path

import click

from geusemaker.cli import console
from geusemaker.cli.display.listing import render_deployment_list
from geusemaker.cli.output import (
    OutputFormat,
    build_response,
    emit_result,
    output_option,
)
from geusemaker.infra import AWSClientFactory
from geusemaker.infra.state import StateManager
from geusemaker.services.state_recovery import StateRecoveryService


@click.command("list")
@output_option()
@click.option(
    "--state-dir",
    type=click.Path(file_okay=False, dir_okay=True, resolve_path=True),
    help="Optional state directory (default ~/.geusemaker).",
)
@click.option(
    "--discover-from-aws",
    is_flag=True,
    default=False,
    help="Discover deployments from AWS resources (useful if state files are missing).",
)
@click.option(
    "--region",
    type=str,
    default="us-east-1",
    help="AWS region to scan for deployments (default: us-east-1).",
)
def list_deployments(output: str, state_dir: str | None, discover_from_aws: bool, region: str) -> None:
    """List deployments from state files or AWS resources."""
    manager = StateManager(base_path=Path(state_dir) if state_dir else None)

    if discover_from_aws:
        # Discover deployments from AWS resources
        recovery_service = StateRecoveryService(AWSClientFactory(), region=region)
        states = recovery_service.discover_deployments()

        # Optionally save discovered states
        for state in states:
            asyncio.run(manager.save_deployment(state))

        console.print(
            f"[green]✓[/green] Discovered {len(states)} deployment(s) from AWS in {region}",
            verbosity="info",
        )
    else:
        # List deployments from state files
        states = asyncio.run(manager.list_deployments())

    output_format = OutputFormat(output.lower())
    if output_format == OutputFormat.TEXT:
        console.print(render_deployment_list(states), verbosity="result")
        return

    emit_result(
        build_response(data=states, status="ok", message="Deployments listed."),
        output_format,
    )


__all__ = ["list_deployments"]
