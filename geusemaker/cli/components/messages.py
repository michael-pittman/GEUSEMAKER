"""Styled message helpers for interactive output."""

from __future__ import annotations

from rich.panel import Panel
from rich.text import Text

from geusemaker.cli import console
from geusemaker.cli.branding import EMOJI
from geusemaker.cli.components.theme import THEME, is_tty


def success(message: str) -> None:
    """Render a success message."""
    _render(message, THEME.success, EMOJI["check"], title="Success", severity="info")


def warning(message: str) -> None:
    """Render a warning message."""
    _render(message, THEME.warning, EMOJI["warning"], title="Warning", severity="warning")


def error(message: str) -> None:
    """Render an error message."""
    _render(message, THEME.error, EMOJI["error"], title="Error", severity="error")


def info(message: str, title: str | None = None) -> None:
    """Render an informational message."""
    _render(message, THEME.info, EMOJI["info"], title=title, severity="info")


def _render(message: str, style: str, icon: str, title: str | None, severity: str) -> None:
    prefix = f"{icon} {message}"
    if not is_tty():
        console.print(prefix, verbosity=severity)
        return
    text = Text(prefix, style=style)
    console.print(Panel(text, border_style=style, title=title), verbosity=severity)


__all__ = ["success", "warning", "error", "info"]
