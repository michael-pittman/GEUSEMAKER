"""Status command stub."""

import click

from geusemaker.cli import console
from geusemaker.cli.branding import EMOJI
from geusemaker.cli.output import (
    OutputFormat,
    build_response,
    emit_result,
    output_option,
)


@click.command("status")
@click.option("--stack-name", "-s", required=True, help="Stack/deployment name.")
@output_option()
def status(stack_name: str, output: str) -> None:
    """Show deployment status (stub)."""
    output_format = OutputFormat(output.lower())
    message = f"{EMOJI['info']} Status requested for stack [bold]{stack_name}[/bold]. Implementation pending."
    if output_format == OutputFormat.TEXT:
        console.print(message, verbosity="info")
    else:
        emit_result(
            build_response(status="ok", message="Status not yet implemented", data={"stack_name": stack_name}),
            output_format,
        )


__all__ = ["status"]
