"""Rollback command."""

from pathlib import Path

import click

from geusemaker.cli import console
from geusemaker.cli.branding import EMOJI
from geusemaker.cli.output import (
    OutputFormat,
    build_response,
    emit_result,
    output_option,
)
from geusemaker.infra.state import StateManager
from geusemaker.services.rollback import RollbackService


@click.command("rollback")
@click.argument("stack_name")
@click.option(
    "--to-version",
    default=1,
    show_default=True,
    help="Rollback to a specific previous state (1 = most recent).",
)
@click.option("--force", is_flag=True, help="Skip confirmation prompt.")
@click.option(
    "--state-dir",
    type=click.Path(file_okay=False, dir_okay=True, resolve_path=True),
    help="Optional state directory (default ~/.geusemaker).",
)
@output_option()
def rollback(stack_name: str, to_version: int, force: bool, state_dir: str | None, output: str) -> None:
    """Rollback a deployment to a previous state."""
    output_format = OutputFormat(output.lower())
    manager = StateManager(base_path=Path(state_dir) if state_dir else None)
    state = asyncio.run(manager.load_deployment(stack_name))
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

    if not state.previous_states:
        payload = build_response(
            status="error",
            message=f"No rollback history available for '{stack_name}'.",
            error_code="no_history",
        )
        if output_format == OutputFormat.TEXT:
            console.print(f"{EMOJI['warning']} No rollback history available for '{stack_name}'.", verbosity="warning")
        else:
            emit_result(payload, output_format)
        raise SystemExit(1)

    if not force:
        console.print(
            f"{EMOJI['warn']} Rolling back [bold]{stack_name}[/bold] to version {to_version} "
            f"(history depth: {len(state.previous_states)}).",
            verbosity="warning",
        )
        if not click.confirm("Proceed with rollback?"):
            console.print(f"{EMOJI['warning']} Rollback cancelled.", verbosity="warning")
            raise SystemExit(0)

    service = RollbackService(state_manager=manager, region=state.config.region)
    try:
        result = service.rollback(state, to_version=to_version)
    except Exception as exc:  # noqa: BLE001
        payload = build_response(status="error", message=f"Rollback failed: {exc}", error_code="rollback_failed")
        if output_format == OutputFormat.TEXT:
            console.print(f"{EMOJI['error']} Rollback failed: {exc}", verbosity="error")
        else:
            emit_result(payload, output_format)
        raise SystemExit(1)

    payload = build_response(
        status="ok",
        message=f"Rolled back {stack_name}",
        data={"changes_reverted": result.changes_reverted},
    )
    if output_format == OutputFormat.TEXT:
        console.print(
            f"{EMOJI['check']} Rolled back [bold]{stack_name}[/bold] "
            f"(changes: {', '.join(result.changes_reverted) or 'none'})",
            verbosity="result",
        )
    else:
        emit_result(payload, output_format)


import asyncio  # noqa: E402

__all__ = ["rollback"]
