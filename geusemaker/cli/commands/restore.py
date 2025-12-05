"""Restore deployment state from a backup."""

from __future__ import annotations

from pathlib import Path

import click

from geusemaker.cli import console
from geusemaker.cli.output import (
    OutputFormat,
    build_response,
    emit_result,
    output_option,
)
from geusemaker.infra.state import StateManager
from geusemaker.services.backup import BackupService


def _manager(state_dir: str | None, backup_dir: str | None) -> StateManager:
    base = Path(state_dir) if state_dir else None
    backups = Path(backup_dir) if backup_dir else None
    return StateManager(base_path=base, backups_path=backups)


@click.command("restore")
@click.argument("stack_name")
@click.option(
    "--backup",
    "backup_path",
    type=click.Path(exists=True, dir_okay=False, resolve_path=True),
    help="Path to the backup archive to restore.",
)
@click.option(
    "--latest",
    is_flag=True,
    default=False,
    help="Restore from the most recent backup for the stack.",
)
@click.option(
    "--state-dir",
    type=click.Path(file_okay=False, dir_okay=True, resolve_path=True),
    help="Optional state directory (default ~/.geusemaker).",
)
@click.option(
    "--backup-dir",
    type=click.Path(file_okay=False, dir_okay=True, resolve_path=True),
    help="Optional backup directory (default ~/.geusemaker/backups).",
)
@output_option()
def restore(
    stack_name: str,
    backup_path: str | None,
    latest: bool,
    state_dir: str | None,
    backup_dir: str | None,
    output: str,
) -> None:
    """Restore STACK_NAME from a backup."""
    manager = _manager(state_dir, backup_dir)
    service = BackupService(manager)

    output_format = OutputFormat(output.lower())

    if latest:
        backups = service.list(stack_name)
        if not backups:
            raise click.ClickException(f"No backups found for {stack_name}")
        selected = backups[0].path
    elif backup_path:
        selected = Path(backup_path)
    else:
        raise click.ClickException("Specify --latest or --backup to choose a backup.")

    state = service.restore(stack_name, selected)
    payload = build_response(
        status="ok",
        message=f"Restored {stack_name} from {selected}",
        data={"stack_name": stack_name, "schema_version": state.schema_version, "source": str(selected)},
    )
    if output_format == OutputFormat.TEXT:
        console.print(
            f"Restored [bold]{stack_name}[/bold] (schema v{state.schema_version}) from {selected}",
            verbosity="result",
        )
        return
    emit_result(payload, output_format)


__all__ = ["restore"]
