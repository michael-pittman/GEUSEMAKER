"""Validate command for pre-deployment checks."""

import click

from geusemaker.cli import console
from geusemaker.cli.branding import EMOJI
from geusemaker.cli.display.validation import render_validation_report
from geusemaker.cli.output import (
    OutputFormat,
    build_response,
    emit_result,
    output_option,
)
from geusemaker.infra import AWSClientFactory
from geusemaker.models import DeploymentConfig
from geusemaker.services.validation import PreDeploymentValidator


@click.command("validate")
@click.option("--stack-name", "-s", required=True, help="Stack/deployment name.")
@click.option(
    "--tier",
    type=click.Choice(["dev", "automation", "gpu"], case_sensitive=False),
    default="dev",
    show_default=True,
    help="Deployment tier.",
)
@click.option(
    "--region",
    default="us-east-1",
    show_default=True,
    help="AWS region for deployment.",
)
@click.option(
    "--instance-type",
    default="t3.medium",
    show_default=True,
    help="Instance type to validate.",
)
@click.option(
    "--use-spot/--no-spot",
    default=True,
    show_default=True,
    help="Validate spot configuration preference.",
)
@output_option()
def validate(
    stack_name: str,
    tier: str,
    region: str,
    instance_type: str,
    use_spot: bool,
    output: str,
) -> None:
    """Run pre-deployment validation without creating resources."""
    output_format = OutputFormat(output.lower())
    config = DeploymentConfig(
        stack_name=stack_name,
        tier=tier.lower(),  # type: ignore[arg-type]
        region=region,
        instance_type=instance_type,
        use_spot=use_spot,
    )
    validator = PreDeploymentValidator(AWSClientFactory(), region=config.region)
    report = validator.validate(config)

    if output_format == OutputFormat.TEXT:
        console.print(render_validation_report(report), verbosity="result")
    else:
        payload = build_response(
            status="ok" if report.passed else "error",
            message="Validation report",
            data=report,
            error_code=None if report.passed else "validation_failed",
        )
        emit_result(payload, output_format)

    if report.passed:
        console.print(
            f"{EMOJI['spark']} Validation passed with {report.warnings} warning(s).",
            verbosity="result",
        )
        raise SystemExit(0)

    console.print(
        f"{EMOJI['warning']} Validation failed with {report.errors} error(s). "
        "Resolve the failures above before deploying.",
        verbosity="error",
    )
    raise SystemExit(1)


__all__ = ["validate"]
