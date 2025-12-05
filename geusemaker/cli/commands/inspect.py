"""Inspect a deployment from state."""

from __future__ import annotations

import asyncio
from pathlib import Path

import click

from geusemaker.cli import console
from geusemaker.cli.display.listing import render_inspection
from geusemaker.cli.output import (
    OutputFormat,
    build_response,
    emit_result,
    output_option,
)
from geusemaker.infra.state import StateManager


@click.command("inspect")
@click.argument("stack_name")
@output_option()
@click.option(
    "--state-dir",
    type=click.Path(file_okay=False, dir_okay=True, resolve_path=True),
    help="Optional state directory (default ~/.geusemaker).",
)
def inspect(stack_name: str, output: str, state_dir: str | None) -> None:
    """Inspect a deployment state file."""
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
            console.print(f"[red]Deployment '{stack_name}' not found.[/red]", verbosity="error")
        else:
            emit_result(payload, output_format)
        raise SystemExit(1)

    if output_format == OutputFormat.TEXT:
        console.print(render_inspection(state), verbosity="result")
        return

    emit_result(build_response(status="ok", data=state), output_format)


__all__ = ["inspect"]
