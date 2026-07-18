"""Shared chrome for the operational TUI screens: Footer + `?` help overlay.

The hub :class:`~geusemaker.cli.tui.app.GeuseMakerApp` composes a ``Footer`` and
owns the global navigation keys, but the pushed operational screens replace that
chrome. Without a ``Footer`` their ``BINDINGS`` (BACK, STOP STREAM, LAUNCH…) have
nowhere to render as key hints, and the documented ``?`` help action was never
implemented.

:class:`OperationalScreen` gives every operational screen a persistent footer
(each screen still yields its own ``Footer`` in ``compose`` so the widget is a
top-level sibling of that screen's root container) and a shared ``?``/``help``
action. Textual merges ``BINDINGS`` across the MRO, so the ``?`` binding declared
here is inherited by every subclass and shows up in each screen's Footer.

The ``?`` action opens :class:`HelpModal`, a dismissible brutalist overlay that
lists the invoking screen's own key actions plus the hub's global navigation
keys — both derived at runtime from the live ``BINDINGS`` so the overlay can
never drift out of sync with the actual key map.
"""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical, VerticalScroll
from textual.dom import DOMNode
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Static

from geusemaker.cli.tui.theme import GM_MUTED, GM_SIGNAL, GM_VARIABLES_TCSS

_KEY_COLUMN_WIDTH = 8

#: Friendly display for key names that are ugly when merely upper-cased.
_KEY_DISPLAY: dict[str, str] = {
    "question_mark": "?",
    "escape": "ESC",
}


def _key_label(key: str) -> str:
    return _KEY_DISPLAY.get(key, key.upper())


def _as_binding(entry: BindingType) -> Binding:
    """Normalize a ``BINDINGS`` entry (tuple or ``Binding``) to a ``Binding``."""
    if isinstance(entry, Binding):
        return entry
    return Binding(*entry)


def collect_bindings(node: DOMNode) -> list[tuple[str, str]]:
    """Collect ``(key, description)`` for a node's shown, described bindings.

    Walks the node's class MRO exactly like Textual's own binding merge so the
    result matches what the Footer renders: later (more derived) classes win on
    key collisions, and only ``show=True`` bindings with a description appear.
    """
    merged: dict[str, str] = {}
    for base in reversed(type(node).__mro__):
        for entry in base.__dict__.get("BINDINGS", []):
            binding = _as_binding(entry)
            if not binding.show or not binding.description:
                merged.pop(binding.key, None)
                continue
            merged[binding.key] = binding.description
    return list(merged.items())


def _format_rows(bindings: list[tuple[str, str]]) -> str:
    """Render ``(key, description)`` pairs as brutalist ``KEY  DESCRIPTION`` rows."""
    if not bindings:
        return f"[{GM_MUTED}]— NONE —[/{GM_MUTED}]"
    rows = []
    for key, description in bindings:
        label = _key_label(key).ljust(_KEY_COLUMN_WIDTH)
        rows.append(f"[bold {GM_SIGNAL}]{label}[/bold {GM_SIGNAL}] {description}")
    return "\n".join(rows)


class HelpModal(ModalScreen[None]):
    """Dismissible key-map overlay for an operational screen.

    Lists the invoking screen's own actions and the hub's global navigation
    keys. Dismissed with ``escape``, ``?``, or the CLOSE button.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "dismiss_help", "CLOSE"),
        Binding("question_mark", "dismiss_help", "CLOSE", show=False),
    ]

    DEFAULT_CSS = (
        GM_VARIABLES_TCSS
        + """
    HelpModal {
        align: center middle;
        background: $gm-surface 70%;
    }
    #help-panel {
        width: 64;
        max-width: 90%;
        height: auto;
        max-height: 80%;
        background: $gm-panel;
        border: heavy $gm-signal;
        padding: 1 2;
    }
    #help-title {
        height: 3;
        padding: 0 1;
        border: heavy $gm-signal;
        color: $gm-signal;
        text-style: bold;
    }
    #help-scroll {
        height: auto;
        max-height: 20;
        margin-top: 1;
    }
    .help-section {
        margin-top: 1;
        color: $gm-muted;
        text-style: bold;
    }
    .help-rows {
        padding: 0 1;
        color: $gm-ink;
    }
    #help-close {
        margin-top: 1;
        width: 1fr;
    }
    """
    )

    def __init__(
        self,
        *,
        title: str,
        screen_bindings: list[tuple[str, str]],
        global_bindings: list[tuple[str, str]],
    ) -> None:
        super().__init__()
        self._title = title
        self._screen_bindings = screen_bindings
        self._global_bindings = global_bindings

    def compose(self) -> ComposeResult:
        with Vertical(id="help-panel"):
            yield Static(f"HELP · {self._title}", id="help-title")
            with VerticalScroll(id="help-scroll"):
                yield Static("THIS SCREEN", classes="help-section")
                yield Static(
                    _format_rows(self._screen_bindings),
                    id="help-screen-bindings",
                    classes="help-rows",
                )
                yield Static("GLOBAL NAVIGATION", classes="help-section")
                yield Static(
                    _format_rows(self._global_bindings),
                    id="help-global-bindings",
                    classes="help-rows",
                )
            yield Button("CLOSE  ESC", id="help-close")

    def action_dismiss_help(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "help-close":
            self.dismiss(None)


class OperationalScreen(Screen[None]):
    """Base for pushed operational screens: persistent footer + ``?`` help.

    Subclasses still yield their own ``Footer`` in ``compose`` (so it is a
    top-level sibling of their root container); this base contributes the
    inherited ``?`` binding and the ``help`` action that opens :class:`HelpModal`.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("question_mark", "help", "HELP"),
    ]

    @property
    def help_title(self) -> str:
        """Human label for the help overlay, derived from the class name."""
        name = type(self).__name__.removesuffix("Screen")
        # Split CamelCase into spaced words, then uppercase (e.g. DeployRun -> DEPLOY RUN).
        spaced = "".join(f" {char}" if char.isupper() else char for char in name).strip()
        return spaced.upper() or "SCREEN"

    def action_help(self) -> None:
        """Open the key-map overlay for this screen (guarded against re-entry)."""
        if isinstance(self.app.screen, HelpModal):
            return
        self.app.push_screen(
            HelpModal(
                title=self.help_title,
                screen_bindings=collect_bindings(self),
                global_bindings=collect_bindings(self.app),
            )
        )


__all__ = ["HelpModal", "OperationalScreen", "collect_bindings"]
