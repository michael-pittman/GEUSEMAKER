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

# When machine output is active (--output json|yaml), stdout is reserved for exactly
# one structured document; all human-facing output is diverted to stderr.
_machine_output: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "geusemaker_machine_output",
    default=False,
)

_stderr_console: Console | None = None


def _get_stderr_console() -> Console:
    global _stderr_console
    if _stderr_console is None:
        _stderr_console = Console(stderr=True)
    return _stderr_console


class VerbosityConsole(Console):
    """Console that honours verbosity levels and supports error-only output.

    Contracts:
    - ``--silent``: errors only.
    - machine output (``--output json|yaml``): stdout carries only the structured
      document (emitted separately via ``emit_result``); everything printed through
      this console goes to stderr.
    - normal mode: progress and presentation on stdout.
    """

    def print(self, *args, **kwargs):  # type: ignore[override]
        level: str = kwargs.pop("verbosity", "info")
        current = _verbosity.get()
        if current == VerbosityLevel.SILENT and level != "error":
            if not any(_looks_like_error(arg) for arg in args):
                return
        if current == VerbosityLevel.NORMAL and level == "debug":
            return
        if _machine_output.get():
            _get_stderr_console().print(*args, **kwargs)
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


def set_machine_output(enabled: bool) -> None:
    """Reserve stdout for a single structured document (json/yaml output modes)."""
    _machine_output.set(enabled)


def is_machine_output() -> bool:
    """Return True when machine-readable output mode is active."""
    return _machine_output.get()


__all__ = [
    "VerbosityLevel",
    "VerbosityConsole",
    "set_verbosity",
    "get_verbosity",
    "is_silent",
    "set_machine_output",
    "is_machine_output",
]
