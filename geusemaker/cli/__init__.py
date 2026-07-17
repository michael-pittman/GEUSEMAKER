from rich.theme import Theme

from geusemaker.cli.output.verbosity import (
    VerbosityConsole,
    VerbosityLevel,
    get_verbosity,
    is_silent,
    set_verbosity,
)

console = VerbosityConsole(
    theme=Theme(
        {
            "gm.ink": "#e8ecef",
            "gm.muted": "#6b7280",
            "gm.signal": "bold #c8f542",
            "gm.warning": "#f5a524",
            "gm.error": "bold #ff4d4d",
            "gm.rule": "#2a3038",
            "gm.step": "bold #e8ecef on #12151a",
        }
    )
)

__all__ = ["console", "set_verbosity", "get_verbosity", "VerbosityLevel", "is_silent"]
