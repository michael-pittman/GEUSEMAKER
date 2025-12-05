"""Logs command stub."""

import click

from geusemaker.cli import console
from geusemaker.cli.branding import EMOJI
from geusemaker.cli.output import (
    OutputFormat,
    build_response,
    emit_result,
    output_option,
)


@click.command("logs")
@click.option("--stack-name", "-s", required=True, help="Stack/deployment name.")
@click.option("--tail", default=100, show_default=True, help="Number of lines to show.")
@output_option()
def logs(stack_name: str, tail: int, output: str) -> None:
    """Show deployment logs (stub)."""
    output_format = OutputFormat(output.lower())
    msg = f"{EMOJI['info']} Logs requested for stack [bold]{stack_name}[/bold] (tail {tail}). Implementation pending."
    if output_format == OutputFormat.TEXT:
        console.print(msg, verbosity="info")
    else:
        emit_result(
            build_response(
                status="ok",
                message="Logs retrieval not yet implemented",
                data={"stack_name": stack_name, "tail": tail},
            ),
            output_format,
        )


__all__ = ["logs"]
