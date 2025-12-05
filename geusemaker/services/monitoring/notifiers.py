"""Notification helpers for health monitoring."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Protocol

from rich.console import Console
from rich.panel import Panel

from geusemaker.models.monitoring import HealthEvent

LOGGER = logging.getLogger(__name__)


class Notifier(Protocol):
    """Protocol for sending notifications."""

    def notify(self, event: HealthEvent) -> None: ...


class ConsoleNotifier:
    """Console notifier (logs)."""

    def __init__(self, console: Console | None = None, ring_bell: bool = True):
        self.console = console or Console()
        self.ring_bell = ring_bell

    def notify(self, event: HealthEvent) -> None:
        style = "green"
        if event.event_type == "alert":
            style = "red"
        elif event.event_type == "status_change":
            style = "yellow"

        message = (
            f"[{style}]{event.event_type.upper()}[/] "
            f"{event.service_name}: {event.previous_status or '-'} -> {event.new_status}"
        )
        detail = f" ({event.details})" if event.details else ""
        self.console.log(message + detail)
        if self.ring_bell and event.event_type == "alert":
            try:
                self.console.bell()
            except Exception as exc:  # noqa: BLE001
                LOGGER.debug("Console bell failed: %s", exc)


class RichAlertNotifier:
    """Rich panel-based notifier for prominent alerts."""

    def __init__(self, console: Console | None = None):
        self.console = console or Console()

    def notify(self, event: HealthEvent) -> None:
        if event.event_type != "alert":
            return
        title = f"🚨 {event.service_name} ALERT"
        details = event.details or f"{event.previous_status or '-'} -> {event.new_status}"
        panel = Panel(
            details,
            title=title,
            border_style="red",
            padding=(1, 2),
        )
        self.console.print(panel)


class LogNotifier:
    """File-based notifier for health events."""

    def __init__(self, log_path: Path, level: str = "info", max_bytes: int = 1_000_000):
        self.log_path = log_path
        self.level = level
        self.max_bytes = max_bytes
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def notify(self, event: HealthEvent) -> None:
        payload = event.model_dump()
        payload["level"] = self.level
        line = json.dumps(payload, default=str)
        self._rotate_if_needed()
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def _rotate_if_needed(self) -> None:
        if self.log_path.exists() and self.log_path.stat().st_size > self.max_bytes:
            rotated = self.log_path.with_suffix(".log.1")
            self.log_path.replace(rotated)


__all__ = ["Notifier", "ConsoleNotifier", "RichAlertNotifier", "LogNotifier"]
