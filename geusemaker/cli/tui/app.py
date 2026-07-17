"""Full-screen brutalist operations hub."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.widgets import Footer, Header, Label, ListItem, ListView, RichLog, Static

from geusemaker.cli.branding import COMPACT_BANNER, DEPLOY_BANNER, STAGE_GLYPHS
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
    ):
        super().__init__()
        self.initial_screen = initial_screen
        self.stack_name = stack_name
        self.show_splash = show_splash

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

    def action_show_mode(self, mode: str) -> None:
        try:
            body = self.query_one("#body", Vertical)
        except NoMatches:
            # Splash screen is still on top of the stack; ignore mode keys.
            return
        title = self.query_one("#mode-title", Static)
        summary = self.query_one("#summary", Static)
        log = self.query_one("#event-log", RichLog)
        title.update(f"MODE · {mode.upper()}")
        stack = f" · STACK {self.stack_name}" if self.stack_name else ""
        messages = {
            "hub": "SELECT AN OPERATION. READ-ONLY VIEWS DO NOT CONTACT AWS UNTIL REQUESTED.",
            "deploy": "DEPLOY CHECKLIST READY · IMPORT A CONFIG OR USE THE DEFAULT WIZARD.",
            "monitor": f"HEALTH + EVENT STREAM{stack}",
            "inspect": f"LOCAL RESOURCE INVENTORY{stack}",
        }
        message = messages.get(mode, messages["hub"])
        summary.update(message)
        log.clear()
        if mode == "deploy":
            log.write(DEPLOY_BANNER)
        else:
            log.write(f"[bold #c8f542][READY][/bold #c8f542] {message}")
            if mode == "hub":
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
