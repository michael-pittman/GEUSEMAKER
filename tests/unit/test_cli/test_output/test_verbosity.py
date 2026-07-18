from __future__ import annotations

from io import StringIO

import pytest
from rich.console import Console

from geusemaker.cli.output.verbosity import (
    VerbosityConsole,
    VerbosityLevel,
    set_machine_output,
    set_verbosity,
)


@pytest.fixture(autouse=True)
def _reset_verbosity():
    set_verbosity(VerbosityLevel.NORMAL)
    set_machine_output(False)
    yield
    set_verbosity(VerbosityLevel.NORMAL)
    set_machine_output(False)


def _console() -> tuple[VerbosityConsole, StringIO]:
    buffer = StringIO()
    return VerbosityConsole(file=buffer, force_terminal=False, color_system=None), buffer


def test_silent_shows_only_explicit_error():
    console, buffer = _console()
    set_verbosity(VerbosityLevel.SILENT)
    console.print("an error occurred", verbosity="error")
    assert "an error occurred" in buffer.getvalue()


def test_silent_suppresses_info():
    console, buffer = _console()
    set_verbosity(VerbosityLevel.SILENT)
    console.print("some info", verbosity="info")
    assert buffer.getvalue().strip() == ""


def test_silent_suppresses_warning_and_result():
    console, buffer = _console()
    set_verbosity(VerbosityLevel.SILENT)
    console.print("a warning", verbosity="warning")
    console.print("a result", verbosity="result")
    assert buffer.getvalue().strip() == ""


def test_silent_no_substring_magic():
    """A plain print whose text contains 'error' is NOT specially treated.

    The old substring sniffing is gone: without verbosity="error" this obeys the
    default (info) severity and is suppressed under --silent.
    """
    console, buffer = _console()
    set_verbosity(VerbosityLevel.SILENT)
    console.print("some text with the word error in it")
    assert buffer.getvalue().strip() == ""


def test_silent_no_substring_magic_for_red_markup():
    console, buffer = _console()
    set_verbosity(VerbosityLevel.SILENT)
    console.print("[red]looks alarming[/red]", verbosity="info")
    assert buffer.getvalue().strip() == ""


def test_normal_shows_info_and_result():
    console, buffer = _console()
    set_verbosity(VerbosityLevel.NORMAL)
    console.print("hello", verbosity="info")
    console.print("payload", verbosity="result")
    output = buffer.getvalue()
    assert "hello" in output
    assert "payload" in output


def test_normal_suppresses_debug():
    console, buffer = _console()
    set_verbosity(VerbosityLevel.NORMAL)
    console.print("noisy", verbosity="debug")
    assert buffer.getvalue().strip() == ""


def test_verbose_shows_debug():
    console, buffer = _console()
    set_verbosity(VerbosityLevel.VERBOSE)
    console.print("noisy", verbosity="debug")
    assert "noisy" in buffer.getvalue()


def test_machine_output_diverts_to_stderr(monkeypatch):
    stderr_buffer = StringIO()
    stderr_console = Console(file=stderr_buffer, force_terminal=False, color_system=None)
    monkeypatch.setattr(
        "geusemaker.cli.output.verbosity._get_stderr_console",
        lambda: stderr_console,
    )
    console, stdout_buffer = _console()
    set_verbosity(VerbosityLevel.NORMAL)
    set_machine_output(True)
    console.print("diagnostic", verbosity="info")
    assert stdout_buffer.getvalue().strip() == ""
    assert "diagnostic" in stderr_buffer.getvalue()
