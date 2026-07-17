"""Keep every $gm-* token definition site in lockstep with ColorTheme."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytest.importorskip("textual")

from geusemaker.cli import tui as tui_pkg  # noqa: E402
from geusemaker.cli.components.theme import ColorTheme  # noqa: E402
from geusemaker.cli.tui.theme import GM_TOKENS, GM_VARIABLES_TCSS  # noqa: E402

BRUTALIST_TCSS = Path(tui_pkg.__file__).parent / "brutalist.tcss"
# Tolerant on purpose: multi-hyphen names, 3-8 digit hex, leading indentation.
TOKEN_RE = re.compile(r"^\s*\$(gm-[a-z][a-z-]*):\s*(#[0-9a-fA-F]{3,8});", re.M)
SCREEN_MODULES = ("inspect_screen", "monitor_screen", "deploy_screen", "deploy_run_screen", "logs_screen", "splash")


def test_gm_tokens_derive_from_color_theme() -> None:
    palette = ColorTheme()
    assert GM_TOKENS == {
        "gm-surface": palette.surface,
        "gm-panel": palette.panel,
        "gm-ink": palette.ink,
        "gm-muted": palette.muted,
        "gm-signal": palette.signal,
        "gm-warn": palette.warning,
        "gm-fault": palette.error,
        "gm-rule": palette.border,
    }


def test_brutalist_tcss_matches_gm_tokens() -> None:
    declared = dict(TOKEN_RE.findall(BRUTALIST_TCSS.read_text()))
    assert declared == GM_TOKENS


def test_gm_variables_tcss_declares_every_token() -> None:
    declared = dict(TOKEN_RE.findall(GM_VARIABLES_TCSS))
    assert declared == GM_TOKENS


def test_no_screen_restates_token_declarations() -> None:
    for module in SCREEN_MODULES:
        source = (Path(tui_pkg.__file__).parent / f"{module}.py").read_text()
        for name in GM_TOKENS:
            assert f"${name}:" not in source, f"{module} redeclares ${name}"


def test_no_screen_hardcodes_palette_hex_values() -> None:
    for module in (*SCREEN_MODULES, "app"):
        source = (Path(tui_pkg.__file__).parent / f"{module}.py").read_text().lower()
        for name, value in GM_TOKENS.items():
            assert value.lower() not in source, f"{module} hardcodes {name} ({value})"


def test_screens_use_shared_token_block() -> None:
    for module in (m for m in SCREEN_MODULES if m != "splash"):
        source = (Path(tui_pkg.__file__).parent / f"{module}.py").read_text()
        assert "GM_VARIABLES_TCSS" in source, f"{module} does not use the shared tokens"
