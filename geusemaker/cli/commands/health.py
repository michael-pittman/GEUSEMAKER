"""Health check command."""

from __future__ import annotations

import asyncio
from pathlib import Path

import click

from geusemaker.cli import console
from geusemaker.cli.branding import EMOJI
from geusemaker.cli.display.health import render_health_results
from geusemaker.cli.output import (
    OutputFormat,
    build_response,
    emit_result,
    render_output,
)
from geusemaker.models.health import HealthCheckResult
from geusemaker.services.health import (
    HealthCheckClient,
    check_all_services,
    check_postgres,
)


@click.command("health")
@click.option("--host", required=True, help="Host/IP of the deployment instance or ALB.")
@click.option("--include-postgres/--skip-postgres", default=True, show_default=True)
@click.option(
    "--output",
    "--format",
    "output_format",
    type=click.Choice(["text", "json", "yaml", "rich"], case_sensitive=False),
    default="text",
    show_default=True,
)
@click.option(
    "--output-file",
    type=click.Path(dir_okay=False, writable=True, resolve_path=True),
    help="Optional file path to write JSON/YAML results.",
)
@click.option("--timeout", default=10.0, show_default=True, help="HTTP timeout seconds.")
def health(
    host: str,
    include_postgres: bool,
    output_format: str,
    output_file: str | None,
    timeout: float,
) -> None:
    """Run health checks against a deployment host."""
    results = asyncio.run(_run_checks(host, include_postgres, timeout))
    fmt = OutputFormat.TEXT if output_format.lower() in {"text", "rich"} else OutputFormat(output_format.lower())
    payload = [r.model_dump() for r in results]

    if fmt == OutputFormat.TEXT:
        content = render_health_results(results)
        if output_file:
            Path(output_file).write_text(str(content))
            console.print(f"{EMOJI['check']} Health results written to {output_file}", verbosity="result")
        else:
            console.print(content, verbosity="result")
    else:
        response = build_response(
            status="ok",
            message="Health check completed.",
            data=payload,
        )
        serialized = render_output(response, fmt)
        if output_file:
            Path(output_file).write_text(serialized)
            console.print(f"{EMOJI['check']} Health results written to {output_file}", verbosity="result")
        else:
            emit_result(response, fmt)

    unhealthy = [r for r in results if not r.healthy]
    raise SystemExit(0 if not unhealthy else 1)


async def _run_checks(host: str, include_postgres: bool, timeout: float) -> list[HealthCheckResult]:
    client = HealthCheckClient()
    results = await check_all_services(client, host=host)
    if include_postgres:
        results.append(await check_postgres(client, host=host, port=5432))
    return results


__all__ = ["health"]
