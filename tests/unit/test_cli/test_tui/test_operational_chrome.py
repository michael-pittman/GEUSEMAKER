"""Chrome tests for the operational TUI screens: persistent Footer + `?` help.

Every pushed operational screen (Monitor/Logs/Deploy/DeployRun/Inspect) must
carry a Footer so its BINDINGS render as key hints, and must answer `?` with a
dismissible help overlay listing the screen's own actions plus the hub's global
navigation keys. These are exercised against a host app that reuses the real
GeuseMakerApp BINDINGS so the GLOBAL NAVIGATION section is populated exactly as
in production. No network or boto3 is touched (all AWS seams are faked).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

pytest.importorskip("textual")

from textual.app import App  # noqa: E402
from textual.pilot import Pilot  # noqa: E402
from textual.screen import Screen  # noqa: E402
from textual.widgets import Footer, Static  # noqa: E402

from geusemaker.cli import tui as tui_pkg  # noqa: E402
from geusemaker.cli.progress_events import ProgressEvent  # noqa: E402
from geusemaker.cli.tui._base import HelpModal, OperationalScreen, collect_bindings  # noqa: E402
from geusemaker.cli.tui.app import GeuseMakerApp  # noqa: E402
from geusemaker.cli.tui.deploy_run_screen import DeployRunScreen  # noqa: E402
from geusemaker.cli.tui.deploy_screen import DeployScreen  # noqa: E402
from geusemaker.cli.tui.inspect_screen import InspectScreen  # noqa: E402
from geusemaker.cli.tui.logs_screen import LogsScreen  # noqa: E402
from geusemaker.cli.tui.monitor_screen import MonitorScreen  # noqa: E402
from geusemaker.infra.state import StateManager  # noqa: E402
from geusemaker.models import CostTracking, DeploymentConfig, DeploymentState  # noqa: E402
from geusemaker.models.health import HealthCheckResult  # noqa: E402

BRUTALIST_CSS = Path(tui_pkg.__file__).parent / "brutalist.tcss"

SERVICES = ("n8n", "ollama", "qdrant", "crawl4ai", "postgres")


class HostApp(App[None]):
    """Minimal host that reuses the real hub nav bindings and brutalist CSS."""

    CSS_PATH = str(BRUTALIST_CSS)
    BINDINGS = GeuseMakerApp.BINDINGS

    def __init__(self, screen: Screen[None]) -> None:
        super().__init__()
        self._screen = screen

    def on_mount(self) -> None:
        self.push_screen(self._screen)


async def _healthy(host: str) -> list[HealthCheckResult]:
    return [
        HealthCheckResult(
            service_name=name,
            healthy=True,
            status_code=200,
            response_time_ms=1.0,
            error_message=None,
            endpoint=f"http://{host}/{name}",
        )
        for name in SERVICES
    ]


def _fake_stream_factory(_instance_id: str, _target_key: str) -> Iterator[str]:
    return iter(())


def _make_config() -> DeploymentConfig:
    return DeploymentConfig(stack_name="demo", tier="dev", region="us-east-1")


def _make_state(config: DeploymentConfig) -> DeploymentState:
    cost = CostTracking(
        instance_type="t3.medium",
        is_spot=True,
        on_demand_price_per_hour=Decimal("0.04"),
        estimated_monthly_cost=Decimal("25.0"),
    )
    return DeploymentState(
        stack_name=config.stack_name,
        status="running",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        vpc_id="vpc-1",
        subnet_ids=["subnet-1"],
        security_group_id="sg-1",
        efs_id="fs-1",
        efs_mount_target_id="fsmt-1",
        instance_id="i-1",
        keypair_name="kp-1",
        public_ip="1.2.3.4",
        private_ip="10.0.0.1",
        n8n_url="http://1.2.3.4:5678",
        cost=cost,
        config=config,
    )


def _fake_executor(config: DeploymentConfig, on_progress: Callable[[ProgressEvent], None]) -> DeploymentState:
    on_progress(ProgressEvent(stage="validate", message="ok"))
    return _make_state(config)


def _write_state(state_dir: Path, name: str = "demo") -> None:
    StateManager(base_path=state_dir).save_deployment_sync(
        _make_state(_make_config().model_copy(update={"stack_name": name}))
    )


def _build_screen(kind: str, tmp_path: Path) -> OperationalScreen:
    """Construct one operational screen with every AWS seam faked."""
    if kind == "monitor":
        _write_state(tmp_path)
        return MonitorScreen(stack_name="demo", state_dir=tmp_path, poll_interval=0.05, health_checker=_healthy)
    if kind == "logs":
        _write_state(tmp_path)
        return LogsScreen(stack_name="demo", state_dir=tmp_path, stream_factory=_fake_stream_factory)
    if kind == "deploy":
        return DeployScreen(initial_state={"stack_name": "demo"})
    if kind == "deploy_run":
        return DeployRunScreen(
            config=_make_config(),
            executor=_fake_executor,
            userdata_streamer=lambda _instance_id: iter(()),
        )
    if kind == "inspect":
        return InspectScreen(state_dir=tmp_path)
    raise ValueError(kind)


#: (kind, a primary action description the help overlay must surface).
SCREENS: tuple[tuple[str, str], ...] = (
    ("monitor", "BACK"),
    ("logs", "STOP STREAM"),
    ("deploy", "LAUNCH"),
    ("deploy_run", "BACK"),
    ("inspect", "LOGS"),
)


async def _wait(pilot: Pilot[None], condition: Callable[[], bool], timeout: float = 5.0) -> None:
    elapsed = 0.0
    while elapsed < timeout:
        if condition():
            return
        await pilot.pause(0.05)
        elapsed += 0.05
    pytest.fail("timed out waiting for condition")


# --------------------------------------------------------------------------- #
# collect_bindings unit coverage
# --------------------------------------------------------------------------- #
def test_collect_bindings_skips_hidden_and_dedupes() -> None:
    """DeployRunScreen hides q/ctrl+c (show=False); only BACK + HELP surface."""
    screen = DeployRunScreen(config=_make_config(), executor=_fake_executor)
    pairs = collect_bindings(screen)
    descriptions = [desc for _key, desc in pairs]
    assert ("escape", "BACK") in pairs
    assert ("question_mark", "HELP") in pairs
    # q and ctrl+c are show=False -> excluded; BACK appears once, not per-key.
    assert descriptions.count("BACK") == 1


def test_collect_bindings_reads_app_nav_keys() -> None:
    app = GeuseMakerApp(show_splash=False)
    nav = dict(collect_bindings(app))
    assert nav.get("h") == "HUB"
    assert nav.get("q") == "QUIT"
    assert set(nav.values()) >= {"HUB", "DEPLOY", "MONITOR", "INSPECT", "QUIT"}


# --------------------------------------------------------------------------- #
# Footer presence
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("kind", [k for k, _ in SCREENS])
@pytest.mark.asyncio
async def test_operational_screen_mounts_footer(kind: str, tmp_path: Path) -> None:
    screen = _build_screen(kind, tmp_path)
    app = HostApp(screen)
    async with app.run_test(size=(120, 40)) as pilot:
        await _wait(pilot, lambda: app.screen is screen)
        footer = screen.query_one(Footer)
        assert footer.is_attached


# --------------------------------------------------------------------------- #
# `?` help overlay
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(("kind", "primary"), SCREENS)
@pytest.mark.asyncio
async def test_question_mark_opens_and_dismisses_help(kind: str, primary: str, tmp_path: Path) -> None:
    screen = _build_screen(kind, tmp_path)
    app = HostApp(screen)
    async with app.run_test(size=(120, 40)) as pilot:
        await _wait(pilot, lambda: app.screen is screen)
        await pilot.press("?")
        await _wait(pilot, lambda: isinstance(app.screen, HelpModal))
        modal = app.screen
        assert isinstance(modal, HelpModal)

        screen_rows = str(modal.query_one("#help-screen-bindings", Static).content)
        global_rows = str(modal.query_one("#help-global-bindings", Static).content)
        # The overlay surfaces this screen's primary action and its own help key.
        assert primary in screen_rows
        assert "HELP" in screen_rows
        # ...and the hub's global navigation keys.
        assert "HUB" in global_rows
        assert "QUIT" in global_rows

        # Escape dismisses the overlay and returns to the underlying screen.
        await pilot.press("escape")
        await _wait(pilot, lambda: app.screen is screen)
        assert not isinstance(app.screen, HelpModal)


@pytest.mark.asyncio
async def test_help_overlay_dismisses_with_question_mark_and_close_button(tmp_path: Path) -> None:
    """The overlay is dismissible via `?` again and via the CLOSE button."""
    from textual.widgets import Button

    screen = _build_screen("inspect", tmp_path)
    app = HostApp(screen)
    async with app.run_test(size=(120, 40)) as pilot:
        await _wait(pilot, lambda: app.screen is screen)
        # `?` toggles: open, then `?` closes (modal binds it too).
        await pilot.press("?")
        await _wait(pilot, lambda: isinstance(app.screen, HelpModal))
        await pilot.press("?")
        await _wait(pilot, lambda: app.screen is screen)
        # Reopen and dismiss via the CLOSE button.
        await pilot.press("?")
        await _wait(pilot, lambda: isinstance(app.screen, HelpModal))
        app.screen.query_one("#help-close", Button).press()
        await _wait(pilot, lambda: app.screen is screen)
        assert not isinstance(app.screen, HelpModal)
