"""Generate validation reports."""

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
    render_output,
)
from geusemaker.infra import AWSClientFactory
from geusemaker.infra.state import StateManager
from geusemaker.models import DeploymentConfig
from geusemaker.models.validation import ValidationCheck, ValidationReport
from geusemaker.services.validation import (
    PostDeploymentValidator,
    PreDeploymentValidator,
)
from geusemaker.services.validation.remediation import remediation_for
from geusemaker.services.validation.reporting import (
    render_report,
)


@click.command("report")
@click.option("--stack-name", "-s", required=True, help="Deployment stack name.")
@click.option(
    "--tier",
    type=click.Choice(["dev", "automation", "gpu"], case_sensitive=False),
    default="dev",
    show_default=True,
    help="Deployment tier for context.",
)
@click.option(
    "--region",
    default="us-east-1",
    show_default=True,
    help="AWS region for context/refresh.",
)
@click.option(
    "--output-file",
    type=click.Path(dir_okay=False, writable=True, resolve_path=True),
    help="Optional file path to write the report to.",
)
@output_option()
@click.option(
    "--refresh",
    is_flag=True,
    default=False,
    help="Re-run pre-deployment validation to refresh report.",
)
@click.option(
    "--vpc-id",
    default=None,
    help="Optional existing VPC id to validate.",
)
@click.option(
    "--post",
    "post_validation",
    is_flag=True,
    default=False,
    help="Run post-deployment validation using stored state (hosted services).",
)
@click.option(
    "--state-dir",
    type=click.Path(file_okay=False, dir_okay=True, writable=True, resolve_path=True),
    help="Optional state directory (default ~/.geusemaker).",
)
def report(
    stack_name: str,
    tier: str,
    region: str,
    output: str,
    output_file: str | None,
    refresh: bool,
    vpc_id: str | None,
    post_validation: bool,
    state_dir: str | None,
) -> None:
    """Generate a validation report for a deployment."""
    output_format = OutputFormat(output.lower())
    report_obj = _generate_report(stack_name, tier, region, refresh, vpc_id, post_validation, state_dir)

    if output_format == OutputFormat.TEXT:
        content = render_report(report_obj) if output_file is None else render_report(report_obj)
        if output_file:
            Path(output_file).write_text(str(content))
            console.print(f"{EMOJI['check']} Report written to {output_file}", verbosity="result")
        else:
            console.print(content, verbosity="result")
    else:
        payload = build_response(status="ok", data=report_obj, message="Validation report")
        serialized = render_output(payload, output_format)
        if output_file:
            Path(output_file).write_text(serialized)
            console.print(f"{EMOJI['check']} Report written to {output_file}", verbosity="result")
        else:
            emit_result(payload, output_format)

    raise SystemExit(0 if report_obj.passed else 1)


def _generate_report(
    stack_name: str,
    tier: str,
    region: str,
    refresh: bool,
    vpc_id: str | None,
    post_validation: bool,
    state_dir: str | None,
):
    """Generate or refresh a report; fallback to a stub on failure."""
    if refresh:
        if post_validation:
            state_manager = StateManager(base_path=Path(state_dir) if state_dir else None)
            state = state_manager._read_state(state_manager.deployments_path / f"{stack_name}.json")
            if state is None:
                return ValidationReport(
                    checks=[
                        ValidationCheck(
                            check_name="post_validation",
                            passed=False,
                            message="No stored deployment state found; deploy first or supply --state-dir.",
                            severity="warning",
                        ),
                    ],
                    deployment_name=stack_name,
                    deployment_tier=tier,
                )

            validator = PostDeploymentValidator(
                client_factory=AWSClientFactory(),
                region=region,
            )
            report = asyncio.run(validator.validate(state))
            report.deployment_name = stack_name
            report.deployment_tier = tier
            return report
        config = DeploymentConfig(
            stack_name=stack_name,
            tier=tier.lower(),  # type: ignore[arg-type]
            region=region,
            vpc_id=vpc_id,
        )
        report = PreDeploymentValidator(
            client_factory=AWSClientFactory(),
            region=region,
        ).validate(
            config,
        )
        report.deployment_name = stack_name
        report.deployment_tier = tier
        return report

    # Fallback: basic report stating no stored validation
    check = ValidationCheck(
        check_name="report",
        passed=False,
        message="No stored validation found; run with --refresh to validate now.",
        remediation=remediation_for("ec2_status"),
        severity="warning",
    )
    return ValidationReport(
        checks=[check],
        deployment_name=stack_name,
        deployment_tier=tier,
    )


__all__ = ["report"]
