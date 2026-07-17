"""Animated boot splash for the operations hub."""

from __future__ import annotations

from textual import events
from textual.app import ComposeResult
from textual.containers import Center, Vertical
from textual.screen import Screen
from textual.widgets import Static

from geusemaker.cli.branding import MAIN_BANNER

BANNER_LINES = [line for line in MAIN_BANNER.splitlines() if line.strip()]
SWEEP_WIDTH = max(len(line) for line in BANNER_LINES)

BOOT_LINES = [
    "[dim]▸ LOADING OPERATIONS HUB[/dim]",
    "[dim]▸ THEME · BRUTALIST[/dim]",
    "[dim]▸ AWS CONTACT · ON REQUEST ONLY[/dim]",
    "[bold #c8f542]▸ READY — PRESS ANY KEY[/bold #c8f542]",
]

LINE_STAGGER = 0.08
BOOT_START = 0.7
BOOT_STAGGER = 0.22
AUTO_DISMISS = 2.6


class SplashScreen(Screen[None]):
    """Staggered banner reveal + boot log. Any key (or a click) skips it."""

    def __init__(self) -> None:
        super().__init__()
        self._finished = False
        self._sweep_progress = 0

    def compose(self) -> ComposeResult:
        with Center(id="splash-center"):
            with Vertical(id="splash-body"):
                for index, line in enumerate(BANNER_LINES):
                    yield Static(line, classes="splash-banner-line", id=f"splash-line-{index}")
                yield Static("", id="splash-sweep")
                yield Static("AI INFRASTRUCTURE CONTROL", id="splash-tagline")
                for index, line in enumerate(BOOT_LINES):
                    yield Static(line, classes="splash-boot-line", id=f"splash-boot-{index}")

    def on_mount(self) -> None:
        for index in range(len(BANNER_LINES)):
            widget = self.query_one(f"#splash-line-{index}", Static)
            widget.styles.animate("opacity", value=1.0, duration=0.35, delay=LINE_STAGGER * index, easing="out_cubic")
        tagline = self.query_one("#splash-tagline", Static)
        tagline.styles.animate("opacity", value=1.0, duration=0.4, delay=BOOT_START, easing="out_cubic")
        for index in range(len(BOOT_LINES)):
            widget = self.query_one(f"#splash-boot-{index}", Static)
            widget.styles.animate(
                "opacity",
                value=1.0,
                duration=0.3,
                delay=BOOT_START + BOOT_STAGGER * (index + 1),
                easing="out_cubic",
            )
        self._sweep_timer = self.set_interval(0.03, self._advance_sweep)
        self.set_timer(AUTO_DISMISS, self._finish)

    def _advance_sweep(self) -> None:
        self._sweep_progress = min(self._sweep_progress + 2, SWEEP_WIDTH)
        bar = "━" * self._sweep_progress
        self.query_one("#splash-sweep", Static).update(f"[bold #c8f542]{bar}[/bold #c8f542]")
        if self._sweep_progress >= SWEEP_WIDTH:
            self._sweep_timer.stop()

    def _finish(self) -> None:
        if self._finished:
            return
        self._finished = True
        self.dismiss(None)

    def on_key(self, event: events.Key) -> None:
        event.stop()
        self._finish()

    def on_click(self, event: events.Click) -> None:
        event.stop()
        self._finish()


__all__ = ["SplashScreen"]
