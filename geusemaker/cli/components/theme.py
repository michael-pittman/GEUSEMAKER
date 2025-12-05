"""Shared color and style theme for interactive CLI components."""

from __future__ import annotations

from dataclasses import dataclass

from geusemaker.cli import console


@dataclass(frozen=True)
class ColorTheme:
    """Palette used across interactive components."""

    primary: str = "cyan"
    accent: str = "magenta"
    success: str = "green"
    warning: str = "yellow"
    error: str = "red"
    info: str = "blue"
    muted: str = "grey70"
    border: str = "grey58"


THEME = ColorTheme()


def is_tty() -> bool:
    """Return True when output is attached to a TTY."""
    return bool(getattr(console, "is_terminal", True))


__all__ = ["ColorTheme", "THEME", "is_tty"]
