"""Disk-only Inspect screen: local stack picker + resource inventory.

Reads deployment state exclusively through :class:`StateManager` — this
screen never contacts AWS. Live views (logs, monitor) are jump-offs: the
screen posts :class:`InspectScreen.OpenLogs` / :class:`InspectScreen.OpenMonitor`
messages and the hosting app decides what to do with them.
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Group, RenderableType
from rich.table import Table
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Footer, Label, ListItem, ListView, Static

from geusemaker.cli.display.listing import render_inspection
from geusemaker.cli.tui._base import OperationalScreen
from geusemaker.cli.tui.theme import GM_VARIABLES_TCSS
from geusemaker.infra.state import StateManager
from geusemaker.models import DeploymentState

STACK_ITEM_PREFIX = "stack-"


class InspectScreen(OperationalScreen):
    """Stack picker + resource inventory backed by local state files only."""

    BINDINGS = [
        ("escape", "close", "BACK"),
        ("l", "open_logs", "LOGS"),
        ("m", "open_monitor", "MONITOR"),
    ]

    # $gm-* tokens come from theme.GM_VARIABLES_TCSS (DEFAULT_CSS cannot see
    # app-stylesheet variables in Textual 8.2.8).
    DEFAULT_CSS = (
        GM_VARIABLES_TCSS
        + """
    InspectScreen {
        background: $gm-surface;
        color: $gm-ink;
    }
    #inspect-workspace {
        height: 1fr;
    }
    #inspect-stacks {
        width: 44;
        background: $gm-panel;
        border: heavy $gm-rule;
    }
    #inspect-stacks-title {
        height: 3;
        padding: 0 1;
        border: heavy $gm-signal;
        color: $gm-signal;
        text-style: bold;
    }
    #inspect-empty {
        display: none;
        padding: 1;
        color: $gm-warn;
        text-style: bold;
    }
    #inspect-stack-list {
        background: $gm-panel;
        border: none;
    }
    #inspect-stack-list ListItem {
        height: auto;
        padding: 0 1;
        color: $gm-ink;
    }
    #inspect-detail {
        width: 1fr;
        border: heavy $gm-rule;
        padding: 1 2;
    }
    #inspect-detail-title {
        height: 3;
        padding: 0 1;
        border: heavy $gm-signal;
        color: $gm-signal;
        text-style: bold;
    }
    #inspect-detail-body {
        padding: 1 0;
    }
    """
    )

    class OpenLogs(Message):
        """Request the hosting app to open the logs view for a stack."""

        def __init__(self, stack_name: str) -> None:
            self.stack_name = stack_name
            super().__init__()

    class OpenMonitor(Message):
        """Request the hosting app to open the monitor view for a stack."""

        def __init__(self, stack_name: str) -> None:
            self.stack_name = stack_name
            super().__init__()

    def __init__(
        self,
        *,
        stack_name: str | None = None,
        state_dir: Path | None = None,
    ) -> None:
        super().__init__()
        self._preselect = stack_name
        self._state_dir = state_dir
        self._states: list[DeploymentState] = []
        self._selected: DeploymentState | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="inspect-workspace"):
            with Vertical(id="inspect-stacks"):
                yield Static("STACKS · LOCAL STATE", id="inspect-stacks-title")
                yield Static("", id="inspect-empty")
                yield ListView(id="inspect-stack-list")
            with VerticalScroll(id="inspect-detail"):
                yield Static("INVENTORY", id="inspect-detail-title")
                yield Static("LOADING LOCAL STATE…", id="inspect-detail-body")
        yield Footer()

    def on_mount(self) -> None:
        self._load_stacks()

    @work(exclusive=True)
    async def _load_stacks(self) -> None:
        """Load deployment states from disk. ZERO AWS calls."""
        manager = StateManager(base_path=self._state_dir)
        self._states = await manager.list_deployments()
        self._populate(manager.base_path)

    def _populate(self, base_path: Path) -> None:
        list_view = self.query_one("#inspect-stack-list", ListView)
        empty = self.query_one("#inspect-empty", Static)
        if not self._states:
            self._show_empty_state(base_path, list_view, empty)
            return
        empty.display = False
        list_view.display = True
        for state in self._states:
            item = ListItem(
                Label(self._stack_label(state), markup=False),
                id=f"{STACK_ITEM_PREFIX}{state.stack_name}",
            )
            list_view.append(item)
        index = 0
        if self._preselect is not None:
            for position, state in enumerate(self._states):
                if state.stack_name == self._preselect:
                    index = position
                    break
        list_view.index = index
        list_view.focus()
        self._show_detail(self._states[index])

    def _show_empty_state(self, base_path: Path, list_view: ListView, empty: Static) -> None:
        empty.update(f"NO STACKS FOUND · {base_path}")
        empty.display = True
        list_view.display = False
        self.query_one("#inspect-detail-title", Static).update("INVENTORY · NONE")
        self.query_one("#inspect-detail-body", Static).update(
            "NO LOCAL DEPLOYMENT STATE.\n"
            "RUN `geusemaker deploy` OR `geusemaker list --discover-from-aws` TO POPULATE IT."
        )

    @staticmethod
    def _stack_label(state: DeploymentState) -> str:
        tier = state.config.tier.upper()
        region = state.config.region.upper()
        workload = state.config.effective_workload.upper()
        return f"{state.stack_name}\nTIER {tier} · {region} · {workload}"

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.list_view.id != "inspect-stack-list":
            return
        index = event.list_view.index
        if index is None or not 0 <= index < len(self._states):
            return
        self._show_detail(self._states[index])

    def _show_detail(self, state: DeploymentState) -> None:
        self._selected = state
        self.query_one("#inspect-detail-title", Static).update(f"INVENTORY · {state.stack_name.upper()}")
        self.query_one("#inspect-detail-body", Static).update(self._inventory(state))

    def _inventory(self, state: DeploymentState) -> RenderableType:
        return Group(render_inspection(state), "", self._platform_table(state))

    @staticmethod
    def _platform_table(state: DeploymentState) -> Table:
        table = Table(title="PLATFORM + OPTIONAL RESOURCES", show_lines=False)
        table.add_column("FIELD")
        table.add_column("VALUE")
        rows: list[tuple[str, str]] = [
            ("WORKLOAD", state.config.effective_workload),
            ("INSTANCE TYPE", state.cost.instance_type),
            ("SPOT", "yes" if state.cost.is_spot else "no"),
        ]
        if state.cost.spot_price_per_hour is not None:
            rows.append(("SPOT $/HR", str(state.cost.spot_price_per_hour)))
        rows.append(("ON-DEMAND $/HR", str(state.cost.on_demand_price_per_hour)))
        optional: list[tuple[str, str | None]] = [
            ("IAM ROLE", state.iam_role_name),
            ("IAM INSTANCE PROFILE", state.iam_instance_profile_name),
            ("ALB ARN", state.alb_arn),
            ("ALB DNS", state.alb_dns),
            ("TARGET GROUP", state.target_group_arn),
            ("CLOUDFRONT ID", state.cloudfront_id),
            ("CLOUDFRONT DOMAIN", state.cloudfront_domain),
            ("HTTPS ENDPOINT", state.https_endpoint),
            ("CERTIFICATE", state.certificate_arn),
        ]
        rows.extend((field, value) for field, value in optional if value)
        for field, value in rows:
            table.add_row(field, value)
        return table

    def action_close(self) -> None:
        self.dismiss(None)

    def action_open_logs(self) -> None:
        if self._selected is not None:
            self.post_message(self.OpenLogs(self._selected.stack_name))

    def action_open_monitor(self) -> None:
        if self._selected is not None:
            self.post_message(self.OpenMonitor(self._selected.stack_name))


__all__ = ["InspectScreen"]
