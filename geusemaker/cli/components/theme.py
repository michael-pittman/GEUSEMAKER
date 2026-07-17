"""Shared color and style theme for interactive CLI components."""

from __future__ import annotations

from dataclasses import dataclass

from rich.theme import Theme

from geusemaker.cli import console


@dataclass(frozen=True)
class ColorTheme:
    """Palette used across interactive components."""

    surface: str = "#0a0c0f"
    panel: str = "#12151a"
    ink: str = "#e8ecef"
    muted: str = "#6b7280"
    signal: str = "#c8f542"
    warning: str = "#f5a524"
    error: str = "#ff4d4d"
    border: str = "#2a3038"
    primary: str = "#c8f542"
    accent: str = "#e8ecef"
    success: str = "#c8f542"
    info: str = "#e8ecef"


THEME = ColorTheme()


def rich_theme(palette: ColorTheme = THEME) -> Theme:
    """Return semantic styles shared by both terminal shells."""
    return Theme(
        {
            "gm.ink": palette.ink,
            "gm.muted": palette.muted,
            "gm.signal": f"bold {palette.signal}",
            "gm.warning": palette.warning,
            "gm.error": f"bold {palette.error}",
            "gm.rule": palette.border,
            "gm.step": f"bold {palette.ink} on {palette.panel}",
        }
    )


def is_tty() -> bool:
    """Return True when output is attached to a TTY."""
    return bool(getattr(console, "is_terminal", True))


__all__ = ["ColorTheme", "THEME", "rich_theme", "is_tty"]
