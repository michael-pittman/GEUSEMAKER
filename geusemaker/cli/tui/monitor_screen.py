"""Live health monitor screen for the operations hub.

First AWS/network-touching TUI screen. A single async polling worker loads the
deployment state from disk, resolves the target host exactly like the CLI
monitor command (public IP, falling back to private IP), and polls all service
health endpoints on an interval. The worker is bound to this screen, so
Textual cancels it automatically when the screen is dismissed or removed.

SSM/userdata log streaming is intentionally NOT implemented here (later
phase); ``#monitor-log-slot`` reserves the layout position for it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

import httpx
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import DataTable, RichLog, Static

from geusemaker.cli.tui.theme import GM_FAULT, GM_SIGNAL, GM_VARIABLES_TCSS, GM_WARN
from geusemaker.infra.state import StateError, StateManager
from geusemaker.models.health import HealthCheckResult
from geusemaker.services.health.client import HealthCheckClient
from geusemaker.services.health.services import check_all_services, check_postgres

#: Dependency-injection seam: async callable taking the target host and
#: returning one HealthCheckResult per service. Tests inject fakes here so no
#: network is ever touched; the default is `default_health_checker` below.
HealthChecker = Callable[[str], Awaitable[list[HealthCheckResult]]]

EVENT_LOG_MAX_LINES = 2000

_OK_MARK = f"[bold {GM_SIGNAL}][OK][/bold {GM_SIGNAL}]"
_WAIT_MARK = f"[bold {GM_WARN}][WAIT][/bold {GM_WARN}]"
_ERROR_MARK = f"[bold {GM_FAULT}][ERROR][/bold {GM_FAULT}]"


async def default_health_checker(host: str) -> list[HealthCheckResult]:
    """Check every stack service: HTTP via NGINX routes plus PostgreSQL TCP.

    verify=False mirrors HealthCheckClient's default: Tier 1 NGINX redirects
    port 80 to HTTPS with a self-signed certificate; these probes only report
    reachability, not sensitive data.
    """
    async with httpx.AsyncClient(follow_redirects=True, verify=False) as http_client:  # noqa: S501
        client = HealthCheckClient(client=http_client)
        results = await check_all_services(client, host)
        results.append(await check_postgres(client, host))
    return results


class MonitorScreen(Screen[None]):
    """Per-service health table + event stream driven by a polling worker."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "dismiss_screen", "BACK"),
    ]

    # $gm-* tokens come from theme.GM_VARIABLES_TCSS (DEFAULT_CSS cannot see
    # app-stylesheet variables in Textual 8.2.8).
    DEFAULT_CSS = (
        GM_VARIABLES_TCSS
        + """
    MonitorScreen {
        background: $gm-surface;
        color: $gm-ink;
    }
    #monitor-root {
        padding: 1 2;
    }
    #monitor-title {
        height: 3;
        padding: 0 1;
        border: heavy $gm-signal;
        color: $gm-signal;
        text-style: bold;
    }
    #monitor-status {
        height: 3;
        margin-top: 1;
        padding: 0 1;
        border: heavy $gm-rule;
        color: $gm-ink;
    }
    #monitor-table {
        height: auto;
        max-height: 12;
        margin-top: 1;
        border: heavy $gm-rule;
        background: $gm-panel;
    }
    #monitor-last-poll {
        height: 1;
        padding: 0 1;
        color: $gm-muted;
    }
    #monitor-events {
        height: 1fr;
        min-height: 5;
        margin-top: 1;
        padding: 0 1;
        border: heavy $gm-rule;
        background: $gm-panel;
        color: $gm-ink;
    }
    #monitor-log-slot {
        height: 3;
        margin-top: 1;
        padding: 0 1;
        border: heavy $gm-rule;
        color: $gm-muted;
    }
    """
    )

    def __init__(
        self,
        *,
        stack_name: str,
        state_dir: Path | None = None,
        poll_interval: float = 5.0,
        health_checker: HealthChecker | None = None,
    ) -> None:
        super().__init__()
        self.stack_name = stack_name
        self.state_dir = state_dir
        self.poll_interval = poll_interval
        self._health_checker: HealthChecker = health_checker or default_health_checker
        self._host: str | None = None
        self._poll_count = 0
        self._last_statuses: dict[str, bool] = {}

    def compose(self) -> ComposeResult:
        with Vertical(id="monitor-root"):
            yield Static(f"MONITOR · STACK {self.stack_name.upper()}", id="monitor-title")
            yield Static(f"{_WAIT_MARK} FIRST POLL…", id="monitor-status")
            yield DataTable(id="monitor-table")
            yield Static("LAST POLL · —", id="monitor-last-poll")
            yield RichLog(
                id="monitor-events",
                auto_scroll=True,
                max_lines=EVENT_LOG_MAX_LINES,
                markup=True,
                highlight=False,
            )
            yield Static(
                "[dim]LOG STREAM SLOT · SSM USERDATA / CONTAINER TAIL LANDS IN A LATER PHASE[/dim]",
                id="monitor-log-slot",
            )

    def on_mount(self) -> None:
        table = self.query_one("#monitor-table", DataTable)
        table.cursor_type = "none"
        table.add_columns("SERVICE", "STATUS", "LATENCY MS", "DETAIL")
        events = self.query_one("#monitor-events", RichLog)
        events.write(f"{_WAIT_MARK} FIRST POLL… LOADING STATE FOR '{self.stack_name}'")
        self._run_monitor()

    def action_dismiss_screen(self) -> None:
        self.dismiss(None)

    @work(exclusive=True)
    async def _run_monitor(self) -> None:
        """Load state, resolve the target host, then poll health forever.

        Bound to this screen: Textual cancels the worker when the screen is
        dismissed/unmounted, so the loop never outlives the pane.
        """
        try:
            manager = await asyncio.to_thread(StateManager, self.state_dir)
            state = await manager.load_deployment(self.stack_name)
        except StateError as exc:
            self._show_fatal(f"STATE LOAD FAILED · {exc}")
            return
        if state is None:
            self._show_fatal(f"NO DEPLOYMENT STATE FOUND FOR '{self.stack_name}'")
            return
        # Same resolution as the CLI monitor command (_load_host).
        host = state.public_ip or state.private_ip
        if not host:
            self._show_fatal(f"UNRESOLVABLE HOST FOR '{self.stack_name}' · STATE HAS NO PUBLIC OR PRIVATE IP")
            return
        self._host = host
        self.query_one("#monitor-status", Static).update(
            f"{_WAIT_MARK} TARGET {host} · INTERVAL {self.poll_interval:g}S · AWAITING FIRST POLL",
        )
        self.query_one("#monitor-events", RichLog).write(
            f"{_OK_MARK} TARGET HOST {host} · POLLING EVERY {self.poll_interval:g}S",
        )
        while True:
            try:
                results = await self._health_checker(host)
            except (httpx.HTTPError, OSError, RuntimeError) as exc:
                self._poll_count += 1
                self.query_one("#monitor-events", RichLog).write(
                    f"{_ERROR_MARK} POLL {self._poll_count} FAILED · {exc}",
                )
            else:
                self._poll_count += 1
                self._apply_results(results)
            await asyncio.sleep(self.poll_interval)

    def _apply_results(self, results: list[HealthCheckResult]) -> None:
        """Refresh the status table, timestamp line, and event stream."""
        table = self.query_one("#monitor-table", DataTable)
        events = self.query_one("#monitor-events", RichLog)
        stamp = datetime.now(UTC).strftime("%H:%M:%S")
        table.clear()
        healthy_count = 0
        for result in results:
            name = result.service_name
            detail = self._describe(result)
            if result.healthy:
                healthy_count += 1
                status_cell = Text("OK", style=f"bold {GM_SIGNAL}")
            else:
                status_cell = Text("FAIL", style=f"bold {GM_FAULT}")
            table.add_row(
                Text(name.upper()),
                status_cell,
                Text(f"{result.response_time_ms:.0f}", justify="right"),
                Text(detail),
                key=name,
            )
            previous = self._last_statuses.get(name)
            if previous is not None and previous != result.healthy:
                if result.healthy:
                    events.write(f"{_OK_MARK} {name.upper()} RECOVERED")
                else:
                    events.write(f"{_ERROR_MARK} {name.upper()} WENT DOWN")
            if not result.healthy:
                events.write(f"{_ERROR_MARK} {name.upper()} UNHEALTHY · {detail}")
            self._last_statuses[name] = result.healthy
        self.query_one("#monitor-status", Static).update(
            f"{_OK_MARK} TARGET {self._host} · {healthy_count}/{len(results)} SERVICES HEALTHY",
        )
        self.query_one("#monitor-last-poll", Static).update(
            f"LAST POLL · {stamp} UTC · CYCLE {self._poll_count}",
        )
        events.write(f"[dim][POLL {self._poll_count}][/dim] {stamp} · {healthy_count}/{len(results)} OK")

    def _show_fatal(self, message: str) -> None:
        """Render an explicit error state — never a silent dead pane."""
        self.query_one("#monitor-status", Static).update(f"{_ERROR_MARK} {message}")
        self.query_one("#monitor-events", RichLog).write(f"{_ERROR_MARK} {message}")

    @staticmethod
    def _describe(result: HealthCheckResult) -> str:
        if result.healthy:
            return f"HTTP {result.status_code}" if result.status_code is not None else "TCP OPEN"
        if result.error_message:
            return result.error_message
        if result.status_code is not None:
            return f"HTTP {result.status_code}"
        return "NO RESPONSE"


__all__ = ["MonitorScreen", "HealthChecker", "default_health_checker", "EVENT_LOG_MAX_LINES"]
