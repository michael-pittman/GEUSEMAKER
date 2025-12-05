from __future__ import annotations

from io import StringIO

from rich.console import Console

from geusemaker.cli.components import messages


def test_messages_render_plain_when_not_tty(monkeypatch):
    buffer = StringIO()
    fake_console = Console(file=buffer, force_terminal=False, color_system=None)
    monkeypatch.setattr(messages, "console", fake_console)
    monkeypatch.setattr("geusemaker.cli.components.theme.console", fake_console)

    messages.error("plain text")

    output = buffer.getvalue()
    assert "plain text" in output
