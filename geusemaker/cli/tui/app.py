"""Full-screen brutalist operations hub."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Label, ListItem, ListView, RichLog, Static

from geusemaker.cli.branding import COMPACT_BANNER


class GeuseMakerApp(App[None]):
    CSS_PATH = "brutalist.tcss"
    TITLE = "GEUSEMAKER"
    SUB_TITLE = "AI INFRASTRUCTURE CONTROL"
    BINDINGS = [
        ("q", "quit", "QUIT"),
        ("d", "show_mode('deploy')", "DEPLOY"),
        ("m", "show_mode('monitor')", "MONITOR"),
        ("i", "show_mode('inspect')", "INSPECT"),
    ]

    def __init__(self, *, initial_screen: str = "hub", stack_name: str | None = None):
        super().__init__()
        self.initial_screen = initial_screen
        self.stack_name = stack_name

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="workspace"):
            with Vertical(id="sidebar"):
                yield Static(COMPACT_BANNER, id="mark")
                yield ListView(
                    ListItem(Label("[D] DEPLOY"), id="deploy"),
                    ListItem(Label("[M] MONITOR"), id="monitor"),
                    ListItem(Label("[I] INSPECT"), id="inspect"),
                    id="nav",
                )
            with Vertical(id="body"):
                yield Static("", id="mode-title")
                yield Static("", id="summary")
                yield RichLog(id="event-log", wrap=True, highlight=True, markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self.action_show_mode(self.initial_screen)

    def action_show_mode(self, mode: str) -> None:
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
        summary.update(messages.get(mode, messages["hub"]))
        log.clear()
        log.write(f"[bold #c8f542][READY][/bold #c8f542] {messages.get(mode, messages['hub'])}")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item.id:
            self.action_show_mode(event.item.id)
