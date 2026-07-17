"""Shared deployment runner used by interactive and non-interactive flows."""

from __future__ import annotations

from dataclasses import dataclass

from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from geusemaker.cli import console
from geusemaker.cli.branding import EMOJI
from geusemaker.cli.components.stage import print_stage
from geusemaker.cli.display.cost import render_budget_status
from geusemaker.cli.display.validation import render_validation_report
from geusemaker.cli.output import is_machine_output
from geusemaker.cli.progress_events import ProgressCallback, ProgressEvent
from geusemaker.infra import AWSClientFactory, StateManager
from geusemaker.models import DeploymentConfig, DeploymentState
from geusemaker.orchestration import Tier1Orchestrator, Tier2Orchestrator, Tier3Orchestrator
from geusemaker.services.acm import ACMService
from geusemaker.services.compute.spot import SpotSelectionService
from geusemaker.services.cost import BudgetService, CostEstimator
from geusemaker.services.instance_resolver import InstanceResolver
from geusemaker.services.pricing import PricingService
from geusemaker.services.route53 import Route53Service
from geusemaker.services.ssm import SSMService
from geusemaker.services.validation import PreDeploymentValidator


@dataclass
class DeploymentValidationFailed(Exception):
    """Raised when validation fails during deployment."""

    report: object


