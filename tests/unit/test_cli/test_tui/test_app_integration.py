"""Pilot tests wiring Inspect/Monitor screens into the hub app (no network, no boto3)."""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

pytest.importorskip("textual")

from geusemaker.cli.tui.app import GeuseMakerApp  # noqa: E402
from geusemaker.cli.tui.inspect_screen import InspectScreen  # noqa: E402
from geusemaker.cli.tui.monitor_screen import MonitorScreen  # noqa: E402
from geusemaker.infra.state import StateManager  # noqa: E402
from geusemaker.models import CostTracking, DeploymentConfig, DeploymentState  # noqa: E402
from geusemaker.models.health import HealthCheckResult  # noqa: E402

SERVICES = ("n8n", "ollama", "qdrant", "crawl4ai", "postgres")


class FakeHealthChecker:
    """Records calls and replays healthy results; never touches the network."""

    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, host: str) -> list[HealthCheckResult]:
        self.calls += 1
        return [
            HealthCheckResult(
                service_name=name,
                healthy=True,
                status_code=200,
                response_time_ms=12.0,
                error_message=None,
                endpoint=f"http://{host}/{name}",
            )
            for name in SERVICES
        ]


def _seed_stack(state_dir: Path, name: str = "alpha") -> None:
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
        vpc_id=f"vpc-{name}",
        subnet_ids=[f"subnet-{name}"],
        security_group_id=f"sg-{name}",
        efs_id=f"fs-{name}",
        efs_mount_target_id=f"fsmt-{name}",
        instance_id=f"i-{name}",
        n8n_url="http://1.2.3.4:5678",
        keypair_name=f"kp-{name}",
        public_ip="1.2.3.4",
        private_ip="10.0.0.1",
        cost=cost,
        config=config,
    )
    StateManager(base_path=state_dir).save_deployment_sync(state)


def _app(tmp_path: Path, **kwargs: object) -> GeuseMakerApp:
    return GeuseMakerApp(show_splash=False, state_dir=tmp_path, **kwargs)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_i_key_pushes_inspect_screen(tmp_path: Path) -> None:
    _seed_stack(tmp_path)
    app = _app(tmp_path)
    async with app.run_test(size=(100, 32)) as pilot:
        await pilot.pause()
        await pilot.press("i")
        await pilot.pause(0.3)
        assert isinstance(app.screen, InspectScreen)


@pytest.mark.asyncio
async def test_monitor_jumpoff_from_inspect_and_escape_chain(tmp_path: Path) -> None:
    _seed_stack(tmp_path)
    checker = FakeHealthChecker()
    app = _app(tmp_path, health_checker=checker)
    async with app.run_test(size=(100, 32)) as pilot:
        await pilot.pause()
        await pilot.press("i")
        await pilot.pause(0.4)
        assert isinstance(app.screen, InspectScreen)
        await pilot.press("m")
        await pilot.pause(0.4)
        assert isinstance(app.screen, MonitorScreen)
        assert checker.calls >= 1
        await pilot.press("escape")
        await pilot.pause(0.2)
        assert isinstance(app.screen, InspectScreen)
        await pilot.press("escape")
        await pilot.pause(0.2)
        assert not isinstance(app.screen, InspectScreen | MonitorScreen)


@pytest.mark.asyncio
async def test_monitor_mode_without_stack_routes_to_inspect(tmp_path: Path) -> None:
    _seed_stack(tmp_path)
    app = _app(tmp_path)
    async with app.run_test(size=(100, 32)) as pilot:
        await pilot.pause()
        await pilot.press("m")
        await pilot.pause(0.3)
        assert isinstance(app.screen, InspectScreen)


@pytest.mark.asyncio
async def test_initial_screen_monitor_with_stack(tmp_path: Path) -> None:
    _seed_stack(tmp_path)
    checker = FakeHealthChecker()
    app = _app(tmp_path, initial_screen="monitor", stack_name="alpha", health_checker=checker)
    async with app.run_test(size=(100, 32)) as pilot:
        await pilot.pause(0.5)
        assert isinstance(app.screen, MonitorScreen)
        assert checker.calls >= 1


@pytest.mark.asyncio
async def test_logs_jumpoff_opens_logs_screen_and_streams(tmp_path: Path) -> None:
    from geusemaker.cli.tui.logs_screen import LogsScreen

    _seed_stack(tmp_path)
    calls: list[tuple[str, str]] = []

    def factory(instance_id: str, target_key: str):  # type: ignore[no-untyped-def]
        calls.append((instance_id, target_key))
        return iter(["line one", "line two"])

    app = _app(tmp_path, log_stream_factory=factory)
    async with app.run_test(size=(110, 34)) as pilot:
        await pilot.pause()
        await pilot.press("i")
        await pilot.pause(0.4)
        await pilot.press("l")
        await pilot.pause(0.4)
        assert isinstance(app.screen, LogsScreen)
        await pilot.press("escape")
        await pilot.pause(0.3)
        assert isinstance(app.screen, InspectScreen)


