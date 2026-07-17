"""Pilot tests for the disk-only Inspect screen."""

from __future__ import annotations

import pytest

pytest.importorskip("textual")

from datetime import UTC, datetime  # noqa: E402
from decimal import Decimal  # noqa: E402
from pathlib import Path  # noqa: E402

from textual.app import App  # noqa: E402
from textual.pilot import Pilot  # noqa: E402
from textual.widgets import ListItem, ListView, Static  # noqa: E402

import geusemaker.cli.tui.inspect_screen as inspect_screen_module  # noqa: E402
from geusemaker.cli.tui.inspect_screen import InspectScreen  # noqa: E402
from geusemaker.infra.state import StateManager  # noqa: E402
from geusemaker.models import CostTracking, DeploymentConfig, DeploymentState  # noqa: E402

TCSS_PATH = Path(inspect_screen_module.__file__).with_name("brutalist.tcss")


def _state(
    name: str,
    tier: str = "dev",
    region: str = "us-east-1",
    **overrides: object,
) -> DeploymentState:
    config = DeploymentConfig(stack_name=name, tier=tier, region=region)
    cost = CostTracking(
        instance_type="t3.medium",
        is_spot=True,
        on_demand_price_per_hour=Decimal("0.04"),
        estimated_monthly_cost=Decimal("25.0"),
    )
    defaults: dict[str, object] = {
        "stack_name": name,
        "status": "running",
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "vpc_id": f"vpc-{name}",
        "subnet_ids": [f"subnet-{name}"],
        "security_group_id": f"sg-{name}",
        "efs_id": f"fs-{name}",
        "efs_mount_target_id": f"fsmt-{name}",
        "instance_id": f"i-{name}",
        "keypair_name": f"kp-{name}",
        "public_ip": "1.2.3.4",
        "private_ip": "10.0.0.1",
        "n8n_url": "http://1.2.3.4:5678",
        "cost": cost,
        "config": config,
    }
    defaults.update(overrides)
    return DeploymentState(**defaults)  # type: ignore[arg-type]


def _seed(tmp_path: Path, *states: DeploymentState) -> None:
    manager = StateManager(base_path=tmp_path)
    for state in states:
        manager.save_deployment_sync(state)


class HostApp(App[None]):
    """Minimal host that provides the $gm-* tokens and records jump-off messages."""

    CSS_PATH = TCSS_PATH

    def __init__(self, inspect: InspectScreen) -> None:
        super().__init__()
        self._inspect = inspect
        self.monitor_requests: list[str] = []
        self.logs_requests: list[str] = []

    def on_mount(self) -> None:
        self.push_screen(self._inspect)

    def on_inspect_screen_open_monitor(self, message: InspectScreen.OpenMonitor) -> None:
        self.monitor_requests.append(message.stack_name)

    def on_inspect_screen_open_logs(self, message: InspectScreen.OpenLogs) -> None:
        self.logs_requests.append(message.stack_name)


async def _settle(pilot: Pilot[None]) -> None:
    """Wait for the state-loading worker to finish and the UI to repaint."""
    await pilot.pause()
    await pilot.app.workers.wait_for_complete()
    await pilot.pause()


def _rendered(app: App[None], selector: str) -> str:
    """Render a Static widget's content to plain text."""
    from rich.console import Console

    static = app.screen.query_one(selector, Static)
    console = Console(width=200, no_color=True, highlight=False)
    with console.capture() as capture:
        console.print(static.content)
    return capture.get()


@pytest.mark.asyncio
async def test_lists_stacks_with_tier_region_workload(tmp_path: Path) -> None:
    _seed(tmp_path, _state("alpha"), _state("beta", tier="gpu", region="us-west-2"))
    screen = InspectScreen(state_dir=tmp_path)
    app = HostApp(screen)
    async with app.run_test() as pilot:
        await _settle(pilot)
        list_view = app.screen.query_one("#inspect-stack-list", ListView)
        items = list(list_view.query(ListItem))
        assert {item.id for item in items} == {"stack-alpha", "stack-beta"}
        labels = "\n".join(str(item.query_one("Label").content) for item in items)
        assert "TIER DEV · US-EAST-1 · CPU" in labels
        assert "TIER GPU · US-WEST-2 · GPU" in labels


