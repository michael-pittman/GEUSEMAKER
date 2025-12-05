from __future__ import annotations

import pytest

from geusemaker.cli.components.dialogs import (
    DialogAbort,
    DialogBack,
    Dialogs,
    scripted_inputs,
)


def test_prompt_text_accepts_default_and_back() -> None:
    dialogs = Dialogs(input_provider=scripted_inputs(["", "back"]))
    assert dialogs.prompt_text("Name:", default="demo") == "demo"
    with pytest.raises(DialogBack):
        dialogs.prompt_text("Name:", default="demo")


def test_confirm_handles_quit() -> None:
    dialogs = Dialogs(input_provider=scripted_inputs(["quit"]))
    with pytest.raises(DialogAbort):
        dialogs.confirm("Continue?")


def test_select_returns_index() -> None:
    dialogs = Dialogs(input_provider=scripted_inputs(["2"]))
    choice = dialogs.select("Pick", options=["a", "b"], allow_back=False, allow_quit=False)
    assert choice == 1
