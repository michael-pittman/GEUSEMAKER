"""Tests for InteractivePrompts helpers."""

from __future__ import annotations

from geusemaker.cli.components.dialogs import Dialogs, scripted_inputs
from geusemaker.cli.interactive.prompts import InteractivePrompts


def _prompts(*inputs: str) -> InteractivePrompts:
    return InteractivePrompts(Dialogs(input_provider=scripted_inputs(list(inputs))))


def test_choose_from_list_default_is_relative_to_options() -> None:
    """default_index refers to the caller's options, not the displayed list with 'Create new'."""
    prompts = _prompts("")
    choice = prompts.choose_from_list("Pick", ["first", "second"], default_index=0)
    # Displayed index 1 == options[0]; pressing Enter must NOT select "Create new".
    assert choice == 1


def test_choose_from_list_default_create_new_is_explicit() -> None:
    prompts = _prompts("")
    choice = prompts.choose_from_list("Pick", ["first", "second"], default_create_new=True)
    assert choice == 0  # "Create new"


def test_choose_from_list_without_create_new_keeps_plain_indexing() -> None:
    prompts = _prompts("")
    choice = prompts.choose_from_list("Pick", ["first", "second"], default_index=1, allow_create_new=False)
    assert choice == 1


def test_stack_name_explains_validation_failure(capsys) -> None:  # type: ignore[no-untyped-def]
    prompts = _prompts("9bad", "good-name")
    value = prompts.stack_name()
    assert value == "good-name"
    captured = capsys.readouterr()
    assert "start with a letter" in captured.out.lower()


def test_region_other_accepts_custom_region() -> None:
    # Option 6 is "Other"; then a free-text region code is entered.
    prompts = _prompts("6", "ap-northeast-1")
    assert prompts.region() == "ap-northeast-1"


def test_region_labels_are_geographic() -> None:
    from geusemaker.cli.interactive.prompts import REGION_CHOICES

    labels = dict(REGION_CHOICES)
    assert labels["us-east-1"] == "US East (N. Virginia)"
    assert "close to US/EU users" not in " ".join(labels.values())


def test_setup_mode_defaults_to_quick() -> None:
    assert _prompts("").setup_mode() == "quick"


def test_setup_mode_can_select_advanced() -> None:
    assert _prompts("2").setup_mode() == "advanced"
