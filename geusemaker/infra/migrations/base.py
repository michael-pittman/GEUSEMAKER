"""Base migration contract."""

from __future__ import annotations

from typing import Any


class Migration:
    """Base migration contract."""

    name: str
    from_version: int
    to_version: int

    def up(self, state: dict[str, Any]) -> dict[str, Any]:  # pragma: no cover - interface
        raise NotImplementedError

    def down(self, state: dict[str, Any]) -> dict[str, Any]:  # pragma: no cover - interface
        raise NotImplementedError


__all__ = ["Migration"]
