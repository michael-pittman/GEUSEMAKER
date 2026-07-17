"""Pilot tests for the seam-driven Deploy configuration form.

Zero AWS/network usage: every assertion runs against the ConfigBuilder seam
and local widgets only.
"""

from __future__ import annotations

import pytest

pytest.importorskip("textual")

from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

from textual.app import App  # noqa: E402
from textual.containers import Vertical  # noqa: E402
from textual.pilot import Pilot  # noqa: E402
from textual.widgets import Input, Select, Static  # noqa: E402

import geusemaker.cli.tui.deploy_screen as deploy_screen_module  # noqa: E402
from geusemaker.cli.configuration import ConfigBuilder, DeploymentDraft  # noqa: E402
from geusemaker.cli.tui.deploy_screen import DeployScreen  # noqa: E402
from geusemaker.models import DeploymentConfig  # noqa: E402

TCSS_PATH = Path(deploy_screen_module.__file__).with_name("brutalist.tcss")

VALID_STATE: dict[str, Any] = {
    "stack_name": "quick-dev",
    "tier": "dev",
    "setup_mode": "quick",
    "workload": "cpu",
    "instance_type": "t3.medium",
    "region": "us-east-1",
}


class HostApp(App[None]):
    """Minimal host that provides the $gm-* tokens and records launch requests."""

    CSS_PATH = TCSS_PATH

    def __init__(self, deploy: DeployScreen) -> None:
        super().__init__()
        self._deploy = deploy
        self.launches: list[DeploymentConfig] = []

    def on_mount(self) -> None:
        self.push_screen(self._deploy)

    def on_deploy_screen_launch_requested(self, message: DeployScreen.LaunchRequested) -> None:
        self.launches.append(message.config)


async def _settle(pilot: Pilot[None]) -> None:
    await pilot.pause()
    await pilot.pause()


def _rendered(app: App[None], selector: str) -> str:
    """Render a Static widget's content to plain text."""
    from rich.console import Console

    static = app.screen.query_one(selector, Static)
    console = Console(width=200, no_color=True, highlight=False)
    with console.capture() as capture:
        console.print(static.content)
    return capture.get()


def _row_visible(app: App[None], field: str) -> bool:
    return bool(app.screen.query_one(f"#field-row-{field}", Vertical).display)


@pytest.mark.asyncio
async def test_quick_mode_hides_networking_and_ami_fields_until_advanced() -> None:
    screen = DeployScreen(initial_state=dict(VALID_STATE))
    app = HostApp(screen)
    async with app.run_test() as pilot:
        await _settle(pilot)
        for field in ("vpc_id", "subnet_id", "security_group_id", "efs_id", "os_type", "ami_id", "use_spot"):
            assert not _row_visible(app, field), field
        assert not app.screen.query_one("#group-title-networking", Static).display
        for field in ("stack_name", "tier", "region", "instance_type", "enable_https"):
            assert _row_visible(app, field), field
        # Flipping setup_mode to advanced re-evaluates visibility.
        app.screen.query_one("#field-setup_mode", Select).value = "advanced"
        await _settle(pilot)
        for field in ("vpc_id", "subnet_id", "security_group_id", "efs_id", "os_type", "ami_id", "use_spot"):
            assert _row_visible(app, field), field
        assert app.screen.query_one("#group-title-networking", Static).display
        assert screen.builder.draft.setup_mode == "advanced"


@pytest.mark.asyncio
async def test_editing_field_updates_draft_and_preview() -> None:
    screen = DeployScreen(initial_state=dict(VALID_STATE))
    app = HostApp(screen)
    async with app.run_test() as pilot:
        await _settle(pilot)
        app.screen.query_one("#field-stack_name", Input).value = "edited-stack"
        await _settle(pilot)
        assert screen.builder.draft.stack_name == "edited-stack"
        assert "edited-stack" in _rendered(app, "#deploy-preview")


@pytest.mark.asyncio
async def test_invalid_coercion_shows_field_error_and_leaves_draft_unset() -> None:
    screen = DeployScreen(initial_state=dict(VALID_STATE))
    app = HostApp(screen)
    async with app.run_test() as pilot:
        await _settle(pilot)
        app.screen.query_one("#field-rollback_timeout_minutes", Input).value = "not-a-number"
        await _settle(pilot)
        error_slot = app.screen.query_one("#field-error-rollback_timeout_minutes", Static)
        assert error_slot.display
        assert "INVALID" in _rendered(app, "#field-error-rollback_timeout_minutes")
        assert screen.builder.draft.rollback_timeout_minutes is None