@pytest.mark.asyncio
async def test_mode_keys_from_pushed_screen_return_to_hub(tmp_path: Path) -> None:
    _seed_stack(tmp_path)
    app = _app(tmp_path)
    async with app.run_test(size=(100, 32)) as pilot:
        await pilot.pause()
        await pilot.press("i")
        await pilot.pause(0.4)
        assert isinstance(app.screen, InspectScreen)
        await pilot.press("d")
        await pilot.pause(0.3)
        from geusemaker.cli.tui.deploy_screen import DeployScreen

        assert not isinstance(app.screen, InspectScreen)
        assert isinstance(app.screen, DeployScreen)


class FakeDeployExecutor:
    """Emits a short tier-1 event sequence and returns a minimal state."""

    def __init__(self) -> None:
        self.calls = 0
        self.configs: list[object] = []

    def __call__(self, config, on_progress):  # type: ignore[no-untyped-def]
        from geusemaker.cli.progress_events import ProgressEvent

        self.calls += 1
        self.configs.append(config)
        for stage, resource in (("validate", None), ("vpc", "vpc-1"), ("finalize", None)):
            on_progress(ProgressEvent(stage=stage, message=f"{stage} ok", resource_id=resource))
        config_model = DeploymentConfig(stack_name=config.stack_name, tier=config.tier, region=config.region)
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
            config=config_model,
        )


@pytest.mark.asyncio
async def test_d_key_opens_deploy_form_and_launch_runs_executor(tmp_path: Path) -> None:
    from geusemaker.cli.tui.deploy_run_screen import DeployRunScreen
    from geusemaker.cli.tui.deploy_screen import DeployScreen

    executor = FakeDeployExecutor()
    app = _app(tmp_path, stack_name="alpha", deploy_executor=executor)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause(0.3)
        assert isinstance(app.screen, DeployScreen)
        from textual.widgets import Select

        app.screen.query_one("#field-tier", Select).value = "dev"
        await pilot.pause(0.2)
        await pilot.press("ctrl+l")
        await pilot.pause(0.6)
        assert isinstance(app.screen, DeployRunScreen)
        assert executor.calls == 1
        assert executor.configs[0].stack_name == "alpha"
        # Mode keys must be ignored while a deploy run screen is up.
        await pilot.press("i")
        await pilot.pause(0.2)
        assert isinstance(app.screen, DeployRunScreen)
        # Deployment finished (fake executor is instant) -> single escape closes.
        await pilot.press("escape")
        await pilot.pause(0.3)
        assert not isinstance(app.screen, DeployRunScreen)


class GatedDeployExecutor:
    """Emits one event then blocks so the run screen stays live for the test."""

    def __init__(self) -> None:
        self.gate = threading.Event()

    def __call__(self, config, on_progress):  # type: ignore[no-untyped-def]
        from geusemaker.cli.progress_events import ProgressEvent

        on_progress(ProgressEvent(stage="vpc", message="Creating VPC", resource_id="vpc-1"))
        if not self.gate.wait(timeout=10):
            raise RuntimeError("gate never released")
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
            config=DeploymentConfig(stack_name=config.stack_name, tier=config.tier, region=config.region),
        )


@pytest.mark.asyncio
async def test_q_during_live_deploy_does_not_quit_app(tmp_path: Path) -> None:
    """Regression: `q` mid-deploy must arm the run screen's guard, not quit.

    The app-level ("q", "quit") binding would bypass the double-press
    confirmation; the run screen's own `q` binding takes priority.
    """
    from geusemaker.cli.tui.deploy_run_screen import DeployRunScreen
    from geusemaker.cli.tui.deploy_screen import DeployScreen

    executor = GatedDeployExecutor()
    app = _app(tmp_path, stack_name="alpha", deploy_executor=executor)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause(0.3)
        assert isinstance(app.screen, DeployScreen)
        from textual.widgets import Select

        app.screen.query_one("#field-tier", Select).value = "dev"
        await pilot.pause(0.2)
        await pilot.press("ctrl+l")
        await pilot.pause(0.6)
        assert isinstance(app.screen, DeployRunScreen)
        run_screen = app.screen
        # Deploy still running (executor blocked) -> single `q` must NOT quit.
        await pilot.press("q")
        await pilot.pause(0.2)
        assert app.is_running
        assert isinstance(app.screen, DeployRunScreen)
        assert run_screen._dismiss_armed
        # Second `q` detaches cleanly; app keeps running.
        await pilot.press("q")
        await pilot.pause(0.2)
        assert app.is_running
        assert not isinstance(app.screen, DeployRunScreen)
        executor.gate.set()
        await pilot.pause(0.2)


@pytest.mark.asyncio
async def test_q_on_hub_still_quits_app(tmp_path: Path) -> None:
    """The `q` override is scoped to the run screen: the hub still quits on `q`."""
    app = _app(tmp_path)
    async with app.run_test(size=(100, 32)) as pilot:
        await pilot.pause()
        await pilot.press("q")
        await pilot.pause(0.2)
        assert not app.is_running


@pytest.mark.asyncio
async def test_deploy_form_escape_returns_to_hub(tmp_path: Path) -> None:
    from geusemaker.cli.tui.deploy_screen import DeployScreen

    app = _app(tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause(0.3)
        assert isinstance(app.screen, DeployScreen)
        await pilot.press("escape")
        await pilot.pause(0.2)
        assert not isinstance(app.screen, DeployScreen)
