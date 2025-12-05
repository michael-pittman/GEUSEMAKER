"""Cost command to estimate deployment expenses."""

from __future__ import annotations

from decimal import Decimal

import click

from geusemaker.cli import console
from geusemaker.cli.branding import EMOJI
from geusemaker.cli.display import (
    render_budget_status,
    render_cost_estimate,
    render_cost_history,
    render_pricing_summary,
)
from geusemaker.cli.output import (
    OutputFormat,
    build_response,
    emit_result,
    output_option,
)
from geusemaker.infra import AWSClientFactory
from geusemaker.models import DeploymentConfig
from geusemaker.services.compute import SpotSelectionService
from geusemaker.services.cost import BudgetService, CostEstimator, CostReportService
from geusemaker.services.pricing import PricingService


@click.command("cost")
@click.option("--stack-name", "-s", required=True, help="Stack/deployment name.")
@click.option(
    "--tier",
    type=click.Choice(["dev", "automation", "gpu"], case_sensitive=False),
    default="dev",
    show_default=True,
    help="Deployment tier to estimate.",
)
@click.option("--region", default="us-east-1", show_default=True, help="AWS region.")
@click.option("--instance-type", default="t3.medium", show_default=True, help="EC2 instance type.")
@click.option("--spot/--no-spot", default=True, show_default=True, help="Use spot instances.")
@click.option("--budget", type=float, default=None, help="Monthly budget limit in USD.")
@click.option("--storage-gb", type=float, default=100.0, show_default=True, help="EFS storage size (GB).")
@click.option(
    "--data-transfer-gb",
    type=float,
    default=100.0,
    show_default=True,
    help="Monthly data transfer out (GB).",
)
@click.option(
    "--cloudfront-requests",
    type=int,
    default=1_000_000,
    show_default=True,
    help="Monthly CloudFront requests (for GPU/CDN tiers).",
)
@click.option("--alb-lcus", type=float, default=1.0, show_default=True, help="Expected ALB LCUs.")
@output_option()
def cost(
    stack_name: str,
    tier: str,
    region: str,
    instance_type: str,
    spot: bool,
    budget: float | None,
    storage_gb: float,
    data_transfer_gb: float,
    cloudfront_requests: int,
    alb_lcus: float,
    output: str,
) -> None:
    """Show cost estimates or actuals."""
    output_format = OutputFormat(output.lower())
    console.print(f"{EMOJI['spark']} Estimating costs for [bold]{stack_name}[/bold]...", verbosity="info")

    config = DeploymentConfig(
        stack_name=stack_name,
        tier=tier,
        region=region,
        instance_type=instance_type,
        use_spot=spot,
        enable_alb=tier in ("automation", "gpu"),
        enable_cdn=tier == "gpu",
    )

    client_factory = AWSClientFactory()
    pricing_service = PricingService(client_factory, region=region)
    spot_selector = SpotSelectionService(
        client_factory=client_factory,
        pricing_service=pricing_service,
        region=region,
    )
    estimator = CostEstimator(
        client_factory=client_factory,
        pricing_service=pricing_service,
        region=region,
        spot_selector=spot_selector,
    )
    budget_service = BudgetService()
    report_service = CostReportService()

    try:
        estimate = estimator.estimate_deployment_cost(
            config=config,
            storage_gb=storage_gb,
            data_transfer_gb=data_transfer_gb,
            cloudfront_requests=cloudfront_requests,
            alb_lcus=alb_lcus,
        )
    except Exception as exc:  # noqa: BLE001
        error_payload = build_response(
            status="error",
            message=f"Failed to calculate cost estimate: {exc}",
            error_code="cost_estimate",
        )
        if output_format == OutputFormat.TEXT:
            console.print(f"{EMOJI['warn']} Failed to calculate cost estimate: {exc}", verbosity="error")
        else:
            emit_result(error_payload, output_format)
        raise SystemExit(1)

    selection = spot_selector.select_instance_type(config)
    analysis = spot_selector.analyze_spot_prices(config.instance_type, config.region)
    budget_status = budget_service.check_budget(estimate, Decimal(str(budget))) if budget else None
    history = []
    report = report_service.build_report(estimate, runtime_hours=0.0, budget_status=budget_status, cost_history=history)

    if output_format == OutputFormat.TEXT:
        render_pricing_summary(selection, analysis)
        render_cost_estimate(estimate)
        render_budget_status(budget_status)
        render_cost_history(history)
        console.print(
            f"{EMOJI['info']} Cost report generated for [bold]{stack_name}[/bold]. "
            f"Estimated monthly: ${estimate.monthly_cost:.2f}.",
            verbosity="result",
        )
        return

    payload = build_response(
        status="ok",
        message="Cost estimate generated.",
        data={
            "estimate": estimate.model_dump(mode="json"),
            "budget_status": budget_status.model_dump(mode="json") if budget_status else None,
            "report": report.model_dump(mode="json"),
        },
    )
    emit_result(payload, output_format)


__all__ = ["cost"]
