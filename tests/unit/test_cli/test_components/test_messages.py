from __future__ import annotations

from io import StringIO

from geusemaker.cli.components import messages
from geusemaker.cli.output.verbosity import (
    VerbosityConsole,
    VerbosityLevel,
    set_verbosity,
)


def test_messages_render_plain_when_not_tty(monkeypatch):
    buffer = StringIO()
    fake_console = VerbosityConsole(file=buffer, force_terminal=False, color_system=None)
    monkeypatch.setattr(messages, "console", fake_console)
    monkeypatch.setattr("geusemaker.cli.components.theme.console", fake_console)

    messages.error("plain text")

    output = buffer.getvalue()
    assert "plain text" in output


def _silent_console(monkeypatch, *, tty: bool) -> StringIO:
    buffer = StringIO()
    fake_console = VerbosityConsole(file=buffer, force_terminal=tty, color_system=None)
    monkeypatch.setattr(messages, "console", fake_console)
    monkeypatch.setattr("geusemaker.cli.components.theme.console", fake_console)
    monkeypatch.setattr(messages, "is_tty", lambda: tty)
    set_verbosity(VerbosityLevel.SILENT)
    return buffer


def test_error_shown_under_silent_non_tty(monkeypatch):
    """Non-TTY (string) path: an error must still be emitted under --silent."""
    try:
        buffer = _silent_console(monkeypatch, tty=False)
        messages.error("boom happened")
        assert "boom happened" in buffer.getvalue()
    finally:
        set_verbosity(VerbosityLevel.NORMAL)


def test_error_shown_under_silent_tty_panel(monkeypatch):
    """TTY (Panel) path: the original bug. An error Panel must show under --silent."""
    try:
        buffer = _silent_console(monkeypatch, tty=True)
        messages.error("panel boom")
        assert "panel boom" in buffer.getvalue()
    finally:
        set_verbosity(VerbosityLevel.NORMAL)


def test_info_suppressed_under_silent_non_tty(monkeypatch):
    """Non-TTY (string) path: info is suppressed under --silent."""
    try:
        buffer = _silent_console(monkeypatch, tty=False)
        messages.info("just fyi")
        assert buffer.getvalue().strip() == ""
    finally:
        set_verbosity(VerbosityLevel.NORMAL)


def test_info_suppressed_under_silent_tty_panel(monkeypatch):
    """TTY (Panel) path: info Panel is suppressed under --silent."""
    try:
        buffer = _silent_console(monkeypatch, tty=True)
        messages.info("just fyi panel")
        assert buffer.getvalue().strip() == ""
    finally:
        set_verbosity(VerbosityLevel.NORMAL)
