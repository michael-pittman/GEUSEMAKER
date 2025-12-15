"""Destroy command."""

from pathlib import Path

import click
from rich.progress import Progress, SpinnerColumn, TextColumn

from geusemaker.cli import console, is_silent
from geusemaker.cli.branding import EMOJI
from geusemaker.cli.output import (
    OutputFormat,
    build_response,
    emit_result,
    output_option,
)
from geusemaker.infra.state import StateManager
from geusemaker.services.destruction import DestructionService


@click.command("destroy")
@click.argument("stack_name")
@click.option("--force", is_flag=True, help="Skip confirmation prompt.")
@click.option("--dry-run", is_flag=True, help="Preview deletion without making changes.")
@click.option("--preserve-efs", is_flag=True, help="Preserve EFS filesystem (keep data, delete other resources).")
@click.option(
    "--state-dir",
    type=click.Path(file_okay=False, dir_okay=True, resolve_path=True),
    help="Optional state directory (default ~/.geusemaker).",
)
@output_option()
def destroy(stack_name: str, force: bool, dry_run: bool, preserve_efs: bool, state_dir: str | None, output: str) -> None:
    """Destroy an existing deployment."""
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

    if output_format != OutputFormat.TEXT and not force:
        raise click.UsageError("--force is required when using non-text output modes to avoid interactive prompts.")

    if not force:
        warning_msg = (
            f"{EMOJI['warn']} This will delete resources for [bold]{stack_name}[/bold]. "
            "Reused resources will be preserved."
        )
        if preserve_efs:
            warning_msg += " EFS filesystem will be preserved."
        console.print(warning_msg, verbosity="warning")
        confirmation = click.prompt("Type the deployment name to confirm", default="", show_default=False)
        if confirmation != stack_name:
            console.print(f"{EMOJI['warning']} Confirmation did not match. Destruction cancelled.", verbosity="warning")
            raise SystemExit(0)

    service = DestructionService(state_manager=manager, region=state.config.region)

    # Set up progress tracking
    result = None
    if output_format == OutputFormat.TEXT and not is_silent():
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("Starting destruction...", total=None)

            def update_progress(msg: str) -> None:
                progress.update(task, description=msg)

            try:
                result = service.destroy(state, dry_run=dry_run, preserve_efs=preserve_efs, progress_callback=update_progress)
            except Exception as exc:  # noqa: BLE001
                console.print(f"{EMOJI['error']} Destroy failed: {exc}", verbosity="error")
                raise SystemExit(1)
    else:
        # No progress display for non-TEXT output or silent mode
        try:
            result = service.destroy(state, dry_run=dry_run, preserve_efs=preserve_efs)
        except Exception as exc:  # noqa: BLE001
            payload = build_response(
                status="error",
                message=f"Destroy failed: {exc}",
                error_code="destroy_failed",
            )
            if output_format == OutputFormat.TEXT:
                console.print(f"{EMOJI['error']} Destroy failed: {exc}", verbosity="error")
            else:
                emit_result(payload, output_format)
            raise SystemExit(1)

    if result is None:
        console.print(f"{EMOJI['error']} Destroy failed: no result returned", verbosity="error")
        raise SystemExit(1)

    if result.errors:
        for err in result.errors:
            console.print(f"{EMOJI['error']} {err}", verbosity="error")
        raise SystemExit(1)

    payload_data = {
        "deleted": [r.resource_id for r in result.deleted_resources],
        "preserved": [f"{r.resource_type}:{r.resource_id}" for r in result.preserved_resources],
        "archived_state": str(result.archived_state_path) if result.archived_state_path else None,
        "dry_run": dry_run,
    }

    if dry_run:
        if output_format == OutputFormat.TEXT:
            console.print(
                f"{EMOJI['info']} Dry run complete. Resources that would be deleted: "
                f"{', '.join(r.resource_id for r in result.deleted_resources)}",
                verbosity="result",
            )
        else:
            emit_result(build_response(status="ok", message="Dry run complete", data=payload_data), output_format)
        raise SystemExit(0)

    if output_format == OutputFormat.TEXT:
        console.print(
            f"{EMOJI['check']} Destroyed [bold]{stack_name}[/bold]. "
            f"Archived state: {result.archived_state_path or 'n/a'}",
            verbosity="result",
        )
        if result.preserved_resources:
            preserved = ", ".join(f"{r.resource_type}:{r.resource_id}" for r in result.preserved_resources)
            console.print(f"{EMOJI['info']} Preserved resources: {preserved}", verbosity="info")
    else:
        emit_result(
            build_response(
                status="ok",
                message=f"Destroyed {stack_name}",
                data=payload_data,
            ),
            output_format,
        )


import asyncio  # noqa: E402

__all__ = ["destroy"]
