"""Progress utilities for interactive flows."""

from __future__ import annotations

from collections.abc import Iterable
from contextlib import contextmanager

from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from geusemaker.cli import console
from geusemaker.cli.components.theme import THEME, is_tty


@contextmanager
def spinner(message: str):
    """Display a spinner while a task runs."""
    if not is_tty():
        console.print(f"{message} ...")
        yield
        console.print(f"Done: {message}")
        return
    with console.status(f"[{THEME.primary}]{message}[/]", spinner="dots"):
        yield


class ProgressTracker:
    """Lightweight wrapper around Rich progress with graceful fallback."""

    def __init__(self, steps: Iterable[str] | None = None):
        self._steps = list(steps or [])
        self._progress: Progress | None = None
        self._task_id: int | None = None
        self._completed = 0

    def __enter__(self):
        if is_tty():
            self._progress = Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("{task.completed}/{task.total}"),
                TimeElapsedColumn(),
                console=console,
                expand=True,
            )
            self._progress.__enter__()
            total = len(self._steps) if self._steps else 1
            self._task_id = self._progress.add_task("Preparing", total=total)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._progress:
            self._progress.__exit__(exc_type, exc, tb)
        if not is_tty() and exc:
            console.print(f"Error: {exc}")
        return False

    def advance(self, description: str | None = None) -> None:
        """Advance to the next step with an optional description."""
        self._completed += 1
        if self._progress and self._task_id is not None:
            if description:
                self._progress.update(self._task_id, description=description)
            self._progress.advance(self._task_id)
        else:
            label = f"{self._completed}/{max(1, len(self._steps))}"
            console.print(f"{label} - {description or 'progress'}")

    def start_step(self, description: str) -> None:
        """Update the progress description without advancing."""
        if self._progress and self._task_id is not None:
            self._progress.update(self._task_id, description=description)
        else:
            console.print(description)


__all__ = ["spinner", "ProgressTracker"]
