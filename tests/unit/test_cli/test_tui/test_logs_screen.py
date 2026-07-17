"""Pilot tests for the TUI logs screen (no AWS, no network, no boto3)."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

pytest.importorskip("textual")

from textual.app import App  # noqa: E402
from textual.pilot import Pilot  # noqa: E402
from textual.widgets import ListView, RichLog, Static  # noqa: E402

from geusemaker.cli import tui as tui_pkg  # noqa: E402
from geusemaker.cli.tui.logs_screen import (  # noqa: E402
    LOG_TARGETS,
    TARGET_ITEM_PREFIX,
    LogsScreen,
)
from geusemaker.infra.state import StateManager  # noqa: E402
from geusemaker.models import CostTracking, DeploymentConfig, DeploymentState  # noqa: E402

BRUTALIST_CSS = Path(tui_pkg.__file__).parent / "brutalist.tcss"


class LogsTestApp(App[None]):
    """Minimal host app providing the $gm-* variables the screen CSS uses."""

    CSS_PATH = str(BRUTALIST_CSS)

    def __init__(self, logs_screen: LogsScreen) -> None:
        super().__init__()
        self._logs_screen = logs_screen

    def on_mount(self) -> None:
        self.push_screen(self._logs_screen)


class BlockingStream:
    """Iterator that blocks until close() unblocks it; records the close."""

    def __init__(self) -> None:
        self.closed = False
        self._gate = threading.Event()

    def __iter__(self) -> BlockingStream:
        return self

    def __next__(self) -> str:
        self._gate.wait()
        raise StopIteration

    def close(self) -> None:
        self.closed = True
        self._gate.set()


class RecordingFactory:
    """Stream factory: records calls, hands out per-call scripted streams."""

    def __init__(self, streams: list[Iterator[str]] | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self._streams = streams or []

    def __call__(self, instance_id: str, target_key: str) -> Iterator[str]:
        self.calls.append((instance_id, target_key))
        if not self._streams:
            pytest.fail(f"Stream factory called unexpectedly for {target_key!r}")
        return self._streams.pop(0)


def _scripted(lines: list[str]) -> Iterator[str]:
    yield from lines


def _raising(message: str) -> Iterator[str]:
    yield "one line before the failure"
    raise RuntimeError(message)


def _seed_stack(state_dir: Path, name: str = "alpha", *, instance_id: str = "i-alpha") -> None:
    """Persist a minimal valid DeploymentState (test_app_integration pattern).

    ``instance_id=""`` is only loadable while status is 'creating' with a
    pending instance provenance (StateManager.validate_state), which is
    exactly the aborted-before-EC2 shape the screen must survive.
    """
    config = DeploymentConfig(stack_name=name, tier="dev", region="us-east-1")
    cost = CostTracking(
        instance_type="t3.medium",
        is_spot=True,
        on_demand_price_per_hour=Decimal("0.04"),
        estimated_monthly_cost=Decimal("25.0"),
    )
    state = DeploymentState(
        stack_name=name,
        status="running" if instance_id else "creating",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        vpc_id=f"vpc-{name}",
        subnet_ids=[f"subnet-{name}"],
        security_group_id=f"sg-{name}",
        efs_id=f"fs-{name}",
        efs_mount_target_id=f"fsmt-{name}",
        instance_id=instance_id,
        n8n_url="http://1.2.3.4:5678",
        keypair_name=f"kp-{name}",
        public_ip="1.2.3.4",
        private_ip="10.0.0.1",
        cost=cost,
        config=config,
        resource_provenance={} if instance_id else {"instance": "pending"},
    )
    StateManager(base_path=state_dir).save_deployment_sync(state)


def _screen(state_dir: Path, factory: RecordingFactory, stack_name: str = "alpha") -> LogsScreen:
    return LogsScreen(stack_name=stack_name, state_dir=state_dir, stream_factory=factory)


async def _wait_for(pilot: Pilot[None], condition: Callable[[], bool], timeout: float = 5.0) -> None:
    elapsed = 0.0
    step = 0.05
    while elapsed < timeout:
        if condition():
            return
        await pilot.pause(step)
        elapsed += step
    pytest.fail("Timed out waiting for condition")


def _status_text(screen: LogsScreen) -> str:
    return str(screen.query_one("#logs-status", Static).content)


def _pane_lines(screen: LogsScreen) -> list[str]:
    log = screen.query_one("#logs-stream", RichLog)
    return [strip.text.rstrip() for strip in log.lines]


def _pane_text(screen: LogsScreen) -> str:
    return "\n".join(_pane_lines(screen))


async def _select_target(pilot: Pilot[None], screen: LogsScreen, target_key: str) -> None:
    """Drive the picker like a user: highlight the target item, press enter."""
    list_view = screen.query_one("#logs-target-list", ListView)
    for index, item in enumerate(list_view.children):
        if item.id == f"{TARGET_ITEM_PREFIX}{target_key}":
            list_view.index = index
            break
    else:
        pytest.fail(f"No picker item for target {target_key!r}")
    await pilot.pause()
    list_view.action_select_cursor()
    await pilot.pause()


async def _wait_ready(pilot: Pilot[None], screen: LogsScreen) -> None:
    picker = screen.query_one("#logs-target-list", ListView)
    await _wait_for(pilot, lambda: not picker.disabled)


@pytest.mark.asyncio
async def test_picker_lists_all_targets(tmp_path: Path) -> None:
    """All 8 catalog targets appear, in LOG_TARGETS order, with group headers."""
    _seed_stack(tmp_path)
    factory = RecordingFactory()
    screen = _screen(tmp_path, factory)
    app = LogsTestApp(screen)
    async with app.run_test(size=(120, 40)) as pilot:
        await _wait_ready(pilot, screen)
        list_view = screen.query_one("#logs-target-list", ListView)
        target_ids = [
            item.id.removeprefix(TARGET_ITEM_PREFIX)
            for item in list_view.children
            if item.id and item.id.startswith(TARGET_ITEM_PREFIX)
        ]
        assert target_ids == list(LOG_TARGETS)
        assert len(target_ids) == 8
        header_ids = [item.id for item in list_view.children if item.id and item.id.startswith("group-")]
        assert header_ids == ["group-instance", "group-containers"]
        assert factory.calls == []


@pytest.mark.asyncio
async def test_select_userdata_streams_lines_with_wait_and_ended(tmp_path: Path) -> None:
    _seed_stack(tmp_path)
    factory = RecordingFactory([_scripted(["cloud-init start", "docker pull ok"])])
    screen = _screen(tmp_path, factory)
    app = LogsTestApp(screen)
    async with app.run_test(size=(120, 40)) as pilot:
        await _wait_ready(pilot, screen)
        await _select_target(pilot, screen, "userdata")
        await _wait_for(pilot, lambda: "STREAM CLOSED" in _pane_text(screen))
        lines = [line for line in _pane_lines(screen) if line]
        assert lines[0] == "[WAIT] ATTACHING · USERDATA"
        assert lines[-1] == "[ENDED] STREAM CLOSED · USERDATA"
        text = _pane_text(screen)
        assert "cloud-init start" in text
        assert "docker pull ok" in text
        assert text.index("cloud-init start") < text.index("docker pull ok")
        assert factory.calls == [("i-alpha", "userdata")]
        assert "[ENDED]" in _status_text(screen)


@pytest.mark.asyncio
async def test_switch_targets_mid_stream_cancels_first_and_streams_second(tmp_path: Path) -> None:
    _seed_stack(tmp_path)
    blocking = BlockingStream()
    factory = RecordingFactory([blocking, _scripted(["n8n ready on 5678"])])
    screen = _screen(tmp_path, factory)
    app = LogsTestApp(screen)
    async with app.run_test(size=(120, 40)) as pilot:
        await _wait_ready(pilot, screen)
        await _select_target(pilot, screen, "userdata")
        await _wait_for(pilot, lambda: len(factory.calls) == 1)
        assert "ATTACHING · USERDATA" in _pane_text(screen)
        await _select_target(pilot, screen, "n8n")
        await _wait_for(pilot, lambda: blocking.closed)
        await _wait_for(pilot, lambda: "STREAM CLOSED · N8N" in _pane_text(screen))
        assert factory.calls == [("i-alpha", "userdata"), ("i-alpha", "n8n")]
        text = _pane_text(screen)
        # Pane was cleared on switch: the first target's WAIT line is gone.
        assert "ATTACHING · USERDATA" not in text
        assert "n8n ready on 5678" in text


@pytest.mark.asyncio
async def test_s_key_detaches_stream_explicitly(tmp_path: Path) -> None:
    _seed_stack(tmp_path)
    blocking = BlockingStream()
    factory = RecordingFactory([blocking])
    screen = _screen(tmp_path, factory)
    app = LogsTestApp(screen)
    async with app.run_test(size=(120, 40)) as pilot:
        await _wait_ready(pilot, screen)
        await _select_target(pilot, screen, "ollama")
        await _wait_for(pilot, lambda: len(factory.calls) == 1)
        await pilot.press("s")
        await _wait_for(pilot, lambda: "[DETACHED]" in _pane_text(screen))
        assert "STREAM DETACHED · OLLAMA" in _pane_text(screen)
        assert "[DETACHED]" in _status_text(screen)
        await _wait_for(pilot, lambda: blocking.closed)


@pytest.mark.asyncio
async def test_stream_runtime_error_renders_error(tmp_path: Path) -> None:
    _seed_stack(tmp_path)
    factory = RecordingFactory([_raising("SSM ACCESS DENIED FOR i-alpha")])
    screen = _screen(tmp_path, factory)
    app = LogsTestApp(screen)
    async with app.run_test(size=(120, 40)) as pilot:
        await _wait_ready(pilot, screen)
        await _select_target(pilot, screen, "qdrant")
        await _wait_for(pilot, lambda: "[ERROR]" in _pane_text(screen))
        text = _pane_text(screen)
        assert "SSM ACCESS DENIED FOR i-alpha" in text
        assert "one line before the failure" in text
        assert "STREAM CLOSED" not in text
        assert "STREAM FAILED · QDRANT" in _status_text(screen)


@pytest.mark.asyncio
async def test_missing_stack_shows_error_and_disables_picker(tmp_path: Path) -> None:
    factory = RecordingFactory()
    screen = _screen(tmp_path, factory, stack_name="ghost")
    app = LogsTestApp(screen)
    async with app.run_test(size=(120, 40)) as pilot:
        await _wait_for(pilot, lambda: "[ERROR]" in _status_text(screen))
        assert "NO DEPLOYMENT STATE FOUND FOR 'ghost'" in _status_text(screen)
        assert "[ERROR]" in _pane_text(screen)
        assert screen.query_one("#logs-target-list", ListView).disabled
        await pilot.pause(0.2)
        assert factory.calls == []


@pytest.mark.asyncio
async def test_missing_instance_id_shows_error_and_disables_picker(tmp_path: Path) -> None:
    _seed_stack(tmp_path, instance_id="")
    factory = RecordingFactory()
    screen = _screen(tmp_path, factory)
    app = LogsTestApp(screen)
    async with app.run_test(size=(120, 40)) as pilot:
        await _wait_for(pilot, lambda: "[ERROR]" in _status_text(screen))
        assert "NO INSTANCE ID IN STATE FOR 'alpha'" in _status_text(screen)
        assert "[ERROR]" in _pane_text(screen)
        assert screen.query_one("#logs-target-list", ListView).disabled
        await pilot.pause(0.2)
        assert factory.calls == []


@pytest.mark.asyncio
async def test_escape_dismisses_cleanly_mid_stream(tmp_path: Path) -> None:
    _seed_stack(tmp_path)
    blocking = BlockingStream()
    factory = RecordingFactory([blocking])
    screen = _screen(tmp_path, factory)
    app = LogsTestApp(screen)
    async with app.run_test(size=(120, 40)) as pilot:
        await _wait_ready(pilot, screen)
        await _select_target(pilot, screen, "postgres")
        await _wait_for(pilot, lambda: len(factory.calls) == 1)
        await pilot.press("escape")
        await pilot.pause(0.2)
        assert screen not in app.screen_stack
        await _wait_for(pilot, lambda: blocking.closed)