class DeploymentRunner:
    """Execute validation + orchestrator with optional progress hooks."""

    def __init__(
        self,
        client_factory: AWSClientFactory | None = None,
        state_manager: StateManager | None = None,
    ):
        self.client_factory = client_factory or AWSClientFactory()
        self.state_manager = state_manager or StateManager()

    def _stream_userdata_logs(self, state: DeploymentState) -> None:
        """Stream UserData initialization logs in real time from the deployed instance."""
        if not state.instance_id and not getattr(state, "auto_scaling_group_name", None):
            return

        # Machine output reserves stdout for one structured document; the Rich Live
        # panel writes directly to the console, so skip streaming entirely.
        if is_machine_output():
            return

        ssm_service = SSMService(self.client_factory, region=state.config.region)

        try:
            instance_id = InstanceResolver(self.client_factory, region=state.config.region).resolve(state).instance_id
            self.state_manager.save_deployment_sync(state)
            console.print(
                f"\n{EMOJI['info']} Streaming UserData initialization logs...",
                verbosity="info",
            )

            # Collect log lines for display in panel
            log_lines: list[str] = []

            # Create initial panel
            panel = Panel(
                Text("Waiting for logs...", style="dim"),
                title=f"{EMOJI['log']} UserData Initialization",
                border_style="cyan",
                expand=False,
            )

            # Use Live context to update panel with streaming logs
            with Live(panel, console=console, refresh_per_second=4) as live:
                for log_line in ssm_service.stream_userdata_logs(
                    instance_id=instance_id,
                    poll_interval=2.0,
                    timeout_seconds=600,
                ):
                    log_lines.append(log_line)
                    # Show last 20 lines in the panel
                    display_lines = log_lines[-20:]
                    log_text = "\n".join(display_lines)

                    # Update panel with new content
                    live.update(
                        Panel(
                            Text(log_text, style="white", overflow="fold"),
                            title=f"{EMOJI['log']} UserData Initialization",
                            border_style="cyan",
                            expand=False,
                        )
                    )

            # The stream also ends on error-guard detection or timeout, so check the
            # actual outcome instead of unconditionally declaring success.
            try:
                final_status = ssm_service.get_userdata_status(instance_id)
            except RuntimeError:
                final_status = "unknown"

            if final_status == "success":
                console.print(
                    f"\n{EMOJI['check']} UserData initialization complete!",
                    verbosity="info",
                )
            elif final_status == "error":
                console.print(
                    f"\n{EMOJI['error']} UserData initialization FAILED — services did not start. "
                    f"Inspect with: geusemaker logs {state.stack_name}",
                    verbosity="error",
                )
            else:
                console.print(
                    f"\n{EMOJI['warning']} UserData still initializing (status: {final_status}). "
                    f"Check progress with: geusemaker logs {state.stack_name} --follow",
                    verbosity="warning",
                )

        except RuntimeError as exc:
            console.print(
                f"{EMOJI['warning']} Could not stream UserData logs: {exc}",
                verbosity="warning",
            )

    def run(
        self,
        config: DeploymentConfig,
        progress: object | None = None,
        skip_validation: bool = False,
        on_progress: ProgressCallback | None = None,
    ) -> DeploymentState:
        """Validate configuration and run the Tier1 orchestrator."""
        emit = on_progress or print_stage
        # Normalize tier-related feature flags
        updates: dict[str, object] = {}
        if config.tier == "automation" and not config.enable_alb:
            updates["enable_alb"] = True
        if config.tier == "gpu":
            if not config.enable_alb:
                updates["enable_alb"] = True
            if not config.enable_cdn:
                updates["enable_cdn"] = True
        # The 15-minute default rollback timeout cannot fit a CDN deployment:
        # ACM issuance + instance + ALB alone take ~15 minutes before CloudFront's
        # 15-30 minute rollout begins, so the default would abort every healthy
        # Tier 3 deploy. Scale it up unless the user chose a larger value.
        if (config.enable_cdn or config.tier == "gpu") and config.rollback_timeout_minutes <= 15:
            updates["rollback_timeout_minutes"] = 60
        if updates:
            config = config.model_copy(update=updates)
            console.print(
                f"{EMOJI['info']} Adjusted config for tier '{config.tier}': "
                f"{', '.join(f'{k}={v}' for k, v in updates.items())}",
                verbosity="info",
            )

        pricing_service = PricingService(self.client_factory, region=config.region)
        spot_selector = SpotSelectionService(
            self.client_factory,
            pricing_service=pricing_service,
            region=config.region,
        )
        cost_estimator = CostEstimator(
            self.client_factory,
            pricing_service=pricing_service,
            region=config.region,
            spot_selector=spot_selector,
        )
        budget_service = BudgetService()

        emit(ProgressEvent("spot", f"Selecting compute capacity for {config.instance_type}"))
        selection = spot_selector.select_instance_type(config)
        estimate = cost_estimator.estimate_deployment_cost(config, selection=selection)
        budget_status = budget_service.check_budget(estimate, config.budget_limit)
        render_budget_status(budget_status)
        if budget_status and budget_status.status == "exceeded":
            raise DeploymentValidationFailed(budget_status)

        if skip_validation:
            console.print(
                f"{EMOJI['warning']} Skipping pre-deployment validation (--skip-validation).",
                verbosity="info",
            )
        else:
            emit(ProgressEvent("validate", "Running pre-deployment validation"))
            validator = PreDeploymentValidator(self.client_factory, region=config.region)
            if progress:
                try:
                    progress.start_step("Validating configuration")
                except AttributeError:
                    pass
            report = validator.validate(config)
            console.print(render_validation_report(report), verbosity="info")
            if not getattr(report, "passed", True):
                console.print(
                    f"{EMOJI['warning']} Pre-deployment validation failed; fix issues and retry.",
                    verbosity="error",
                )
                raise DeploymentValidationFailed(report)

        # Tier 2/3 HTTPS: auto-provision an ALB ACM cert via Route 53 when requested.
        if config.enable_https and config.enable_alb and not config.alb_certificate_arn:
            if config.alb_domain_name and config.alb_hosted_zone_id:
                if progress:
                    try:
                        progress.advance("Provisioning ACM certificate")
                    except AttributeError:
                        pass

                console.print(
                    f"{EMOJI['info']} Requesting ACM certificate for {config.alb_domain_name} (DNS validation)...",
                    verbosity="info",
                )
                acm = ACMService(self.client_factory, region=config.region)
                r53 = Route53Service(self.client_factory)
                tags = [
                    {"Key": "Name", "Value": f"{config.stack_name}-alb-cert"},
                    {"Key": "Stack", "Value": config.stack_name},
                    {"Key": "Tier", "Value": config.tier},
                    {"Key": "ManagedBy", "Value": "GeuseMaker"},
                ]
                cert_arn = acm.request_dns_certificate(config.alb_domain_name, tags=tags)

                console.print(
                    f"{EMOJI['info']} Waiting for ACM DNS validation record to be generated...",
                    verbosity="info",
                )
                rr_name, rr_type, rr_value = acm.wait_for_dns_validation_record(
                    cert_arn,
                    timeout_seconds=300,
                    poll_interval_seconds=5.0,
                )
                change_id = r53.upsert_record(
                    hosted_zone_id=config.alb_hosted_zone_id,
                    name=rr_name,
                    record_type=rr_type,
                    value=rr_value,
                    ttl=60,
                )
                if change_id:
                    r53.wait_for_change(change_id)

                console.print(
                    f"{EMOJI['info']} Waiting for ACM certificate to be issued...",
                    verbosity="info",
                )
                acm.wait_for_issued(cert_arn, timeout_seconds=900)

                config = config.model_copy(update={"alb_certificate_arn": cert_arn})
                console.print(
                    f"{EMOJI['check']} ACM certificate issued: {cert_arn}",
                    verbosity="info",
                )
            else:
                # enable_https defaults to True, so configs written before HTTPS support
                # must keep deploying. Fall back to an HTTP-only ALB instead of failing.
                console.print(
                    f"{EMOJI['warning']} HTTPS requested but no --alb-certificate-arn or "
                    "(alb_domain_name + alb_hosted_zone_id) provided; deploying HTTP-only ALB. "
                    "Provide a certificate ARN or a Route 53 domain to enable HTTPS.",
                    verbosity="warning",
                )
                config = config.model_copy(update={"enable_https": False})

        if progress:
            try:
                progress.advance("Provisioning resources")
            except AttributeError:
                pass

        orchestrator = self._select_orchestrator(
            config,
            pricing_service=pricing_service,
            spot_selector=spot_selector,
        )
        # Share pre-selected compute choice to align AZ + pricing with validation
        orchestrator._preselected_selection = selection
        primary_stage = "cdn" if config.enable_cdn or config.tier == "gpu" else "alb" if config.enable_alb else "ec2"
        emit(ProgressEvent(primary_stage, f"Provisioning {config.topology} topology"))
        state = orchestrator.deploy(config, enable_rollback=config.auto_rollback_on_failure)

        # Stream UserData initialization logs after deployment
        if progress:
            try:
                progress.advance("Streaming initialization logs")
            except AttributeError:
                pass
        emit(ProgressEvent("userdata", "Streaming instance initialization"))
        self._stream_userdata_logs(state)

        if progress:
            try:
                progress.advance("Saving state")
            except AttributeError:
                pass
        emit(ProgressEvent("finalize", f"Deployment state saved for {state.stack_name}"))
        return state

    def _select_orchestrator(
        self,
        config: DeploymentConfig,
        pricing_service: PricingService,
        spot_selector: SpotSelectionService,
    ):
        if config.enable_cdn or config.tier == "gpu":
            return Tier3Orchestrator(
                self.client_factory,
                region=config.region,
                state_manager=self.state_manager,
                pricing_service=pricing_service,
                spot_selector=spot_selector,
            )
        if config.enable_alb or config.tier == "automation":
            return Tier2Orchestrator(
                self.client_factory,
                region=config.region,
                state_manager=self.state_manager,
                pricing_service=pricing_service,
                spot_selector=spot_selector,
            )
        return Tier1Orchestrator(
            self.client_factory,
            region=config.region,
            state_manager=self.state_manager,
            pricing_service=pricing_service,
            spot_selector=spot_selector,
        )


__all__ = ["DeploymentRunner", "DeploymentValidationFailed"]
