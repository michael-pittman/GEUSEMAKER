"""Update command."""

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
from geusemaker.infra.state import StateManager
from geusemaker.models.update import UpdateRequest
from geusemaker.services.update import UpdateOrchestrator


def _parse_images(images: tuple[str, ...]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for image in images:
        if "=" not in image:
            raise ValueError("Images must be provided as name=repository:tag")
        name, ref = image.split("=", 1)
        if not name or not ref:
            raise ValueError("Images must include a name and reference (name=repo:tag).")
        parsed[name] = ref
    return parsed


@click.command("update")
@click.argument("stack_name")
@click.option("--instance-type", help="New EC2 instance type to apply.")
@click.option(
    "--image",
    "images",
    multiple=True,
    help="Container image override (name=repository:tag). Can be set multiple times.",
)
@click.option("--force", is_flag=True, help="Apply without confirmation.")
@click.option(
    "--state-dir",
    type=click.Path(file_okay=False, dir_okay=True, resolve_path=True),
    help="Optional state directory (default ~/.geusemaker).",
)
@output_option()
def update(
    stack_name: str,
    instance_type: str | None,
    images: tuple[str, ...],
    force: bool,
    state_dir: str | None,
    output: str,
) -> None:
    """Update a running deployment (instance type or container images)."""
    output_format = OutputFormat(output.lower())
    manager = StateManager(base_path=Path(state_dir) if state_dir else None)
    state = asyncio.run(manager.load_deployment(stack_name))
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

    try:
        image_overrides = _parse_images(images)
    except ValueError as exc:  # noqa: BLE001
        if output_format == OutputFormat.TEXT:
            console.print(f"{EMOJI['error']} {exc}", verbosity="error")
        else:
            emit_result(
                build_response(status="error", message=str(exc), error_code="invalid_images"),
                output_format,
            )
        raise SystemExit(1)

    request = UpdateRequest(
        deployment_name=stack_name,
        instance_type=instance_type,
        container_images=image_overrides or None,
        force=force,
    )

    if not force:
        change_lines = []
        if instance_type:
            change_lines.append(f"- Instance type: {state.config.instance_type} -> {instance_type}")
        if image_overrides:
            change_lines.append("- Container images: " + ", ".join(f"{k}={v}" for k, v in image_overrides.items()))
        console.print(f"{EMOJI['info']} Requested changes for [bold]{stack_name}[/bold]:", verbosity="info")
        for line in change_lines:
            console.print(f"  {line}", verbosity="info")
        if not click.confirm("Apply these changes?"):
            console.print(f"{EMOJI['warning']} Update cancelled.", verbosity="warning")
            raise SystemExit(0)

    orchestrator = UpdateOrchestrator(state_manager=manager, region=state.config.region)
    try:
        result = orchestrator.update(request, state=state)
    except Exception as exc:  # noqa: BLE001
        payload = build_response(status="error", message=f"Update failed: {exc}", error_code="update_failed")
        if output_format == OutputFormat.TEXT:
            console.print(f"{EMOJI['error']} Update failed: {exc}", verbosity="error")
        else:
            emit_result(payload, output_format)
        raise SystemExit(1)

    payload = build_response(
        status="ok",
        message=f"Update applied to {stack_name}",
        data={"changes_applied": result.changes_applied},
    )
    if output_format == OutputFormat.TEXT:
        console.print(
            f"{EMOJI['check']} Update applied to [bold]{stack_name}[/bold]: {', '.join(result.changes_applied)}",
            verbosity="result",
        )
    else:
        emit_result(payload, output_format)


import asyncio  # noqa: E402

__all__ = ["update"]
