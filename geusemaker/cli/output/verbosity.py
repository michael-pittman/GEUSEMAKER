"""Verbosity-aware console output."""

from __future__ import annotations

import contextvars
from enum import Enum

from rich.console import Console


class VerbosityLevel(str, Enum):
    """Verbosity levels for CLI output."""

    SILENT = "silent"
    NORMAL = "normal"
    VERBOSE = "verbose"


_verbosity: contextvars.ContextVar[VerbosityLevel] = contextvars.ContextVar(
    "geusemaker_verbosity",
    default=VerbosityLevel.NORMAL,
)


class VerbosityConsole(Console):
    """Console that honours verbosity levels and supports error-only output."""

    def print(self, *args, **kwargs):  # type: ignore[override]
        level: str = kwargs.pop("verbosity", "info")
        current = _verbosity.get()
        if current == VerbosityLevel.SILENT and level not in {"error", "result"}:
            if not any(_looks_like_error(arg) for arg in args):
                return
        if current == VerbosityLevel.NORMAL and level == "debug":
            return
        super().print(*args, **kwargs)


def _looks_like_error(arg: object) -> bool:
    if isinstance(arg, str):
        lowered = arg.lower()
        return "❌" in arg or "[red" in lowered or "error" in lowered
    return False


def set_verbosity(level: VerbosityLevel) -> None:
    """Set the global verbosity level."""
    _verbosity.set(level)


def get_verbosity() -> VerbosityLevel:
    """Return current verbosity."""
    return _verbosity.get()


def is_silent() -> bool:
    """Return True when silent mode is enabled."""
    return _verbosity.get() == VerbosityLevel.SILENT


__all__ = ["VerbosityLevel", "VerbosityConsole", "set_verbosity", "get_verbosity", "is_silent"]
