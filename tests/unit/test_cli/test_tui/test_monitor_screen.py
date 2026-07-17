"""Pilot tests for the TUI monitor screen (no network, no boto3)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

pytest.importorskip("textual")

from textual.app import App  # noqa: E402
from textual.pilot import Pilot  # noqa: E402
from textual.widgets import DataTable, RichLog, Static  # noqa: E402

from geusemaker.cli import tui as tui_pkg  # noqa: E402
from geusemaker.cli.tui.monitor_screen import MonitorScreen  # noqa: E402
from geusemaker.infra.state import StateManager  # noqa: E402
from geusemaker.models import CostTracking, DeploymentConfig, DeploymentState  # noqa: E402
from geusemaker.models.health import HealthCheckResult  # noqa: E402

BRUTALIST_CSS = Path(tui_pkg.__file__).parent / "brutalist.tcss"

SERVICES = ("n8n", "ollama", "qdrant", "crawl4ai", "postgres")

POLL_INTERVAL = 0.05


class MonitorTestApp(App[None]):
    """Minimal host app providing the $gm-* variables the screen CSS uses."""

    CSS_PATH = str(BRUTALIST_CSS)

    def __init__(self, monitor_screen: MonitorScreen) -> None:
        super().__init__()
        self._monitor_screen = monitor_screen

    def on_mount(self) -> None:
        self.push_screen(self._monitor_screen)


class FakeHealthChecker:
    """Records calls and replays scripted results; never touches the network."""

    def __init__(self, scripted: list[list[HealthCheckResult]]) -> None:
        self.calls = 0
        self.hosts: list[str] = []
        self._scripted = scripted

    async def __call__(self, host: str) -> list[HealthCheckResult]:
        self.calls += 1
        self.hosts.append(host)
        index = min(self.calls - 1, len(self._scripted) - 1)
        return [result.model_copy(deep=True) for result in self._scripted[index]]


class BlockedHealthChecker:
    """Never completes a poll, so the screen stays in its WAIT state."""

    def __init__(self) -> None:
        self.calls = 0
        self._gate = asyncio.Event()

    async def __call__(self, host: str) -> list[HealthCheckResult]:
        self.calls += 1
        await self._gate.wait()
        return []


def _result(name: str, *, healthy: bool, error: str | None = None) -> HealthCheckResult:
    return HealthCheckResult(
        service_name=name,
        healthy=healthy,
        status_code=200 if healthy else None,
        response_time_ms=12.0,
        error_message=error,
        endpoint=f"http://1.2.3.4/{name}",
    )


def _all_healthy() -> list[HealthCheckResult]:
    return [_result(name, healthy=True) for name in SERVICES]


def _with_unhealthy(bad_service: str, reason: str) -> list[HealthCheckResult]:
    return [
        _result(name, healthy=(name != bad_service), error=reason if name == bad_service else None) for name in SERVICES
    ]


def _write_state(
    state_dir: Path,
    name: str = "demo",
    public_ip: str | None = "1.2.3.4",
    private_ip: str = "10.0.0.1",
) -> None:
    """Persist a minimal valid DeploymentState (fixture pattern from test_infra)."""
    config = DeploymentConfig(stack_name=name, tier="dev", region="us-east-1")
    cost = CostTracking(
        instance_type="t3.medium",
        is_spot=True,
        on_demand_price_per_hour=Decimal("0.04"),
        estimated_monthly_cost=Decimal("25.0"),
    )
    state = DeploymentState(
        stack_name=name,
        status="running",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        vpc_id="vpc-1",
        subnet_ids=["subnet-1"],
        security_group_id="sg-1",
        efs_id="efs-1",
        efs_mount_target_id="mt-1",
        instance_id="i-1",
        keypair_name="kp-1",
        public_ip=public_ip,
        private_ip=private_ip,
        n8n_url="http://1.2.3.4:5678",
        cost=cost,
        config=config,
    )
    StateManager(base_path=state_dir).save_deployment_sync(state)


def _screen(
    state_dir: Path,
    checker: FakeHealthChecker | BlockedHealthChecker,
    stack_name: str = "demo",
) -> MonitorScreen:
    return MonitorScreen(
        stack_name=stack_name,
        state_dir=state_dir,
        poll_interval=POLL_INTERVAL,
        health_checker=checker,
    )


async def _wait_for(pilot: Pilot[None], condition: Callable[[], bool], timeout: float = 5.0) -> None:
    elapsed = 0.0
    step = 0.05
    while elapsed < timeout:
        if condition():
            return
        await pilot.pause(step)
        elapsed += step
    pytest.fail("Timed out waiting for condition")


def _status_text(screen: MonitorScreen) -> str:
    return str(screen.query_one("#monitor-status", Static).content)


def _event_text(screen: MonitorScreen) -> str:
    log = screen.query_one("#monitor-events", RichLog)
    return "\n".join(strip.text for strip in log.lines)


@pytest.mark.asyncio
async def test_initial_wait_state_renders(tmp_path: Path) -> None:
    """The pane shows an explicit WAIT state immediately, never blank."""
    _write_state(tmp_path)
    checker = BlockedHealthChecker()
    screen = _screen(tmp_path, checker)
    app = MonitorTestApp(screen)
    async with app.run_test() as pilot:
        assert "[WAIT]" in _status_text(screen)
        await _wait_for(pilot, lambda: checker.calls >= 1)
        # First poll never completes: still an explicit WAIT state.
        assert "[WAIT]" in _status_text(screen)
        assert "1.2.3.4" in _status_text(screen)


@pytest.mark.asyncio
async def test_polls_populate_service_table(tmp_path: Path) -> None:
    _write_state(tmp_path)
    checker = FakeHealthChecker([_all_healthy()])
    screen = _screen(tmp_path, checker)
    app = MonitorTestApp(screen)
    async with app.run_test() as pilot:
        await _wait_for(pilot, lambda: checker.calls >= 2)
        table = screen.query_one("#monitor-table", DataTable)
        assert table.row_count == len(SERVICES)
        for name in SERVICES:
            row = table.get_row(name)
            assert str(row[0]) == name.upper()
            assert str(row[1]) == "OK"
        assert checker.hosts[0] == "1.2.3.4"
        assert "5/5 SERVICES HEALTHY" in _status_text(screen)
        assert "LAST POLL" in str(screen.query_one("#monitor-last-poll", Static).content)


@pytest.mark.asyncio
async def test_unhealthy_service_renders_error_line(tmp_path: Path) -> None:
    _write_state(tmp_path)
    checker = FakeHealthChecker([_all_healthy(), _with_unhealthy("qdrant", "refused")])
    screen = _screen(tmp_path, checker)
    app = MonitorTestApp(screen)
    async with app.run_test() as pilot:
        await _wait_for(pilot, lambda: checker.calls >= 2)
        table = screen.query_one("#monitor-table", DataTable)
        await _wait_for(pilot, lambda: str(table.get_row("qdrant")[1]) == "FAIL")
        events = _event_text(screen)
        assert "[ERROR]" in events
        assert "QDRANT UNHEALTHY" in events
        assert "refused" in events
        # healthy -> unhealthy transition is logged as a state change
        assert "QDRANT WENT DOWN" in events
        assert "4/5 SERVICES HEALTHY" in _status_text(screen)


@pytest.mark.asyncio
async def test_dismiss_stops_polling_worker(tmp_path: Path) -> None:
    """Escape dismisses the screen and Textual cancels the bound worker."""
    _write_state(tmp_path)
    checker = FakeHealthChecker([_all_healthy()])
    screen = _screen(tmp_path, checker)
    app = MonitorTestApp(screen)
    async with app.run_test() as pilot:
        await _wait_for(pilot, lambda: checker.calls >= 2)
        await pilot.press("escape")
        await pilot.pause(POLL_INTERVAL * 4)
        assert screen not in app.screen_stack
        calls_after_dismiss = checker.calls
        await pilot.pause(POLL_INTERVAL * 10)
        assert checker.calls == calls_after_dismiss


@pytest.mark.asyncio
async def test_missing_stack_shows_explicit_error(tmp_path: Path) -> None:
    checker = FakeHealthChecker([_all_healthy()])
    screen = _screen(tmp_path, checker, stack_name="ghost")
    app = MonitorTestApp(screen)
    async with app.run_test() as pilot:
        await _wait_for(pilot, lambda: "[ERROR]" in _status_text(screen))
        assert "NO DEPLOYMENT STATE FOUND FOR 'ghost'" in _status_text(screen)
        assert "[ERROR]" in _event_text(screen)
        # Polling never started: the checker was never invoked.
        assert checker.calls == 0


@pytest.mark.asyncio
async def test_unresolvable_host_shows_explicit_error(tmp_path: Path) -> None:
    _write_state(tmp_path, public_ip=None, private_ip="")
    checker = FakeHealthChecker([_all_healthy()])
    screen = _screen(tmp_path, checker)
    app = MonitorTestApp(screen)
    async with app.run_test() as pilot:
        await _wait_for(pilot, lambda: "[ERROR]" in _status_text(screen))
        assert "UNRESOLVABLE HOST" in _status_text(screen)
        assert checker.calls == 0
