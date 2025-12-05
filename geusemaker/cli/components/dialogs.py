"""Input/confirmation helpers with optional back/quit handling."""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterable, Sequence

import questionary

from geusemaker.cli import console
from geusemaker.cli.branding import EMOJI
from geusemaker.cli.components.theme import THEME, is_tty


class DialogAbort(RuntimeError):
    """Raised when the user chooses to quit the interactive flow."""


class DialogBack(RuntimeError):
    """Raised when the user wants to return to the previous step."""


InputProvider = Callable[[str], str]


class Dialogs:
    """Collection of interactive prompts with sensible defaults."""

    def __init__(self, input_provider: InputProvider | None = None):
        self._input_provider = input_provider

    def prompt_text(
        self,
        prompt: str,
        default: str | None = None,
        allow_back: bool = True,
        allow_quit: bool = True,
        validator: Callable[[str], bool] | None = None,
        help_text: str | None = None,
    ) -> str:
        """Prompt for free-form text with validation."""
        while True:
            self._print_help(help_text)
            raw = self._read(f"{prompt} " + (f"[{default}] " if default else ""))
            value = raw.strip()
            if not value and default is not None:
                value = default
            self._handle_navigation(value, allow_back, allow_quit)
            if validator and value and not validator(value):
                console.print(f"{EMOJI['warn']} Please enter a valid value.")
                continue
            if value:
                return value
            console.print(f"{EMOJI['warn']} Value cannot be empty.")

    def confirm(
        self,
        prompt: str,
        default: bool = True,
        allow_back: bool = True,
        allow_quit: bool = True,
        help_text: str | None = None,
    ) -> bool:
        """Yes/No prompt that understands 'back'/'quit' navigation."""
        suffix = "[Y/n]" if default else "[y/N]"
        while True:
            self._print_help(help_text)
            raw = self._read(f"{prompt} {suffix} ")
            value = raw.strip().lower()
            if not value:
                return default
            if value in ("y", "yes"):
                return True
            if value in ("n", "no"):
                return False
            self._handle_navigation(value, allow_back, allow_quit)
            console.print(f"{EMOJI['warn']} Please respond with 'y' or 'n'.")

    def select(
        self,
        prompt: str,
        options: Sequence[str],
        default_index: int = 0,
        allow_back: bool = True,
        allow_quit: bool = True,
        help_text: str | None = None,
    ) -> int:
        """Prompt for an option index from a list with arrow key navigation."""
        if not options:
            raise ValueError("options cannot be empty")

        # Use scripted input provider for testing (non-interactive)
        if self._input_provider:
            return self._select_fallback(prompt, options, default_index, allow_back, allow_quit, help_text)

        # Use questionary for interactive terminal with arrow key support
        if not is_tty() or not sys.stdin.isatty():
            return self._select_fallback(prompt, options, default_index, allow_back, allow_quit, help_text)

        # Print help text if provided
        if help_text:
            console.print(f"[{THEME.muted}]{help_text}[/{THEME.muted}]")

        # Create custom style that matches our theme
        # prompt_toolkit needs hex colors, not Rich color names like 'grey70'
        custom_style = {
            "qmark": "cyan bold",
            "question": "cyan bold",
            "answer": "cyan",
            "pointer": "magenta bold",
            "highlighted": "magenta bold",
            "selected": "cyan",
            "separator": "#888888",
            "instruction": "#888888",
            "text": "",
            "disabled": "#888888",
        }

        # Build choices list - add navigation options if enabled
        choices = list(options)
        navigation_choices = []
        if allow_back:
            navigation_choices.append("← Back")
        if allow_quit:
            navigation_choices.append("✗ Quit")

        # Combine regular choices with navigation choices
        all_choices = choices + navigation_choices

        # Adjust default index if navigation options were added
        actual_default = default_index if 0 <= default_index < len(choices) else 0
        default_choice = choices[actual_default] if choices else None

        instruction = "Use ↑↓ arrow keys to navigate, Enter to select, Ctrl+C to cancel"

        try:
            # Use questionary.select for interactive arrow key navigation
            # Convert dict to proper Style object
            style = questionary.Style.from_dict(custom_style)
            result = questionary.select(
                prompt,
                choices=all_choices,
                default=default_choice,
                style=style,
                instruction=instruction,
            ).ask()

            if result is None:
                # User cancelled (Ctrl+C)
                raise DialogAbort("User aborted interactive flow.")

            # Check if result is a navigation command
            if result == "← Back":
                raise DialogBack()
            if result == "✗ Quit":
                raise DialogAbort("User aborted interactive flow.")

            # Find the index of the selected option in the original options list
            try:
                return choices.index(result)
            except ValueError:
                # Fallback to default if something went wrong
                return default_index

        except KeyboardInterrupt as exc:  # noqa: B904
            raise DialogAbort("User interrupted interactive flow.") from exc

    def _select_fallback(
        self,
        prompt: str,
        options: Sequence[str],
        default_index: int,
        allow_back: bool,
        allow_quit: bool,
        help_text: str | None,
    ) -> int:
        """Fallback text-based selection for non-interactive or testing scenarios."""
        if not options:
            raise ValueError("options cannot be empty")
        self._print_help(help_text)
        for idx, option in enumerate(options):
            marker = "•" if idx != default_index else "➤"
            style = THEME.primary if idx == default_index else THEME.muted
            if is_tty():
                console.print(f"[{style}]{marker} {idx + 1}. {option}[/{style}]")
            else:
                console.print(f"{marker} {idx + 1}. {option}")
        while True:
            raw = self._read(f"{prompt} [{default_index + 1}] ")
            value = raw.strip()
            if not value:
                return default_index
            self._handle_navigation(value, allow_back, allow_quit)
            try:
                choice = int(value)
            except ValueError:
                console.print(f"{EMOJI['warn']} Enter a number between 1 and {len(options)}.")
                continue
            if 1 <= choice <= len(options):
                return choice - 1
            console.print(f"{EMOJI['warn']} Enter a number between 1 and {len(options)}.")

    def _handle_navigation(self, value: str, allow_back: bool, allow_quit: bool) -> None:
        if allow_back and value.lower() == "back":
            raise DialogBack()
        if allow_quit and value.lower() in {"quit", "q", "exit"}:
            raise DialogAbort("User aborted interactive flow.")

    def _read(self, prompt: str) -> str:
        if self._input_provider:
            return self._input_provider(prompt)
        try:
            return console.input(prompt)
        except KeyboardInterrupt as exc:  # noqa: B904
            raise DialogAbort("User interrupted interactive flow.") from exc

    def _print_help(self, help_text: str | None) -> None:
        if help_text:
            console.print(f"[{THEME.muted}]{help_text}[/{THEME.muted}]")


def scripted_inputs(values: Iterable[str]) -> InputProvider:
    """Return an input provider that yields predefined responses (for tests)."""
    iterator = iter(values)

    def _provider(prompt: str) -> str:  # noqa: D401
        try:
            return next(iterator)
        except StopIteration as exc:  # noqa: B904
            raise DialogAbort("No more scripted inputs.") from exc

    return _provider


__all__ = ["DialogAbort", "DialogBack", "Dialogs", "scripted_inputs"]
