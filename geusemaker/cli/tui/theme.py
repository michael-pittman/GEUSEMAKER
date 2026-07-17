"""Brutalist $gm-* design tokens for Textual screens, derived from ColorTheme.

`geusemaker/cli/components/theme.py` (ColorTheme) is the palette's single
Python source; this module maps it onto the TUI's `$gm-*` TCSS variable names.
Textual 8.2.8 scopes stylesheet variables per source, so app-level variables in
brutalist.tcss are not visible inside a widget's DEFAULT_CSS — screens prepend
GM_VARIABLES_TCSS to their DEFAULT_CSS instead of restating values, and use
GM_SIGNAL for Rich markup accents. brutalist.tcss keeps literal definitions for
the app stylesheet (test host apps load it standalone); test_theme.py asserts
it stays in sync with ColorTheme.
"""

from __future__ import annotations

from geusemaker.cli.components.theme import ColorTheme

_PALETTE = ColorTheme()

GM_TOKENS: dict[str, str] = {
    "gm-surface": _PALETTE.surface,
    "gm-panel": _PALETTE.panel,
    "gm-ink": _PALETTE.ink,
    "gm-muted": _PALETTE.muted,
    "gm-signal": _PALETTE.signal,
    "gm-warn": _PALETTE.warning,
    "gm-fault": _PALETTE.error,
    "gm-rule": _PALETTE.border,
}

GM_VARIABLES_TCSS: str = "\n".join(f"${name}: {value};" for name, value in GM_TOKENS.items()) + "\n"

GM_SIGNAL: str = GM_TOKENS["gm-signal"]
GM_WARN: str = GM_TOKENS["gm-warn"]
GM_FAULT: str = GM_TOKENS["gm-fault"]
GM_MUTED: str = GM_TOKENS["gm-muted"]
GM_INK: str = GM_TOKENS["gm-ink"]

__all__ = ["GM_FAULT", "GM_INK", "GM_MUTED", "GM_SIGNAL", "GM_TOKENS", "GM_VARIABLES_TCSS", "GM_WARN"]
