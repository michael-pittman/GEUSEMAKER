"""State management for deployments stored as JSON files."""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from filelock import FileLock
from pydantic import ValidationError

from geusemaker.infra.migrations import MigrationRunner
from geusemaker.infra.migrations.runner import MigrationError, MigrationResult
from geusemaker.models import STATE_SCHEMA_VERSION, DeploymentState

LOGGER = logging.getLogger(__name__)


class StateError(RuntimeError):
    """Base error for state management."""


class StateValidationError(StateError):
    """State failed schema validation."""


class StateMigrationError(StateError):
    """State migration failed."""


class StateCorruptionError(StateError):
    """State file is unreadable or corrupted."""


DEFAULT_BACKUP_RETENTION = 10


class StateManager:
    """JSON-backed state manager stored under ~/.geusemaker/."""

    def __init__(
        self,
        base_path: Path | None = None,
        backup_retention: int = DEFAULT_BACKUP_RETENTION,
        migration_runner: MigrationRunner | None = None,
        backups_path: Path | None = None,
    ):
        self.base_path = base_path or Path.home() / ".geusemaker"
        self.deployments_path = self.base_path / "deployments"
        self.config_path = self.base_path / "config"
        self.cache_path = self.base_path / "cache"
        self.archive_path = self.base_path / "archive"
        self.backups_path = backups_path or self.base_path / "backups"
        self.backup_retention = backup_retention
        self.migration_runner = migration_runner or MigrationRunner()
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        for path in (
            self.base_path,
            self.deployments_path,
            self.config_path,
            self.cache_path,
            self.archive_path,
            self.backups_path,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def _lock(self, file_path: Path) -> FileLock:
        return FileLock(f"{file_path}.lock", timeout=10)

    def deployment_path(self, stack_name: str) -> Path:
        """Return the path for a deployment state file."""
        return self.deployments_path / f"{stack_name}.json"

    async def save_deployment(self, state: DeploymentState) -> None:
        """Persist deployment state atomically with a pre-write backup."""
        file_path = self.deployment_path(state.stack_name)
        await asyncio.to_thread(self._write_state, file_path, state)

    def _write_state(self, file_path: Path, state: DeploymentState) -> None:
        state.updated_at = datetime.now(UTC)
        state.schema_version = STATE_SCHEMA_VERSION
        tmp_path = file_path.with_suffix(".tmp")
        serialized = state.model_dump_json(indent=2, exclude_none=True)
        with self._lock(file_path):
            self._backup_existing(file_path)
            tmp_path.write_text(serialized)
            tmp_path.replace(file_path)
        LOGGER.info(
            "Saved deployment state",
            extra={"stack_name": state.stack_name, "path": str(file_path)},
        )

    async def load_deployment(self, stack_name: str, recover: bool = True) -> DeploymentState | None:
        """Load a deployment state if it exists, applying migrations and validation."""
        file_path = self.deployment_path(stack_name)
        return await asyncio.to_thread(self._read_state, file_path, recover)

    def _read_state(self, file_path: Path, recover: bool = True) -> DeploymentState | None:
        if not file_path.exists():
            return None

        try:
            with self._lock(file_path):
                data = json.loads(file_path.read_text())
        except json.JSONDecodeError as exc:
            LOGGER.error("Corrupted state file %s: %s", file_path, exc)
            if recover:
                return self._recover_from_backup(file_path.stem)
            raise StateCorruptionError(f"Corrupted state file: {file_path}") from exc

        current_version = self._extract_version(data)
        migration_history: list[MigrationResult] = []
        if current_version != STATE_SCHEMA_VERSION:
            try:
                data, migration_history = self.migration_runner.upgrade(
                    data,
                    current_version,
                    STATE_SCHEMA_VERSION,
                )
            except MigrationError as exc:
                LOGGER.error("Migration failed for %s: %s", file_path, exc)
                if recover:
                    return self._recover_from_backup(file_path.stem)
                raise StateMigrationError(f"Failed to migrate state {file_path}") from exc

        try:
            state = DeploymentState.model_validate(data)
            self.validate_state(state)
        except (ValidationError, StateValidationError) as exc:
            LOGGER.error("State validation failed for %s: %s", file_path, exc)
            if recover:
                return self._recover_from_backup(file_path.stem)
            raise StateValidationError(f"Invalid state file {file_path}") from exc

        if migration_history:
            state.migration_history.extend([result.name for result in migration_history])
            self._write_state(file_path, state)

        return state

    def _extract_version(self, data: dict[str, Any]) -> int:
        raw_version = data.get("schema_version", 1)
        try:
            version = int(raw_version)
        except (TypeError, ValueError):
            return 1
        return version if version > 0 else 1

    async def list_deployments(self) -> list[DeploymentState]:
        """Return all deployments sorted by updated_at desc."""
        states: list[DeploymentState] = []
        for path in self.deployments_path.glob("*.json"):
            try:
                state = await self.load_deployment(path.stem)
            except StateError:
                LOGGER.warning("Skipping invalid state file %s", path)
                continue
            if state:
                states.append(state)
        return sorted(states, key=lambda s: s.updated_at, reverse=True)

    async def query(
        self,
        filters: dict[str, Any] | None = None,
        date_range: tuple[datetime | None, datetime | None] | None = None,
    ) -> list[DeploymentState]:
        """Query deployment states by status, tier, region, and optional date window."""
        filters = filters or {}
        states = await self.list_deployments()
        results: list[DeploymentState] = []
        created_after, created_before = date_range or (None, None)
        for state in states:
            if not self._matches_filters(state, filters, created_after, created_before):
                continue
            results.append(state)
        return results

    def _matches_filters(
        self,
        state: DeploymentState,
        filters: dict[str, Any],
        created_after: datetime | None,
        created_before: datetime | None,
    ) -> bool:
        if "status" in filters and state.status != filters["status"]:
            return False
        if "tier" in filters and state.config.tier != filters["tier"]:
            return False
        if "region" in filters and state.config.region != filters["region"]:
            return False
        if created_after and state.created_at < created_after:
            return False
        if created_before and state.created_at > created_before:
            return False
        return True

    def export_json(self, state: DeploymentState, pretty: bool = True) -> str:
        """Return JSON representation of a state."""
        data = state.model_dump(mode="json", exclude_none=True)
        return json.dumps(data, indent=2 if pretty else None, default=str)

    def export_yaml(self, state: DeploymentState) -> str:
        """Return YAML representation of a state."""
        data = state.model_dump(mode="json", exclude_none=True)
        return yaml.safe_dump(data, sort_keys=False)

    def export_to_file(self, state: DeploymentState, destination: Path) -> Path:
        """Export a state to a file (JSON or YAML inferred by suffix)."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.suffix.lower() in {".yaml", ".yml"}:
            destination.write_text(self.export_yaml(state))
        else:
            destination.write_text(self.export_json(state))
        return destination

    async def delete_deployment(self, stack_name: str) -> bool:
        """Delete a deployment state file."""
        file_path = self.deployment_path(stack_name)
        return await asyncio.to_thread(self._delete_file, file_path)

    def _delete_file(self, file_path: Path) -> bool:
        if not file_path.exists():
            return False
        with self._lock(file_path):
            file_path.unlink()
            lock_path = Path(f"{file_path}.lock")
            if lock_path.exists():
                lock_path.unlink()
        return True

    async def archive_deployment(self, state: DeploymentState) -> Path:
        """Write a deployment state snapshot to the archive directory."""
        timestamp = int(state.updated_at.timestamp())
        archive_file = self.archive_path / f"{state.stack_name}-{timestamp}.json"
        await asyncio.to_thread(self._write_state, archive_file, state)
        return archive_file

    def backup_state(self, stack_name: str, label: str | None = None) -> Path:
        """Create a compressed backup for the specified deployment."""
        file_path = self.deployment_path(stack_name)
        if not file_path.exists():
            raise FileNotFoundError(f"No state found for stack {stack_name}")
        with self._lock(file_path):
            backup = self._write_backup(file_path, label=label)
        return backup

    def list_backups(self, stack_name: str | None = None) -> list[Path]:
        """List available backups, newest first."""
        base = self.backups_path if stack_name is None else self.backups_path / stack_name
        if not base.exists():
            return []
        backups = sorted(base.glob("*.json.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
        return backups

    def restore_from_backup(self, stack_name: str, backup_path: Path) -> DeploymentState:
        """Restore a state file from a backup archive."""
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup not found: {backup_path}")
        target = self.deployment_path(stack_name)
        if target.exists():
            self._backup_existing(target)

        with gzip.open(backup_path, "rb") as handle:
            data = json.loads(handle.read().decode())

        current_version = self._extract_version(data)
        migrations: list[MigrationResult] = []
        if current_version != STATE_SCHEMA_VERSION:
            data, migrations = self.migration_runner.upgrade(data, current_version, STATE_SCHEMA_VERSION)

        state = DeploymentState.model_validate(data)
        state.migration_history.extend([m.name for m in migrations])
        self.validate_state(state)
        self._write_state(target, state)
        return state

    def validate_state(self, state: DeploymentState) -> None:
        """Run custom integrity checks beyond Pydantic validation."""
        required_fields: list[tuple[str, bool]] = [
            ("stack_name", bool(state.stack_name)),
            ("vpc_id", bool(state.vpc_id)),
            ("subnet_ids", bool(state.subnet_ids)),
            ("security_group_id", bool(state.security_group_id)),
            ("efs_id", bool(state.efs_id)),
        ]

        # Allow missing instance_id when an abort happens before the instance is created.
        requires_instance_id = not (
            state.status == "creating" and state.resource_provenance.get("instance") == "pending"
        )
        if requires_instance_id:
            required_fields.append(("instance_id", bool(state.instance_id)))

        failures = [name for name, ok in required_fields if not ok]
        if failures:
            raise StateValidationError(f"Missing required fields: {', '.join(failures)}")

    def _backup_existing(self, file_path: Path) -> Path | None:
        if not file_path.exists():
            return None
        return self._write_backup(file_path)

    def _write_backup(self, file_path: Path, label: str | None = None) -> Path:
        stack_name = file_path.stem
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        label_suffix = f"-{label}" if label else ""
        target_dir = self.backups_path / stack_name
        target_dir.mkdir(parents=True, exist_ok=True)
        backup_path = target_dir / f"{stack_name}{label_suffix}-{timestamp}.json.gz"
        counter = 1
        while backup_path.exists():
            backup_path = target_dir / f"{stack_name}{label_suffix}-{timestamp}-{counter}.json.gz"
            counter += 1
        with file_path.open("rb") as source, gzip.open(backup_path, "wb") as dest:
            dest.write(source.read())
        self._enforce_retention(target_dir)
        LOGGER.info("Created backup for %s at %s", stack_name, backup_path)
        return backup_path

    def _enforce_retention(self, backup_dir: Path) -> None:
        if self.backup_retention <= 0:
            return
        backups = sorted(backup_dir.glob("*.json.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in backups[self.backup_retention :]:
            path.unlink(missing_ok=True)

    def _recover_from_backup(self, stack_name: str) -> DeploymentState | None:
        """Attempt to recover the latest backup."""
        backups = self.list_backups(stack_name)
        if not backups:
            LOGGER.error("No backups available for stack %s", stack_name)
            return None
        latest = backups[0]
        LOGGER.warning("Recovering deployment %s from backup %s", stack_name, latest)
        return self.restore_from_backup(stack_name, latest)


__all__ = [
    "StateManager",
    "StateError",
    "StateValidationError",
    "StateMigrationError",
    "StateCorruptionError",
    "DEFAULT_BACKUP_RETENTION",
]
