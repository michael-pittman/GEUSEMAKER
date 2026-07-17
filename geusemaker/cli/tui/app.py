"""Full-screen brutalist operations hub."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.widgets import Footer, Header, Label, ListItem, ListView, RichLog, Static

from geusemaker.cli.branding import COMPACT_BANNER, STAGE_GLYPHS
from geusemaker.cli.tui.deploy_run_screen import DeployExecutor, DeployRunScreen, UserdataStreamer
from geusemaker.cli.tui.deploy_screen import DeployScreen
from geusemaker.cli.tui.inspect_screen import InspectScreen
from geusemaker.cli.tui.logs_screen import LogsScreen, LogStreamFactory
from geusemaker.cli.tui.monitor_screen import HealthChecker, MonitorScreen
from geusemaker.cli.tui.splash import SplashScreen

PIPELINE_STAGES = ("validate", "efs", "iam", "ec2", "alb", "cdn", "finalize")


def _stage_glyph_strip(names: tuple[str, ...] = PIPELINE_STAGES) -> str:
    """Render stage glyphs side by side with abbreviated labels underneath."""
    glyphs = [STAGE_GLYPHS[name].splitlines() for name in names]
    rows = ["  ".join(glyph[row] for glyph in glyphs) for row in range(3)]
    labels = "  ".join(
        name.upper()[: len(glyph[0])].ljust(len(glyph[0])) for name, glyph in zip(names, glyphs, strict=True)
    )
    return "\n".join([*rows, labels])


class GeuseMakerApp(App[None]):
    CSS_PATH = "brutalist.tcss"
    TITLE = "GEUSEMAKER"
    SUB_TITLE = "AI INFRASTRUCTURE CONTROL"
    BINDINGS = [
        ("q", "quit", "QUIT"),
        ("h", "show_mode('hub')", "HUB"),
        ("d", "show_mode('deploy')", "DEPLOY"),
        ("m", "show_mode('monitor')", "MONITOR"),
        ("i", "show_mode('inspect')", "INSPECT"),
    ]

    def __init__(
        self,
        *,
        initial_screen: str = "hub",
        stack_name: str | None = None,
        show_splash: bool = True,
        state_dir: Path | None = None,
        health_checker: HealthChecker | None = None,
        deploy_executor: DeployExecutor | None = None,
        userdata_streamer: UserdataStreamer | None = None,
        log_stream_factory: LogStreamFactory | None = None,
    ):
        super().__init__()
        self.initial_screen = initial_screen
        self.stack_name = stack_name
        self.show_splash = show_splash
        self.state_dir = state_dir
        self.health_checker = health_checker
        self.deploy_executor = deploy_executor
        self.userdata_streamer = userdata_streamer
        self.log_stream_factory = log_stream_factory

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="workspace"):
            with Vertical(id="sidebar"):
                yield Static(COMPACT_BANNER, id="mark")
                yield ListView(
                    ListItem(Label("[H] HUB"), id="hub"),
                    ListItem(Label("[D] DEPLOY"), id="deploy"),
                    ListItem(Label("[M] MONITOR"), id="monitor"),
                    ListItem(Label("[I] INSPECT"), id="inspect"),
                    id="nav",
                )
            with Vertical(id="body"):
                yield Static("", id="mode-title")
                yield Static("", id="summary")
                yield RichLog(id="event-log", wrap=True, highlight=True, markup=True, auto_scroll=False)
        yield Footer()

    def on_mount(self) -> None:
        if self.show_splash:
            self.push_screen(SplashScreen(), callback=self._after_splash)
        else:
            self.action_show_mode(self.initial_screen)

    def _after_splash(self, _result: None) -> None:
        self.call_after_refresh(self.action_show_mode, self.initial_screen)

    def _pop_operational_screens(self) -> None:
        """Pop pushed read-only/form screens so mode switches never stack up.

        DeployRunScreen is deliberately excluded — a live deployment is only
        left via its own double-escape guard.
        """
        while isinstance(self.screen, InspectScreen | MonitorScreen | DeployScreen | LogsScreen):
            self.pop_screen()

    def _open_deploy(self) -> None:
        if isinstance(self.screen, DeployScreen):
            return
        self._pop_operational_screens()
        initial_state = {"stack_name": self.stack_name} if self.stack_name else None
        self.push_screen(DeployScreen(initial_state=initial_state))

    def _open_inspect(self, stack_name: str | None = None) -> None:
        if isinstance(self.screen, InspectScreen):
            return
        self._pop_operational_screens()
        self.push_screen(InspectScreen(stack_name=stack_name or self.stack_name, state_dir=self.state_dir))

    def _open_monitor(self, stack_name: str | None) -> None:
        if stack_name is None:
            self.notify("SELECT A STACK IN INSPECT · PRESS M TO MONITOR", severity="warning")
            self._open_inspect()
            return
        self.push_screen(
            MonitorScreen(stack_name=stack_name, state_dir=self.state_dir, health_checker=self.health_checker)
        )

    def action_show_mode(self, mode: str) -> None:
        if isinstance(self.screen, SplashScreen | DeployRunScreen):
            return
        if mode == "deploy":
            self._open_deploy()
            return
        if mode == "inspect":
            self._open_inspect()
            return
        if mode == "monitor":
            if not isinstance(self.screen, InspectScreen):
                # From Inspect, "m" is handled by the screen itself (jump-off message).
                self._pop_operational_screens()
                self._open_monitor(self.stack_name)
            return
        self._pop_operational_screens()
        try:
            body = self.query_one("#body", Vertical)
        except NoMatches:
            return
        title = self.query_one("#mode-title", Static)
        summary = self.query_one("#summary", Static)
        log = self.query_one("#event-log", RichLog)
        title.update(f"MODE · {mode.upper()}")
        message = "SELECT AN OPERATION. READ-ONLY VIEWS DO NOT CONTACT AWS UNTIL REQUESTED."
        summary.update(message)
        log.clear()
        log.write(f"[bold #c8f542][READY][/bold #c8f542] {message}")
        log.write("")
        log.write("[dim]DEPLOY PIPELINE[/dim]")
        log.write(_stage_glyph_strip())
        log.scroll_home(animate=False)
        nav = self.query_one("#nav", ListView)
        nav_ids = [item.id for item in nav.query(ListItem)]
        if mode in nav_ids:
            nav.index = nav_ids.index(mode)
        body.styles.opacity = 0.0
        body.styles.animate("opacity", value=1.0, duration=0.25, easing="out_cubic")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item.id:
            self.action_show_mode(event.item.id)

    def on_inspect_screen_open_monitor(self, message: InspectScreen.OpenMonitor) -> None:
        self._open_monitor(message.stack_name)

    def on_inspect_screen_open_logs(self, message: InspectScreen.OpenLogs) -> None:
        self.push_screen(
            LogsScreen(
                stack_name=message.stack_name,
                state_dir=self.state_dir,
                stream_factory=self.log_stream_factory,
            )
        )

    def on_deploy_screen_launch_requested(self, message: DeployScreen.LaunchRequested) -> None:
        self.push_screen(
            DeployRunScreen(
                config=message.config,
                executor=self.deploy_executor,
                userdata_streamer=self.userdata_streamer,
            )
        )
