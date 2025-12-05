"""Deploy command bootstrap."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import click

from geusemaker.cli import console
from geusemaker.cli.branding import DEPLOY_BANNER, EMOJI
from geusemaker.cli.interactive import (
    DeploymentRunner,
    DeploymentValidationFailed,
    InteractiveDeployer,
)
from geusemaker.cli.output import (
    OutputFormat,
    build_response,
    emit_result,
    output_option,
)
from geusemaker.config import ConfigLoader, ConfigurationError
from geusemaker.infra import AWSClientFactory, StateManager


def _get_source(ctx: click.Context, param_name: str) -> click.core.ParameterSource | None:
    try:
        return ctx.get_parameter_source(param_name)
    except Exception:  # noqa: BLE001
        return None


def _emit_error(payload: dict[str, Any], output_format: OutputFormat) -> None:
    if output_format == OutputFormat.TEXT:
        console.print(f"{EMOJI['error']} {payload.get('message')}", verbosity="error")
        for detail in payload.get("errors") or []:
            console.print(f" • {detail}", verbosity="error")
        return
    emit_result(payload, output_format)


def _collect_overrides(ctx: click.Context, **values: Any) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    for key, value in values.items():
        source = _get_source(ctx, key)
        if source and source.name != "DEFAULT" and value is not None:
            overrides[key] = value
    return overrides


@click.command("deploy")
@click.option(
    "--config",
    type=click.Path(exists=True, dir_okay=False, resolve_path=True),
    help="Path to YAML/JSON config.",
)
@click.option(
    "--interactive/--no-interactive",
    default=None,
    help="Force the interactive wizard (defaults to auto when no options are provided).",
)
@click.option("--stack-name", "-s", required=False, help="Stack/deployment name.")
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
    help="Instance type to launch.",
)
@click.option(
    "--os-type",
    type=click.Choice(
        ["amazon-linux-2023", "ubuntu-22.04", "ubuntu-24.04", "amazon-linux-2"],
        case_sensitive=False,
    ),
    default="ubuntu-22.04",
    show_default=True,
    help="Operating system for Deep Learning AMI selection.",
)
@click.option(
    "--architecture",
    type=click.Choice(["x86_64", "arm64"], case_sensitive=False),
    default="x86_64",
    show_default=True,
    help="CPU architecture (x86_64 or ARM64/Graviton).",
)
@click.option(
    "--ami-type",
    type=click.Choice(["base", "pytorch", "tensorflow", "multi-framework"], case_sensitive=False),
    default="base",
    show_default=True,
    help="Deep Learning AMI type (base, pytorch, tensorflow, multi-framework).",
)
@click.option(
    "--use-spot/--no-spot",
    default=True,
    show_default=True,
    help="Use spot instances when available.",
)
@click.option("--budget", type=float, default=None, help="Monthly budget limit in USD.")
@click.option(
    "--vpc-id",
    default=None,
    help="Use an existing VPC id (will be validated).",
)
@click.option(
    "--attach-internet-gateway/--no-attach-internet-gateway",
    default=False,
    show_default=True,
    help="When reusing a VPC, allow GeuseMaker to attach an Internet Gateway and public routes.",
)
@click.option(
    "--use-runtime-bundle/--no-runtime-bundle",
    default=False,
    show_default=True,
    help="Embed the packaged runtime bundle into UserData to reduce on-instance downloads.",
)
@click.option(
    "--runtime-bundle-path",
    default=None,
    help="Optional path to a prebuilt runtime-bundle tar.gz to embed instead of the packaged assets.",
)
@click.option(
    "--subnet-id",
    default=None,
    help="Preferred subnet id when reusing a VPC (must belong to the VPC).",
)
@click.option(
    "--storage-subnet-id",
    default=None,
    help="Subnet id to use for storage/EFS when reusing a VPC (defaults to first private subnet).",
)
@click.option(
    "--public-subnet-id",
    "public_subnet_ids",
    multiple=True,
    help="Public subnet ids to target for compute when reusing a VPC (can be set multiple times).",
)
@click.option(
    "--private-subnet-id",
    "private_subnet_ids",
    multiple=True,
    help="Private subnet ids to target for storage when reusing a VPC (can be set multiple times).",
)
@click.option(
    "--security-group-id",
    default=None,
    help="Reuse an existing security group id (must belong to the VPC).",
)
@click.option("--keypair-name", default=None, help="Use an existing EC2 key pair by name.")
@click.option("--enable-alb/--disable-alb", default=False, help="Enable ALB (Tier 2/3).")
@click.option("--enable-cdn/--disable-cdn", default=False, help="Enable CDN/CloudFront (Tier 3).")
@click.option(
    "--auto-rollback/--no-auto-rollback",
    default=True,
    show_default=True,
    help="Auto-rollback on failures.",
)
@click.option(
    "--rollback-timeout",
    default=15,
    show_default=True,
    help="Rollback timeout in minutes.",
)
@click.option(
    "--skip-validation",
    is_flag=True,
    default=False,
    help="Skip pre-deployment validation checks (use with caution).",
)
@output_option()
@click.pass_context
def deploy(
    ctx: click.Context,
    config: str | None,
    interactive: bool | None,
    stack_name: str | None,
    tier: str,
    region: str,
    instance_type: str,
    os_type: str,
    architecture: str,
    ami_type: str,
    use_spot: bool,
    budget: float | None,
    vpc_id: str | None,
    attach_internet_gateway: bool,
    use_runtime_bundle: bool,
    runtime_bundle_path: str | None,
    subnet_id: str | None,
    storage_subnet_id: str | None,
    public_subnet_ids: tuple[str, ...],
    private_subnet_ids: tuple[str, ...],
    security_group_id: str | None,
    keypair_name: str | None,
    enable_alb: bool,
    enable_cdn: bool,
    auto_rollback: bool,
    rollback_timeout: int,
    skip_validation: bool,
    output: str,
) -> None:
    """Create a new deployment (config build + AWS client bootstrap)."""
    # Show the wicked deploy banner
    console.print(DEPLOY_BANNER)
    console.print()

    factory = AWSClientFactory()
    state_manager = StateManager()
    loader = ConfigLoader()
    output_format = OutputFormat(output.lower())

    interactive_requested = interactive if interactive is not None else (stack_name is None and config is None)
    cli_overrides = _collect_overrides(
        ctx,
        stack_name=stack_name,
        tier=tier.lower(),
        region=region,
        instance_type=instance_type,
        os_type=os_type.lower(),
        architecture=architecture.lower(),
        ami_type=ami_type.lower(),
        use_spot=use_spot,
        budget_limit=Decimal(str(budget)) if budget is not None else None,
        vpc_id=vpc_id,
        attach_internet_gateway=attach_internet_gateway,
        use_runtime_bundle=use_runtime_bundle,
        runtime_bundle_path=runtime_bundle_path,
        subnet_id=subnet_id,
        storage_subnet_id=storage_subnet_id,
        public_subnet_ids=list(public_subnet_ids) or None,
        private_subnet_ids=list(private_subnet_ids) or None,
        security_group_id=security_group_id,
        keypair_name=keypair_name,
        enable_alb=enable_alb,
        enable_cdn=enable_cdn,
        auto_rollback_on_failure=auto_rollback,
        rollback_timeout_minutes=rollback_timeout,
    )

    if interactive_requested:
        prefill = loader.env_overrides()
        prefill.update({k: v for k, v in cli_overrides.items() if v is not None})
        initial_state = {
            "stack_name": prefill.get("stack_name", stack_name),
            "tier": prefill.get("tier", tier.lower()),
            "region": prefill.get("region", region),
            "use_spot": prefill.get("use_spot", use_spot),
            "instance_type": prefill.get("instance_type", instance_type),
            "os_type": prefill.get("os_type", os_type.lower()),
            "architecture": prefill.get("architecture", architecture.lower()),
            "ami_type": prefill.get("ami_type", ami_type.lower()),
            "budget_limit": prefill.get("budget_limit"),
            "vpc_id": prefill.get("vpc_id", vpc_id),
            "attach_internet_gateway": prefill.get("attach_internet_gateway", attach_internet_gateway),
            "use_runtime_bundle": prefill.get("use_runtime_bundle", use_runtime_bundle),
            "runtime_bundle_path": prefill.get("runtime_bundle_path", runtime_bundle_path),
            "subnet_id": prefill.get("subnet_id", subnet_id),
            "storage_subnet_id": prefill.get("storage_subnet_id", storage_subnet_id),
            "public_subnet_ids": prefill.get("public_subnet_ids", list(public_subnet_ids) or None),
            "private_subnet_ids": prefill.get("private_subnet_ids", list(private_subnet_ids) or None),
            "security_group_id": prefill.get("security_group_id", security_group_id),
            "keypair_name": prefill.get("keypair_name", keypair_name),
            "enable_alb": prefill.get("enable_alb", enable_alb),
            "enable_cdn": prefill.get("enable_cdn", enable_cdn),
            "auto_rollback_on_failure": prefill.get("auto_rollback_on_failure", auto_rollback),
            "rollback_timeout_minutes": prefill.get("rollback_timeout_minutes", rollback_timeout),
        }
        if not console.is_terminal:
            console.print(
                f"{EMOJI['warning']} Interactive mode requires a TTY. Provide CLI options or a config file.",
                verbosity="error",
            )
            raise SystemExit(1)
        deployer = InteractiveDeployer(
            client_factory=factory,
            state_manager=state_manager,
            skip_validation=skip_validation,
        )
        deployer.run(initial_state=initial_state)
        return

    try:
        config_model = loader.load(
            config_path=Path(config) if config else None,
            cli_overrides=cli_overrides,
        )
    except ConfigurationError as exc:
        error_payload = build_response(
            status="error",
            message=str(exc),
            errors=exc.details or [],
            error_code="validation",
        )
        _emit_error(error_payload, output_format)
        raise SystemExit(2)

    runner = DeploymentRunner(factory, state_manager=state_manager)
    try:
        state = runner.run(config_model, skip_validation=skip_validation)
    except DeploymentValidationFailed:
        error_payload = build_response(
            status="error",
            message="Deployment validation failed; see report above.",
            error_code="validation",
        )
        _emit_error(error_payload, output_format)
        raise SystemExit(2)
    except Exception as exc:  # noqa: BLE001
        error_payload = build_response(
            status="error",
            message=f"Deployment failed: {exc}",
            error_code="deployment",
        )
        _emit_error(error_payload, output_format)
        raise SystemExit(1)

    success_payload = build_response(
        status="ok",
        message=(f"Deployment created: {state.stack_name} status {state.status} in {state.config.region}."),
        data={
            "stack_name": state.stack_name,
            "status": state.status,
            "region": state.config.region,
        },
    )

    if output_format == OutputFormat.TEXT:
        console.print(
            f"{EMOJI['rocket']} Deployment created: [bold]{state.stack_name}[/bold] "
            f"status [bold]{state.status}[/bold] in [bold]{state.config.region}[/bold].",
            verbosity="result",
        )
        return

    emit_result(success_payload, output_format)


__all__ = ["deploy"]
