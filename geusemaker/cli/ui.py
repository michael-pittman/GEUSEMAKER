"""Shared Rich UI helpers."""

from rich.console import Console
from rich.panel import Panel

from geusemaker.cli.branding import COMPACT_BANNER

console = Console()


def print_banner() -> None:
    """Print a compact banner for commands that need lightweight output."""
    console.print(Panel(COMPACT_BANNER, expand=False))


__all__ = ["console", "print_banner"]
