"""Simple migration runner for deployment state files."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from geusemaker.infra.migrations.base import Migration
from geusemaker.infra.migrations.v1_to_v2 import V1ToV2Migration


class MigrationError(RuntimeError):
    """Raised when a migration cannot be applied."""


@dataclass(frozen=True)
class MigrationResult:
    """Result of a migration step."""

    name: str
    from_version: int
    to_version: int


DEFAULT_MIGRATIONS: tuple[Migration, ...] = (V1ToV2Migration(),)


class MigrationRunner:
    """Apply migrations to deployment state dictionaries."""

    def __init__(self, migrations: Iterable[Migration] | None = None):
        self._migrations: tuple[Migration, ...] = tuple(
            sorted(migrations or DEFAULT_MIGRATIONS, key=lambda m: m.from_version),
        )

    def upgrade(
        self,
        state: dict[str, Any],
        current_version: int,
        target_version: int,
    ) -> tuple[dict[str, Any], list[MigrationResult]]:
        """Apply migrations until reaching the target version."""
        if current_version > target_version:
            raise MigrationError(f"State version {current_version} is newer than supported {target_version}")

        version = current_version
        history: list[MigrationResult] = []
        migrated = dict(state)

        while version < target_version:
            migration = self._find_migration(version)
            if not migration:
                raise MigrationError(f"No migration found from version {version} to reach {target_version}")

            migrated = migration.up(migrated)
            version = migration.to_version
            history.append(MigrationResult(migration.name, migration.from_version, migration.to_version))

        migrated["schema_version"] = version
        return migrated, history

    def downgrade(
        self,
        state: dict[str, Any],
        current_version: int,
        target_version: int,
    ) -> tuple[dict[str, Any], list[MigrationResult]]:
        """Downgrade state to the target version (best-effort, used for tests/backups)."""
        if current_version < target_version:
            raise MigrationError(f"Cannot downgrade from {current_version} to newer version {target_version}")

        version = current_version
        history: list[MigrationResult] = []
        migrated = dict(state)

        while version > target_version:
            migration = self._find_reverse_migration(version)
            if not migration:
                raise MigrationError(f"No reverse migration found from version {version} to reach {target_version}")
            migrated = migration.down(migrated)
            version = migration.from_version
            history.append(MigrationResult(migration.name, migration.to_version, migration.from_version))

        migrated["schema_version"] = version
        return migrated, history

    def _find_migration(self, from_version: int) -> Migration | None:
        for migration in self._migrations:
            if migration.from_version == from_version:
                return migration
        return None

    def _find_reverse_migration(self, to_version: int) -> Migration | None:
        for migration in reversed(self._migrations):
            if migration.to_version == to_version:
                return migration
        return None


__all__ = ["MigrationRunner", "MigrationError", "MigrationResult", "Migration"]
