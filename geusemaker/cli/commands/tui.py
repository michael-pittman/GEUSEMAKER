"""Opt-in full-screen terminal shell."""

import click

INSTALL_HINT = "Full-screen UI requires the optional extra: pip install 'geusemaker[tui]'"


def launch_tui(*, initial_screen: str = "hub", stack_name: str | None = None) -> None:
    try:
        import textual  # noqa: F401
    except ImportError as exc:
        raise click.ClickException(INSTALL_HINT) from exc
    from geusemaker.cli.tui import run_tui

    run_tui(initial_screen=initial_screen, stack_name=stack_name)


@click.command("tui")
@click.option("--screen", type=click.Choice(["hub", "deploy", "monitor", "inspect"]), default="hub")
@click.option("--stack-name", help="Open a stack in monitor or inspect mode.")
def tui_command(screen: str, stack_name: str | None) -> None:
    """Open the optional full-screen operations hub."""
    launch_tui(initial_screen=screen, stack_name=stack_name)


__all__ = ["INSTALL_HINT", "launch_tui", "tui_command"]
