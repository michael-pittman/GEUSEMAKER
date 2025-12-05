"""CLI entry point for GeuseMaker."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version

import click

from geusemaker import __version__
from geusemaker.cli import VerbosityLevel, console, set_verbosity
from geusemaker.cli.branding import EMOJI, MAIN_BANNER
from geusemaker.cli.commands.backup import backup_group
from geusemaker.cli.commands.cleanup import cleanup
from geusemaker.cli.commands.cost import cost
from geusemaker.cli.commands.deploy import deploy
from geusemaker.cli.commands.destroy import destroy
from geusemaker.cli.commands.health import health
from geusemaker.cli.commands.info import info
from geusemaker.cli.commands.init import init
from geusemaker.cli.commands.inspect import inspect
from geusemaker.cli.commands.list import list_deployments
from geusemaker.cli.commands.logs import logs
from geusemaker.cli.commands.monitor import monitor_group
from geusemaker.cli.commands.report import report
from geusemaker.cli.commands.restore import restore
from geusemaker.cli.commands.rollback import rollback
from geusemaker.cli.commands.status import status
from geusemaker.cli.commands.update import update
from geusemaker.cli.commands.validate import validate


def _resolve_version() -> str:
    """Return installed package version or fallback to source version."""
    try:
        return pkg_version("geusemaker")
    except PackageNotFoundError:
        return __version__


@click.group(invoke_without_command=True)
@click.version_option(version=_resolve_version(), prog_name="geusemaker")
@click.option("--silent", is_flag=True, default=False, help="Suppress non-error output.")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Show verbose/debug output.")
@click.pass_context
def cli(ctx: click.Context, silent: bool, verbose: bool) -> None:
    """GeuseMaker CLI - deploy AI infrastructure to AWS."""
    if silent and verbose:
        raise click.UsageError("Cannot combine --silent and --verbose.", ctx=ctx)

    if silent:
        set_verbosity(VerbosityLevel.SILENT)
    elif verbose:
        set_verbosity(VerbosityLevel.VERBOSE)
    else:
        set_verbosity(VerbosityLevel.NORMAL)

    ctx.obj = {"verbosity": console, "silent": silent, "verbose": verbose}

    if ctx.invoked_subcommand is None and not silent:
        console.print(f"[bold cyan]{MAIN_BANNER}[/bold cyan]", verbosity="info")
        console.print(
            f"{EMOJI['spark']} Welcome to GeuseMaker! Run `geusemaker --help` to see available commands.",
            verbosity="info",
        )


cli.add_command(deploy)
cli.add_command(destroy)
cli.add_command(update)
cli.add_command(cleanup)
cli.add_command(status)
cli.add_command(logs)
cli.add_command(cost)
cli.add_command(rollback)
cli.add_command(validate)
cli.add_command(report)
cli.add_command(health)
cli.add_command(monitor_group)
cli.add_command(list_deployments)
cli.add_command(inspect)
cli.add_command(backup_group)
cli.add_command(restore)
cli.add_command(info)
cli.add_command(init)


__all__ = ["cli"]
