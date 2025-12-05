"""Shared deployment runner used by interactive and non-interactive flows."""

from __future__ import annotations

from dataclasses import dataclass

from rich.panel import Panel

from geusemaker.cli import console
from geusemaker.cli.branding import EMOJI
from geusemaker.cli.display.validation import render_validation_report
from geusemaker.infra import AWSClientFactory, StateManager
from geusemaker.models import DeploymentConfig, DeploymentState
from geusemaker.orchestration import Tier1Orchestrator
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
            console.print(
                Panel(
                    "",
                    title=f"{EMOJI['log']} UserData Initialization",
                    border_style="cyan",
                    expand=False,
                ),
                verbosity="info",
            )

            # Stream logs in real time
            for log_line in ssm_service.stream_userdata_logs(
                instance_id=state.instance_id,
                poll_interval=2.0,
                timeout_seconds=600,
            ):
                console.print(log_line, verbosity="info", highlight=False)

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

        orchestrator = Tier1Orchestrator(
            self.client_factory,
            region=config.region,
            state_manager=self.state_manager,
        )
        state = orchestrator.deploy(config)

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


__all__ = ["DeploymentRunner", "DeploymentValidationFailed"]
