"""Scrollback-friendly stage rendering."""

import os

from rich.text import Text

from geusemaker.cli import console, is_silent
from geusemaker.cli.branding import STAGE_GLYPHS
from geusemaker.cli.output import is_machine_output
from geusemaker.cli.progress_events import ProgressEvent


def render_stage(event: ProgressEvent, *, unicode: bool = True) -> Text:
    label = f"STAGE · {event.stage.upper()}"
    if not unicode:
        return Text(f"[{event.stage.upper()}] {event.message}")
    lines = STAGE_GLYPHS[event.stage].splitlines()
    return Text("\n".join([*lines[:-1], f"{lines[-1]}  {label}", f"      {event.message}"]))


def print_stage(event: ProgressEvent) -> None:
    if is_silent() or is_machine_output() or not console.is_terminal:
        return
    unicode = not os.environ.get("NO_COLOR") and os.environ.get("TERM") != "dumb"
    console.print(render_stage(event, unicode=unicode), verbosity="info")


__all__ = ["print_stage", "render_stage"]