@pytest.mark.asyncio
async def test_detail_shows_resource_ids(tmp_path: Path) -> None:
    _seed(
        tmp_path,
        _state(
            "prod",
            tier="automation",
            alb_arn="arn:aws:elasticloadbalancing:us-east-1:123:loadbalancer/app/prod/abc",
            alb_dns="prod-alb.us-east-1.elb.amazonaws.com",
            cloudfront_id="E2EXAMPLE",
            cloudfront_domain="d111111abcdef8.cloudfront.net",
        ),
    )
    screen = InspectScreen(state_dir=tmp_path)
    app = HostApp(screen)
    async with app.run_test() as pilot:
        await _settle(pilot)
        title = _rendered(app, "#inspect-detail-title")
        assert "INVENTORY · PROD" in title
        body = _rendered(app, "#inspect-detail-body")
        assert "vpc-prod" in body
        assert "subnet-prod" in body
        assert "sg-prod" in body
        assert "fs-prod" in body
        assert "i-prod" in body
        assert "prod-alb.us-east-1.elb.amazonaws.com" in body
        assert "E2EXAMPLE" in body
        assert "25.0" in body


@pytest.mark.asyncio
async def test_highlighting_second_stack_updates_detail(tmp_path: Path) -> None:
    _seed(tmp_path, _state("alpha"), _state("beta"))
    screen = InspectScreen(state_dir=tmp_path)
    app = HostApp(screen)
    async with app.run_test() as pilot:
        await _settle(pilot)
        list_view = app.screen.query_one("#inspect-stack-list", ListView)
        first = _rendered(app, "#inspect-detail-body")
        await pilot.press("down")
        await pilot.pause()
        second = _rendered(app, "#inspect-detail-body")
        items = list(list_view.query(ListItem))
        assert list_view.index == 1
        highlighted = items[1].id
        assert highlighted is not None
        expected = highlighted.removeprefix("stack-")
        assert f"i-{expected}" in second
        assert first != second


@pytest.mark.asyncio
async def test_preselects_requested_stack(tmp_path: Path) -> None:
    _seed(tmp_path, _state("alpha"), _state("beta"))
    screen = InspectScreen(stack_name="beta", state_dir=tmp_path)
    app = HostApp(screen)
    async with app.run_test() as pilot:
        await _settle(pilot)
        title = _rendered(app, "#inspect-detail-title")
        assert "INVENTORY · BETA" in title
        body = _rendered(app, "#inspect-detail-body")
        assert "i-beta" in body


@pytest.mark.asyncio
async def test_empty_state_is_explicit(tmp_path: Path) -> None:
    screen = InspectScreen(state_dir=tmp_path)
    app = HostApp(screen)
    async with app.run_test() as pilot:
        await _settle(pilot)
        empty = app.screen.query_one("#inspect-empty", Static)
        assert empty.display
        message = _rendered(app, "#inspect-empty")
        assert "NO STACKS FOUND" in message
        assert str(tmp_path) in message
        list_view = app.screen.query_one("#inspect-stack-list", ListView)
        assert not list_view.display
        assert "INVENTORY · NONE" in _rendered(app, "#inspect-detail-title")


@pytest.mark.asyncio
async def test_escape_dismisses_screen(tmp_path: Path) -> None:
    _seed(tmp_path, _state("alpha"))
    screen = InspectScreen(state_dir=tmp_path)
    app = HostApp(screen)
    async with app.run_test() as pilot:
        await _settle(pilot)
        assert app.screen is screen
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen is not screen


@pytest.mark.asyncio
async def test_m_posts_open_monitor_for_selected_stack(tmp_path: Path) -> None:
    _seed(tmp_path, _state("alpha"))
    screen = InspectScreen(state_dir=tmp_path)
    app = HostApp(screen)
    async with app.run_test() as pilot:
        await _settle(pilot)
        await pilot.press("m")
        await pilot.pause()
        assert app.monitor_requests == ["alpha"]


@pytest.mark.asyncio
async def test_l_posts_open_logs_for_selected_stack(tmp_path: Path) -> None:
    _seed(tmp_path, _state("alpha"))
    screen = InspectScreen(state_dir=tmp_path)
    app = HostApp(screen)
    async with app.run_test() as pilot:
        await _settle(pilot)
        await pilot.press("l")
        await pilot.pause()
        assert app.logs_requests == ["alpha"]


@pytest.mark.asyncio
async def test_jump_off_keys_are_noops_with_no_stacks(tmp_path: Path) -> None:
    screen = InspectScreen(state_dir=tmp_path)
    app = HostApp(screen)
    async with app.run_test() as pilot:
        await _settle(pilot)
        await pilot.press("m", "l")
        await pilot.pause()
        assert app.monitor_requests == []
        assert app.logs_requests == []
