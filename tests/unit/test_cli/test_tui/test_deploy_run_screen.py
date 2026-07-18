"""Tests for the TUI deploy run screen (no AWS, no network, no boto3 calls)."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Generator, Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

pytest.importorskip("textual")

from textual.app import App  # noqa: E402
from textual.pilot import Pilot  # noqa: E402
from textual.widgets import RichLog, Static  # noqa: E402

from geusemaker.cli import tui as tui_pkg  # noqa: E402
from geusemaker.cli.progress_events import ProgressEvent  # noqa: E402
from geusemaker.cli.tui.deploy_run_screen import (  # noqa: E402
    STATUS_ACTIVE,
    STATUS_DONE,
    STATUS_ERROR,
    STATUS_PENDING,
    DeployRunScreen,
    stages_for_config,
)
from geusemaker.models import CostTracking, DeploymentConfig, DeploymentState  # noqa: E402
from geusemaker.services.ssm import UserdataCompletion, UserdataLogStream  # noqa: E402

BRUTALIST_CSS = Path(tui_pkg.__file__).parent / "brutalist.tcss"

INSTANCE_ID = "i-1234567890abcdef0"

#: Realistic tier1 event script (mirrors tests/unit/test_orchestration/
#: test_progress_events.py plus the runner's post-deploy userdata event).
TIER1_EVENTS = [
    ProgressEvent("validate", "Running pre-deployment validation"),
    ProgressEvent("vpc", "VPC ready", resource_id="vpc-new"),
    ProgressEvent("sg", "Security group ready", resource_id="sg-1"),
    ProgressEvent("efs", "EFS filesystem available", resource_id="fs-1"),
    ProgressEvent("iam", "Instance profile ready"),
    ProgressEvent("userdata", "Generating UserData script"),
    ProgressEvent("ec2", "Instance running", resource_id=INSTANCE_ID),
    ProgressEvent("userdata", "Streaming instance initialization"),
    ProgressEvent("finalize", "Deployment state saved for demo"),
]


def _config(stack_name: str = "demo") -> DeploymentConfig:
    return DeploymentConfig(stack_name=stack_name, tier="dev", region="us-east-1")


def _state(name: str = "demo") -> DeploymentState:
    """Minimal valid DeploymentState (fixture pattern from test_monitor_screen)."""
    cost = CostTracking(
        instance_type="t3.medium",
        is_spot=True,
        on_demand_price_per_hour=Decimal("0.04"),
        estimated_monthly_cost=Decimal("25.0"),
    )
    return DeploymentState(
        stack_name=name,
        status="running",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        vpc_id="vpc-new",
        subnet_ids=["subnet-1"],
        security_group_id="sg-1",
        efs_id="fs-1",
        efs_mount_target_id="mt-1",
        instance_id=INSTANCE_ID,
        keypair_name="kp-1",
        public_ip="1.2.3.4",
        private_ip="10.0.0.1",
        n8n_url="http://1.2.3.4:5678",
        cost=cost,
        config=_config(name),
    )


class ScriptedExecutor:
    """Emits a scripted event sequence with tiny sleeps, then returns state.

    ``wait_on`` (optional) is awaited (with timeout) before the given stage's
    event index — used to let the fake userdata stream finish before finalize.
    ``fail_after_stage`` raises RuntimeError right after that stage's event.
    """

    def __init__(
        self,
        events: list[ProgressEvent],
        state: DeploymentState,
        *,
        wait_before_index: int | None = None,
        wait_on: threading.Event | None = None,
        fail_after_stage: str | None = None,
        fail_message: str = "boom",
    ) -> None:
        self.events = events
        self.state = state
        self.wait_before_index = wait_before_index
        self.wait_on = wait_on
        self.fail_after_stage = fail_after_stage
        self.fail_message = fail_message

    def __call__(
        self,
        config: DeploymentConfig,
        on_progress: Callable[[ProgressEvent], None],
    ) -> DeploymentState:
        for index, event in enumerate(self.events):
            if index == self.wait_before_index and self.wait_on is not None and not self.wait_on.wait(timeout=5):
                raise RuntimeError("fake stream never finished")
            on_progress(event)
            time.sleep(0.01)
            if event.stage == self.fail_after_stage:
                raise RuntimeError(self.fail_message)
        return self.state


class GatedExecutor:
    """Emits one event, then blocks until the test releases the gate."""

    def __init__(self, events: list[ProgressEvent], state: DeploymentState) -> None:
        self.events = events
        self.state = state
        self.step = threading.Event()

    def __call__(
        self,
        config: DeploymentConfig,
        on_progress: Callable[[ProgressEvent], None],
    ) -> DeploymentState:
        for event in self.events:
            on_progress(event)
            if not self.step.wait(timeout=5):
                raise RuntimeError("gate never released")
            self.step.clear()
        return self.state


class BlockedExecutor:
    """Emits one event, blocks on a gate, then emits late events after release."""

    def __init__(self, state: DeploymentState) -> None:
        self.state = state
        self.gate = threading.Event()
        self.finished = threading.Event()

    def __call__(
        self,
        config: DeploymentConfig,
        on_progress: Callable[[ProgressEvent], None],
    ) -> DeploymentState:
        on_progress(ProgressEvent("vpc", "Creating VPC", resource_id="vpc-new"))
        if not self.gate.wait(timeout=10):
            raise RuntimeError("gate never released")
        # These land after the screen was dismissed: they must be dropped.
        on_progress(ProgressEvent("sg", "Late event after dismissal"))
        on_progress(ProgressEvent("ec2", "Very late event", resource_id=INSTANCE_ID))
        self.finished.set()
        return self.state


class FakeStreamer:
    """Yields scripted lines, records calls, signals completion; no SSM.

    ``completion`` (optional) is delivered as the wrapped stream's terminal
    reason via ``UserdataLogStream.completion`` — mirrors the real streamer,
    which preserves the SSMService completion through the DI seam.
    """

    def __init__(
        self,
        lines: list[str] | None = None,
        done: threading.Event | None = None,
        completion: UserdataCompletion | None = None,
    ) -> None:
        self.lines = lines if lines is not None else []
        self.done = done
        self.completion = completion
        self.calls: list[str] = []

    def __call__(self, instance_id: str) -> Iterator[str]:
        self.calls.append(instance_id)

        def _gen() -> Generator[str, None, UserdataCompletion | None]:
            yield from self.lines
            if self.done is not None:
                self.done.set()
            return self.completion

        return UserdataLogStream(_gen())


class DeployRunTestApp(App[None]):
    """Minimal host app providing the $gm-* variables the screen CSS uses."""

    CSS_PATH = str(BRUTALIST_CSS)

    def __init__(self, screen: DeployRunScreen) -> None:
        super().__init__()
        self._deploy_screen = screen

    def on_mount(self) -> None:
        self.push_screen(self._deploy_screen)


async def _wait_for(pilot: Pilot[None], condition: Callable[[], bool], timeout: float = 5.0) -> None:
    elapsed = 0.0
    step = 0.05
    while elapsed < timeout:
        if condition():
            return
        await pilot.pause(step)
        elapsed += step
    pytest.fail("Timed out waiting for condition")


def _status_text(screen: DeployRunScreen) -> str:
    return str(screen.query_one("#deploy-run-status", Static).content)


def _event_text(screen: DeployRunScreen) -> str:
    log = screen.query_one("#deploy-run-events", RichLog)
    return "\n".join(strip.text for strip in log.lines)


def test_stages_for_config_filters_alb_and_cdn() -> None:
    tier1 = stages_for_config(_config())
    assert "alb" not in tier1
    assert "cdn" not in tier1
    assert tier1[0] == "validate"
    assert tier1[-1] == "finalize"
    tier2 = stages_for_config(DeploymentConfig(stack_name="t2", tier="automation", region="us-east-1"))
    assert "alb" in tier2
    assert "cdn" not in tier2
    tier3 = stages_for_config(
        DeploymentConfig(stack_name="t3", tier="gpu", instance_type="g4dn.xlarge", region="us-east-1")
    )
    assert "alb" in tier3
    assert "cdn" in tier3


@pytest.mark.asyncio
async def test_stages_transition_pending_active_done_in_order() -> None:
    events = [
        ProgressEvent("validate", "Validating"),
        ProgressEvent("vpc", "VPC ready", resource_id="vpc-new"),
        ProgressEvent("sg", "SG ready", resource_id="sg-1"),
        ProgressEvent("efs", "EFS ready", resource_id="fs-1"),
        ProgressEvent("finalize", "Saved"),
    ]
    executor = GatedExecutor(events, _state())
    screen = DeployRunScreen(config=_config(), executor=executor, userdata_streamer=FakeStreamer())
    app = DeployRunTestApp(screen)
    async with app.run_test() as pilot:
        await _wait_for(pilot, lambda: screen.stage_statuses["validate"] == STATUS_ACTIVE)
        assert screen.stage_statuses["vpc"] == STATUS_PENDING
        assert screen.stage_statuses["sg"] == STATUS_PENDING
        executor.step.set()
        await _wait_for(pilot, lambda: screen.stage_statuses["vpc"] == STATUS_ACTIVE)
        assert screen.stage_statuses["validate"] == STATUS_DONE
        assert screen.stage_statuses["sg"] == STATUS_PENDING
        executor.step.set()
        await _wait_for(pilot, lambda: screen.stage_statuses["sg"] == STATUS_ACTIVE)
        assert screen.stage_statuses["vpc"] == STATUS_DONE
        executor.step.set()
        await _wait_for(pilot, lambda: screen.stage_statuses["efs"] == STATUS_ACTIVE)
        assert screen.stage_statuses["sg"] == STATUS_DONE
        executor.step.set()
        await _wait_for(pilot, lambda: screen.stage_statuses["finalize"] == STATUS_ACTIVE)
        executor.step.set()
        await _wait_for(pilot, lambda: "DEPLOY COMPLETE" in _status_text(screen))
        assert all(status == STATUS_DONE for status in screen.stage_statuses.values())


@pytest.mark.asyncio
async def test_userdata_stream_attaches_with_captured_instance_id() -> None:
    stream_done = threading.Event()
    streamer = FakeStreamer(
        lines=["Installing docker...", "Mounting EFS fs-1", "GeuseMaker initialization complete!"],
        done=stream_done,
        completion=UserdataCompletion.SUCCESS,
    )
    # Executor waits for the fake stream to drain before emitting finalize,
    # exactly like the real runner (stream runs before run() returns).
    executor = ScriptedExecutor(
        TIER1_EVENTS,
        _state(),
        wait_before_index=len(TIER1_EVENTS) - 1,
        wait_on=stream_done,
    )
    screen = DeployRunScreen(config=_config(), executor=executor, userdata_streamer=streamer)
    app = DeployRunTestApp(screen)
    async with app.run_test() as pilot:
        await _wait_for(pilot, lambda: "DEPLOY COMPLETE" in _status_text(screen))
        assert streamer.calls == [INSTANCE_ID]
        events_text = _event_text(screen)
        # First userdata event fires before the instance exists: explicit skip.
        assert "INSTANCE ID UNKNOWN · USERDATA STREAM SKIPPED" in events_text
        assert f"USERDATA STREAM ATTACHED · {INSTANCE_ID}" in events_text
        assert "Installing docker..." in events_text
        assert "GeuseMaker initialization complete!" in events_text
        assert "USERDATA STREAM ENDED" in events_text
        # Progress events render as "[STAGE] message" lines.
        assert "[VPC] VPC ready" in events_text
        assert "[EC2] Instance running" in events_text


@pytest.mark.asyncio
async def test_userdata_stream_error_renders_error_line() -> None:
    stream_done = threading.Event()
    streamer = FakeStreamer(
        lines=["Installing docker...", "ERROR: efs mount failed"],
        done=stream_done,
        completion=UserdataCompletion.ERROR,
    )
    executor = ScriptedExecutor(
        TIER1_EVENTS,
        _state(),
        wait_before_index=len(TIER1_EVENTS) - 1,
        wait_on=stream_done,
    )
    screen = DeployRunScreen(config=_config(), executor=executor, userdata_streamer=streamer)
    app = DeployRunTestApp(screen)
    async with app.run_test() as pilot:
        await _wait_for(pilot, lambda: "USERDATA INITIALIZATION FAILED" in _event_text(screen))
        events_text = _event_text(screen)
        assert "USERDATA INITIALIZATION FAILED" in events_text
        # The false-success line must NOT appear on an error termination.
        assert "USERDATA STREAM ENDED" not in events_text


@pytest.mark.asyncio
async def test_userdata_stream_timeout_renders_warning_line() -> None:
    stream_done = threading.Event()
    streamer = FakeStreamer(
        lines=["Installing docker...", "still working"],
        done=stream_done,
        completion=UserdataCompletion.TIMEOUT,
    )
    executor = ScriptedExecutor(
        TIER1_EVENTS,
        _state(),
        wait_before_index=len(TIER1_EVENTS) - 1,
        wait_on=stream_done,
    )
    screen = DeployRunScreen(config=_config(), executor=executor, userdata_streamer=streamer)
    app = DeployRunTestApp(screen)
    async with app.run_test() as pilot:
        await _wait_for(pilot, lambda: "USERDATA STREAM TIMED OUT" in _event_text(screen))
        events_text = _event_text(screen)
        assert "USERDATA STREAM TIMED OUT" in events_text
        assert "USERDATA STREAM ENDED" not in events_text


@pytest.mark.asyncio
async def test_success_banner_renders_and_single_escape_dismisses() -> None:
    executor = ScriptedExecutor(TIER1_EVENTS[:5] + [TIER1_EVENTS[-1]], _state())
    screen = DeployRunScreen(config=_config(), executor=executor, userdata_streamer=FakeStreamer())
    app = DeployRunTestApp(screen)
    async with app.run_test() as pilot:
        await _wait_for(pilot, lambda: "DEPLOY COMPLETE" in _status_text(screen))
        assert "DEPLOY COMPLETE · STACK DEMO" in _status_text(screen)
        assert "DEPLOY COMPLETE · STACK DEMO" in _event_text(screen)
        assert all(status == STATUS_DONE for status in screen.stage_statuses.values())
        # After the terminal state a single escape dismisses immediately.
        await pilot.press("escape")
        await pilot.pause(0.1)
        assert screen not in app.screen_stack


@pytest.mark.asyncio
async def test_failure_marks_stage_error_and_keeps_screen_open() -> None:
    executor = ScriptedExecutor(
        TIER1_EVENTS[:4],
        _state(),
        fail_after_stage="efs",
        fail_message="EFS create failed",
    )
    screen = DeployRunScreen(config=_config(), executor=executor, userdata_streamer=FakeStreamer())
    app = DeployRunTestApp(screen)
    async with app.run_test() as pilot:
        await _wait_for(pilot, lambda: "DEPLOY FAILED" in _status_text(screen))
        assert "EFS create failed" in _status_text(screen)
        assert screen.stage_statuses["efs"] == STATUS_ERROR
        assert screen.stage_statuses["vpc"] == STATUS_DONE
        events_text = _event_text(screen)
        assert "DEPLOY FAILED · EFS create failed" in events_text
        assert "SCREEN LEFT OPEN FOR READING" in events_text
        # The screen stays open for reading — no auto-dismiss.
        await pilot.pause(0.2)
        assert screen in app.screen_stack
        # After the terminal state, one escape closes it.
        await pilot.press("escape")
        await pilot.pause(0.1)
        assert screen not in app.screen_stack


@pytest.mark.asyncio
async def test_q_while_running_arms_guard_then_dismisses_without_quitting() -> None:
    """`q` during a live deploy must route through the SAME guard as escape.

    The app-level ("q", "quit") binding would kill the whole app; the screen's
    own `q` binding takes priority and arms the double-press guard instead.
    A single `q` must NOT quit the app; a second press detaches cleanly.
    """
    executor = BlockedExecutor(_state())
    screen = DeployRunScreen(config=_config(), executor=executor, userdata_streamer=FakeStreamer())
    app = DeployRunTestApp(screen)
    async with app.run_test() as pilot:
        await _wait_for(pilot, lambda: screen.stage_statuses["vpc"] == STATUS_ACTIVE)
        # First `q`: guard arms, warn line, screen stays, app still running.
        await pilot.press("q")
        await pilot.pause(0.1)
        assert "DEPLOY STILL RUNNING · ESC AGAIN TO DETACH" in _event_text(screen)
        assert screen in app.screen_stack
        assert app.is_running
        # Second `q`: detaches with clean teardown (stop/ui-closed both set).
        await pilot.press("q")
        await pilot.pause(0.1)
        assert screen not in app.screen_stack
        assert app.is_running
        assert screen._ui_closed.is_set()
        assert screen._stream_stop.is_set()
        executor.gate.set()
        await _wait_for(pilot, lambda: executor.finished.is_set())
        await pilot.pause(0.2)
        assert app.is_running


@pytest.mark.asyncio
async def test_single_q_during_deploy_does_not_quit_app() -> None:
    """A single `q` mid-deploy must never exit the app (guard only arms)."""
    executor = BlockedExecutor(_state())
    screen = DeployRunScreen(config=_config(), executor=executor, userdata_streamer=FakeStreamer())
    app = DeployRunTestApp(screen)
    async with app.run_test() as pilot:
        await _wait_for(pilot, lambda: screen.stage_statuses["vpc"] == STATUS_ACTIVE)
        await pilot.press("q")
        await pilot.pause(0.2)
        assert app.is_running
        assert screen in app.screen_stack
        assert screen._dismiss_armed
        executor.gate.set()
        await _wait_for(pilot, lambda: executor.finished.is_set())


@pytest.mark.asyncio
async def test_ctrl_c_while_running_routes_through_guard() -> None:
    """ctrl+c is intercepted (priority binding) and shares the same guard.

    In Textual 8.2.8 ctrl+c does not quit — the app maps it to a "press ctrl+q
    to quit" notification and the base Screen maps it to copy_text. Our
    priority `ctrl+c` binding wins the priority pass so it arms/detaches via
    the same guard as escape and `q`.
    """
    executor = BlockedExecutor(_state())
    screen = DeployRunScreen(config=_config(), executor=executor, userdata_streamer=FakeStreamer())
    app = DeployRunTestApp(screen)
    async with app.run_test() as pilot:
        await _wait_for(pilot, lambda: screen.stage_statuses["vpc"] == STATUS_ACTIVE)
        await pilot.press("ctrl+c")
        await pilot.pause(0.1)
        assert screen._dismiss_armed
        assert "DEPLOY STILL RUNNING · ESC AGAIN TO DETACH" in _event_text(screen)
        assert screen in app.screen_stack
        assert app.is_running
        await pilot.press("ctrl+c")
        await pilot.pause(0.1)
        assert screen not in app.screen_stack
        assert app.is_running
        assert screen._ui_closed.is_set()
        assert screen._stream_stop.is_set()
        executor.gate.set()
        await _wait_for(pilot, lambda: executor.finished.is_set())


@pytest.mark.asyncio
async def test_mixed_q_then_escape_share_one_armed_state() -> None:
    """The armed state is unified: `q` arms, escape completes the dismiss."""
    executor = BlockedExecutor(_state())
    screen = DeployRunScreen(config=_config(), executor=executor, userdata_streamer=FakeStreamer())
    app = DeployRunTestApp(screen)
    async with app.run_test() as pilot:
        await _wait_for(pilot, lambda: screen.stage_statuses["vpc"] == STATUS_ACTIVE)
        await pilot.press("q")
        await pilot.pause(0.1)
        assert screen._dismiss_armed
        assert screen in app.screen_stack
        # A different guard key (escape) completes the dismiss.
        await pilot.press("escape")
        await pilot.pause(0.1)
        assert screen not in app.screen_stack
        assert app.is_running
        executor.gate.set()
        await _wait_for(pilot, lambda: executor.finished.is_set())


@pytest.mark.asyncio
async def test_double_escape_while_running_detaches_and_late_events_are_dropped() -> None:
    executor = BlockedExecutor(_state())
    screen = DeployRunScreen(config=_config(), executor=executor, userdata_streamer=FakeStreamer())
    app = DeployRunTestApp(screen)
    async with app.run_test() as pilot:
        await _wait_for(pilot, lambda: screen.stage_statuses["vpc"] == STATUS_ACTIVE)
        # First escape while running: warn line, screen stays.
        await pilot.press("escape")
        await pilot.pause(0.1)
        assert "DEPLOY STILL RUNNING · ESC AGAIN TO DETACH" in _event_text(screen)
        assert screen in app.screen_stack
        # Second escape detaches.
        await pilot.press("escape")
        await pilot.pause(0.1)
        assert screen not in app.screen_stack
        # Release the executor: its late events must not crash the app.
        executor.gate.set()
        await _wait_for(pilot, lambda: executor.finished.is_set())
        await pilot.pause(0.2)
        assert app.is_running