@pytest.mark.asyncio
async def test_launch_with_invalid_draft_shows_errors_and_posts_nothing() -> None:
    screen = DeployScreen(initial_state={"stack_name": "9bad-start", "tier": "dev"})
    app = HostApp(screen)
    async with app.run_test() as pilot:
        await _settle(pilot)
        await pilot.press("ctrl+l")
        await _settle(pilot)
        assert app.launches == []
        validation = _rendered(app, "#deploy-validation")
        assert "STACK_NAME" in validation
        assert "LAUNCH BLOCKED" in _rendered(app, "#deploy-status")


@pytest.mark.asyncio
async def test_launch_with_valid_draft_posts_builder_equivalent_config() -> None:
    screen = DeployScreen(initial_state=dict(VALID_STATE))
    app = HostApp(screen)
    async with app.run_test() as pilot:
        await _settle(pilot)
        await pilot.press("ctrl+l")
        await _settle(pilot)
        expected = ConfigBuilder.from_initial_state(dict(VALID_STATE)).build()
        assert app.launches == [expected]
        assert "VALID · READY TO LAUNCH" in _rendered(app, "#deploy-validation")


@pytest.mark.asyncio
async def test_export_yaml_writes_reloadable_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    screen = DeployScreen(initial_state=dict(VALID_STATE))
    app = HostApp(screen)
    async with app.run_test() as pilot:
        await _settle(pilot)
        await pilot.press("ctrl+e")
        await _settle(pilot)
        exported = tmp_path / "quick-dev.yaml"
        assert exported.exists()
        assert "EXPORTED" in _rendered(app, "#deploy-status")
        reloaded = ConfigBuilder.from_yaml(exported).build()
        assert reloaded == ConfigBuilder.from_initial_state(dict(VALID_STATE)).build()


@pytest.mark.asyncio
async def test_export_with_invalid_draft_is_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    screen = DeployScreen(initial_state={})
    app = HostApp(screen)
    async with app.run_test() as pilot:
        await _settle(pilot)
        await pilot.press("ctrl+e")
        await _settle(pilot)
        assert list(tmp_path.iterdir()) == []
        assert "EXPORT BLOCKED" in _rendered(app, "#deploy-status")


@pytest.mark.asyncio
async def test_import_yaml_seeds_form(tmp_path: Path) -> None:
    seed = tmp_path / "seed.yaml"
    seed.write_text(ConfigBuilder(DeploymentDraft(**VALID_STATE)).to_yaml(), encoding="utf-8")
    screen = DeployScreen(initial_state={})
    app = HostApp(screen)
    async with app.run_test() as pilot:
        await _settle(pilot)
        await pilot.press("ctrl+o")
        await _settle(pilot)
        path_input = app.screen.query_one("#deploy-import-path", Input)
        assert path_input.display
        path_input.value = str(seed)
        path_input.focus()
        await _settle(pilot)
        await pilot.press("enter")
        await _settle(pilot)
        assert screen.builder.draft.stack_name == "quick-dev"
        assert screen.builder.draft.tier == "dev"
        assert app.screen.query_one("#field-stack_name", Input).value == "quick-dev"
        assert "IMPORTED" in _rendered(app, "#deploy-status")


@pytest.mark.asyncio
async def test_import_missing_file_shows_configuration_error(tmp_path: Path) -> None:
    screen = DeployScreen(initial_state={})
    app = HostApp(screen)
    async with app.run_test() as pilot:
        await _settle(pilot)
        await pilot.press("ctrl+o")
        await _settle(pilot)
        path_input = app.screen.query_one("#deploy-import-path", Input)
        path_input.value = str(tmp_path / "does-not-exist.yaml")
        path_input.focus()
        await _settle(pilot)
        await pilot.press("enter")
        await _settle(pilot)
        assert "IMPORT FAILED" in _rendered(app, "#deploy-status")
        assert screen.builder.draft.stack_name is None


@pytest.mark.asyncio
async def test_config_path_constructor_seeds_form(tmp_path: Path) -> None:
    seed = tmp_path / "seed.yaml"
    seed.write_text(ConfigBuilder(DeploymentDraft(**VALID_STATE)).to_yaml(), encoding="utf-8")
    screen = DeployScreen(config_path=seed)
    app = HostApp(screen)
    async with app.run_test() as pilot:
        await _settle(pilot)
        assert screen.builder.draft.stack_name == "quick-dev"
        assert app.screen.query_one("#field-stack_name", Input).value == "quick-dev"
        assert app.screen.query_one("#field-tier", Select).value == "dev"


@pytest.mark.asyncio
async def test_escape_dismisses_screen() -> None:
    screen = DeployScreen(initial_state=dict(VALID_STATE))
    app = HostApp(screen)
    async with app.run_test() as pilot:
        await _settle(pilot)
        assert app.screen is screen
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen is not screen
