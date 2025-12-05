"""Cleanup orphaned resources."""

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
from geusemaker.services.cleanup import OrphanDetector


@click.command("cleanup")
@click.option("--dry-run", is_flag=True, help="Preview cleanup without deleting resources.")
@click.option("--all", "delete_all", is_flag=True, help="Delete all detected orphans without prompting.")
@click.option(
    "--region",
    default="us-east-1",
    show_default=True,
    help="Region to scan, or 'all' for a basic multi-region scan.",
)
@click.option(
    "--state-dir",
    type=click.Path(file_okay=False, dir_okay=True, resolve_path=True),
    help="Optional state directory (default ~/.geusemaker).",
)
@output_option()
def cleanup(dry_run: bool, delete_all: bool, region: str, state_dir: str | None, output: str) -> None:
    """Detect and optionally delete orphaned GeuseMaker resources."""
    output_format = OutputFormat(output.lower())
    manager = StateManager(base_path=Path(state_dir) if state_dir else None)
    detector = OrphanDetector(state_manager=manager, region=region)

    regions = [region]
    if region.lower() == "all":
        regions = ["us-east-1", "us-west-2"]

    orphans: list = []
    for reg in regions:
        orphans.extend(detector.detect_orphans(region=reg))

    if not orphans:
        payload = build_response(status="ok", message="No orphaned resources found.", data=[])
        if output_format == OutputFormat.TEXT:
            console.print(f"{EMOJI['check']} No orphaned resources found.", verbosity="result")
        else:
            emit_result(payload, output_format)
        raise SystemExit(0)

    if output_format == OutputFormat.TEXT:
        console.print(f"{EMOJI['info']} Found {len(orphans)} orphaned resources.", verbosity="info")
        for orphan in orphans:
            console.print(
                f"- {orphan.resource_type} {orphan.resource_id} "
                f"(deployment tag: {orphan.deployment_tag}, region: {orphan.region})",
                verbosity="info",
            )

    targets = list(orphans) if delete_all else []
    if not delete_all and not dry_run:
        for orphan in orphans:
            if click.confirm(f"Delete {orphan.resource_type} {orphan.resource_id} in {orphan.region}?"):
                targets.append(orphan)

    deleted, errors = detector.delete_orphans(targets, dry_run=dry_run)
    report = detector.build_report(orphans, deleted, regions, errors, dry_run)

    if output_format == OutputFormat.TEXT:
        console.print(
            f"{EMOJI['check']} Cleanup complete. "
            f"Deleted: {report.orphans_deleted}, Preserved: {report.orphans_preserved}, "
            f"Estimated savings: ${report.estimated_monthly_savings}",
            verbosity="result",
        )
        if report.errors:
            for err in report.errors:
                console.print(f"{EMOJI['error']} {err}", verbosity="error")
            raise SystemExit(1)
        raise SystemExit(0)

    payload = build_response(
        status="ok" if not report.errors else "error",
        message="Cleanup complete",
        data=report.model_dump(mode="json"),
        error_code="cleanup_failed" if report.errors else None,
        errors=report.errors or None,
    )
    emit_result(payload, output_format)
    raise SystemExit(0 if not report.errors else 1)


__all__ = ["cleanup"]
