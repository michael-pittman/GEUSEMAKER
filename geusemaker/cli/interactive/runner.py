"""Shared deployment runner used by interactive and non-interactive flows."""

from __future__ import annotations

from dataclasses import dataclass

from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from geusemaker.cli import console
from geusemaker.cli.branding import EMOJI
from geusemaker.cli.display.cost import render_budget_status
from geusemaker.cli.display.validation import render_validation_report
from geusemaker.infra import AWSClientFactory, StateManager
from geusemaker.models import DeploymentConfig, DeploymentState
from geusemaker.orchestration import Tier1Orchestrator, Tier2Orchestrator, Tier3Orchestrator
from geusemaker.services.compute.spot import SpotSelectionService
from geusemaker.services.cost import BudgetService, CostEstimator
from geusemaker.services.pricing import PricingService
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
        if not state.instance_id:
            return

        ssm_service = SSMService(self.client_factory, region=state.config.region)

        try:
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
                    instance_id=state.instance_id,
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

            console.print(
                f"\n{EMOJI['check']} UserData initialization complete!",
                verbosity="info",
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
    ) -> DeploymentState:
        """Validate configuration and run the Tier1 orchestrator."""
        # Normalize tier-related feature flags
        updates: dict[str, object] = {}
        if config.tier == "automation" and not config.enable_alb:
            updates["enable_alb"] = True
        if config.tier == "gpu":
            if not config.enable_alb:
                updates["enable_alb"] = True
            if not config.enable_cdn:
                updates["enable_cdn"] = True
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
        state = orchestrator.deploy(config, enable_rollback=config.auto_rollback_on_failure)

        # Stream UserData initialization logs after deployment
        if progress:
            try:
                progress.advance("Streaming initialization logs")
            except AttributeError:
                pass
        self._stream_userdata_logs(state)

        if progress:
            try:
                progress.advance("Saving state")
            except AttributeError:
                pass
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
