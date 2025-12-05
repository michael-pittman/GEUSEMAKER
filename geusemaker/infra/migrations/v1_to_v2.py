"""Migration from schema version 1 to 2."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from geusemaker.infra.migrations.base import Migration


class V1ToV2Migration(Migration):
    """Ensure schema_version exists and add migration history container."""

    name = "v1_to_v2_add_schema_version"
    from_version = 1
    to_version = 2

    def up(self, state: dict[str, Any]) -> dict[str, Any]:
        migrated = deepcopy(state)
        migrated.setdefault("schema_version", self.from_version)
        history = migrated.get("migration_history") or []
        history.append(self.name)
        migrated["migration_history"] = history
        migrated.setdefault("resource_provenance", {})
        return migrated

    def down(self, state: dict[str, Any]) -> dict[str, Any]:
        migrated = deepcopy(state)
        migrated["schema_version"] = self.from_version
        history = migrated.get("migration_history") or []
        if history and history[-1] == self.name:
            history = history[:-1]
        migrated["migration_history"] = history
        return migrated


__all__ = ["V1ToV2Migration"]
