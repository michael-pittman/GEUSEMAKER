"""Backup and restore helpers built on top of the StateManager."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from geusemaker.infra.state import StateManager
from geusemaker.models import DeploymentState


@dataclass(frozen=True)
class BackupInfo:
    """Metadata about a stored backup."""

    stack_name: str
    path: Path
    size_bytes: int
    schema_version: int
    created_at: float


class BackupService:
    """High-level backup/restore operations."""

    def __init__(self, state_manager: StateManager | None = None):
        self.state_manager = state_manager or StateManager()

    def create(self, stack_name: str, label: str | None = None) -> Path:
        """Create a manual backup for the deployment."""
        return self.state_manager.backup_state(stack_name, label=label)

    def list(self, stack_name: str | None = None) -> list[BackupInfo]:
        """Return sorted backup metadata."""
        backups = self.state_manager.list_backups(stack_name)
        return [self._inspect_backup(path) for path in backups]

    def restore(self, stack_name: str, backup_path: Path) -> DeploymentState:
        """Restore a deployment from a specific backup."""
        return self.state_manager.restore_from_backup(stack_name, backup_path)

    def _inspect_backup(self, path: Path) -> BackupInfo:
        raw = path.read_bytes()
        import gzip
        import json

        with gzip.open(path, "rb") as handle:
            data = json.loads(handle.read().decode())
        schema_version = int(data.get("schema_version", 1))
        stack_name = data.get("stack_name", path.stem.split("-")[0])
        return BackupInfo(
            stack_name=stack_name,
            path=path,
            size_bytes=len(raw),
            schema_version=schema_version,
            created_at=path.stat().st_mtime,
        )

    async def restore_latest(self, stack_name: str) -> DeploymentState:
        """Restore using the latest backup for a stack."""
        backups = self.state_manager.list_backups(stack_name)
        if not backups:
            raise FileNotFoundError(f"No backups found for {stack_name}")
        return await asyncio.to_thread(self.restore, stack_name, backups[0])


__all__ = ["BackupService", "BackupInfo"]
