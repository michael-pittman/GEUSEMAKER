from geusemaker.cli.output.verbosity import (
    VerbosityConsole,
    VerbosityLevel,
    get_verbosity,
    is_silent,
    set_verbosity,
)

console = VerbosityConsole()

__all__ = ["console", "set_verbosity", "get_verbosity", "VerbosityLevel", "is_silent"]
