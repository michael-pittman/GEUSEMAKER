"""Logs command implementation."""

from __future__ import annotations

import asyncio
from pathlib import Path

import click

from geusemaker.cli import console
from geusemaker.cli.branding import EMOJI
from geusemaker.cli.output import (
    OutputFormat,
    build_response,
    emit_result,
    output_option,
)
from geusemaker.infra import AWSClientFactory, StateManager
from geusemaker.services.ssm import SSMService


@click.command("logs")
@click.argument("stack_name")
@click.option(
    "--service",
    type=click.Choice(["userdata", "n8n", "ollama", "qdrant", "crawl4ai", "postgres"], case_sensitive=False),
    default="userdata",
    show_default=True,
    help="Service to fetch logs from.",
)
@click.option(
    "--tail",
    default=100,
    show_default=True,
    help="Number of lines to show (ignored for --follow).",
)
@click.option(
    "--follow",
    "-f",
    is_flag=True,
    default=False,
    help="Stream logs in real-time (userdata only).",
)
@click.option(
    "--state-dir",
    type=click.Path(file_okay=False, dir_okay=True, resolve_path=True),
    help="Optional state directory (default ~/.geusemaker).",
)
@output_option()
def logs(
    stack_name: str,
    service: str,
    tail: int,
    follow: bool,
    state_dir: str | None,
    output: str,
) -> None:
    """
    Fetch deployment logs via AWS Systems Manager.

    Supports:
    - UserData initialization logs
    - Docker container logs (n8n, Ollama, Qdrant, Crawl4AI, PostgreSQL)
    - Real-time log streaming with --follow
    """
    output_format = OutputFormat(output.lower())
    state_manager = StateManager(base_path=Path(state_dir) if state_dir else None)

    # Load deployment state
    state = asyncio.run(state_manager.load_deployment(stack_name))
    if state is None:
        payload = build_response(
            status="error",
            message=f"Deployment '{stack_name}' not found.",
            error_code="not_found",
        )
        if output_format == OutputFormat.TEXT:
            console.print(f"{EMOJI['error']} Deployment '{stack_name}' not found.", verbosity="error")
        else:
            emit_result(payload, output_format)
        raise SystemExit(1)

    # Validate --follow only works with userdata
    if follow and service != "userdata":
        payload = build_response(
            status="error",
            message="--follow flag only supported for userdata logs",
            error_code="invalid_option",
        )
        if output_format == OutputFormat.TEXT:
            console.print(
                f"{EMOJI['error']} --follow flag only supported for userdata logs.",
                verbosity="error",
            )
        else:
            emit_result(payload, output_format)
        raise SystemExit(1)

    # Initialize SSM service
    client_factory = AWSClientFactory()
    ssm_service = SSMService(client_factory, region=state.config.region)

    # Fetch logs based on service type
    try:
        if follow:
            _stream_userdata_logs(ssm_service, state.instance_id)
        elif service == "userdata":
            _fetch_userdata_logs(ssm_service, state.instance_id, stack_name, output_format)
        else:
            _fetch_container_logs(ssm_service, state.instance_id, service, tail, stack_name, output_format)
    except RuntimeError as exc:
        payload = build_response(
            status="error",
            message=f"Failed to fetch logs: {exc}",
            error_code="fetch_failed",
        )
        if output_format == OutputFormat.TEXT:
            console.print(f"{EMOJI['error']} Failed to fetch logs: {exc}", verbosity="error")
        else:
            emit_result(payload, output_format)
        raise SystemExit(1)


def _stream_userdata_logs(ssm_service: SSMService, instance_id: str) -> None:
    """Stream UserData logs in real-time."""
    console.print(
        f"{EMOJI['info']} Streaming UserData logs (Ctrl+C to stop)...",
        verbosity="info",
    )
    try:
        for line in ssm_service.stream_userdata_logs(instance_id):
            console.print(line, verbosity="info")
        console.print(f"{EMOJI['check']} UserData initialization complete.", verbosity="info")
    except KeyboardInterrupt:
        console.print(f"{EMOJI['warning']} Log streaming interrupted.", verbosity="warning")


def _fetch_userdata_logs(
    ssm_service: SSMService,
    instance_id: str,
    stack_name: str,
    output_format: OutputFormat,
) -> None:
    """Fetch UserData initialization logs."""
    log_content = ssm_service.fetch_userdata_logs(instance_id, wait_for_completion=False)

    if output_format == OutputFormat.TEXT:
        console.print(
            f"{EMOJI['info']} UserData logs for [bold]{stack_name}[/bold]:",
            verbosity="info",
        )
        console.print(log_content, verbosity="info")
    else:
        payload = build_response(
            status="ok",
            message="UserData logs retrieved successfully",
            data={
                "stack_name": stack_name,
                "service": "userdata",
                "logs": log_content,
            },
        )
        emit_result(payload, output_format)


def _fetch_container_logs(
    ssm_service: SSMService,
    instance_id: str,
    service: str,
    tail: int,
    stack_name: str,
    output_format: OutputFormat,
) -> None:
    """Fetch Docker container logs for a specific service."""
    # Map service names to container names
    container_map = {
        "n8n": "n8n",
        "ollama": "ollama",
        "qdrant": "qdrant",
        "crawl4ai": "crawl4ai",
        "postgres": "postgres",
    }

    container_name = container_map.get(service)
    if not container_name:
        raise RuntimeError(f"Unknown service: {service}")

    # Run docker logs command via SSM
    result = ssm_service.run_shell_script(
        instance_id,
        commands=[f"docker logs --tail {tail} {container_name} 2>&1"],
        comment=f"Fetch {service} container logs",
        timeout_seconds=60,
    )

    invocation_status = result.get("Status")
    if invocation_status != "Success":
        stderr = result.get("StandardErrorContent", "")
        raise RuntimeError(f"Failed to fetch {service} logs: {stderr}")

    log_content = result.get("StandardOutputContent", "")

    if output_format == OutputFormat.TEXT:
        console.print(
            f"{EMOJI['info']} Logs for [bold]{service}[/bold] container (last {tail} lines):",
            verbosity="info",
        )
        console.print(log_content, verbosity="info")
    else:
        payload = build_response(
            status="ok",
            message=f"{service} logs retrieved successfully",
            data={
                "stack_name": stack_name,
                "service": service,
                "tail": tail,
                "logs": log_content,
            },
        )
        emit_result(payload, output_format)


__all__ = ["logs"]
