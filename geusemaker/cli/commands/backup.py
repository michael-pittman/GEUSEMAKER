"""Backup command group."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import click
from rich.table import Table

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


@click.group("backup")
def backup_group() -> None:
    """Manage deployment state backups."""


@backup_group.command("create")
@click.argument("stack_name")
@click.option("--label", "-n", help="Optional label to append to the backup filename.")
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
def create_backup(
    stack_name: str,
    label: str | None,
    state_dir: str | None,
    backup_dir: str | None,
    output: str,
) -> None:
    """Create a manual backup for STACK_NAME."""
    output_format = OutputFormat(output.lower())
    service = BackupService(_manager(state_dir, backup_dir))
    path = service.create(stack_name, label=label)
    payload = build_response(
        status="ok",
        message=f"Created backup for {stack_name} at {path}",
        data={"stack_name": stack_name, "path": str(path)},
    )
    if output_format == OutputFormat.TEXT:
        console.print(f"Created backup for [bold]{stack_name}[/bold] at {path}", verbosity="result")
        return
    emit_result(payload, output_format)


@backup_group.command("list")
@click.argument("stack_name", required=False)
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
def list_backups(stack_name: str | None, state_dir: str | None, backup_dir: str | None, output: str) -> None:
    """List backups for STACK_NAME or all deployments."""
    service = BackupService(_manager(state_dir, backup_dir))
    backups = service.list(stack_name)
    output_format = OutputFormat(output.lower())
    if not backups:
        if output_format == OutputFormat.TEXT:
            console.print("No backups found.", verbosity="info")
        else:
            emit_result(
                build_response(status="ok", message="No backups found.", data=[]),
                output_format,
            )
        return

    payload = [
        {
            "stack_name": info.stack_name,
            "path": str(info.path),
            "size_bytes": info.size_bytes,
            "schema_version": info.schema_version,
            "created_at": info.created_at,
        }
        for info in backups
    ]
    if output_format == OutputFormat.TEXT:
        table = Table(title="Deployment Backups")
        table.add_column("Stack")
        table.add_column("Path")
        table.add_column("Version", justify="right")
        table.add_column("Size (bytes)", justify="right")
        table.add_column("Created", justify="right")
        for info in backups:
            table.add_row(
                info.stack_name,
                str(info.path),
                str(info.schema_version),
                str(info.size_bytes),
                datetime.fromtimestamp(info.created_at).isoformat(),
            )
        console.print(table, verbosity="result")
        return

    emit_result(build_response(data=payload, status="ok"), output_format)


__all__ = ["backup_group"]
