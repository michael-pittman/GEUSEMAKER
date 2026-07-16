"""Optional Textual shell; imported only after dependency checks."""


def run_tui(*, initial_screen: str = "hub", stack_name: str | None = None) -> None:
    from geusemaker.cli.tui.app import GeuseMakerApp

    GeuseMakerApp(initial_screen=initial_screen, stack_name=stack_name).run()


__all__ = ["run_tui"]
