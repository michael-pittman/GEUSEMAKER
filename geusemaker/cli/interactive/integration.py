"""Integration layer that ties the interactive flow to the deployment runner."""

from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import urlparse

import yaml

from geusemaker.cli.components import ProgressTracker, messages, spinner, tables
from geusemaker.cli.interactive.flow import InteractiveAbort, InteractiveFlow
from geusemaker.cli.interactive.runner import (
    DeploymentRunner,
    DeploymentValidationFailed,
)
from geusemaker.infra import AWSClientFactory, StateManager
from geusemaker.models import DeploymentConfig, DeploymentState
from geusemaker.services.destruction import DestructionService


class InteractiveDeployer:
    """High-level controller for interactive deployments."""

    def __init__(
        self,
        client_factory: AWSClientFactory | None = None,
        state_manager: StateManager | None = None,
        skip_validation: bool = False,
    ):
        self.client_factory = client_factory or AWSClientFactory()
        self.state_manager = state_manager or StateManager()
        self.runner = DeploymentRunner(self.client_factory, self.state_manager)
        self.skip_validation = skip_validation

    def run(self, initial_state: dict | None = None) -> DeploymentState | None:
        """Execute interactive flow + deployment; returns state or None if aborted."""
        flow = InteractiveFlow(
            client_factory=self.client_factory,
            session_store=None,
            initial_state=initial_state,
        )
        try:
            config = flow.run()
        except InteractiveAbort as exc:
            messages.warning(f"Interactive mode aborted: {exc}")
            return None

        try:
            steps = ["deploy", "finalize"] if self.skip_validation else ["validate", "deploy", "finalize"]
            with ProgressTracker(steps=steps) as tracker:
                if not self.skip_validation:
                    tracker.start_step("Validating configuration")
                state = self.runner.run(config, progress=tracker, skip_validation=self.skip_validation)
                tracker.advance("Deployment completed")
        except DeploymentValidationFailed:
            messages.error("Validation failed; fix issues and rerun.")
            return None
        except KeyboardInterrupt:
            self._cleanup_on_abort(config.stack_name, config.region)
            raise
        except Exception as exc:  # noqa: BLE001
            messages.error(f"Deployment failed: {exc}")
            self._cleanup_on_abort(config.stack_name, config.region)
            return None

        messages.success(
            f"Deployment created: [bold]{state.stack_name}[/bold] in [bold]{state.config.region}[/bold].",
        )
        self._show_summary(state)
        self._maybe_export_config(config)
        return state

    def _cleanup_on_abort(self, stack_name: str, region: str) -> None:
        """Best-effort cleanup when deployment is interrupted."""
        messages.warning("Attempting cleanup after abort...")
        try:
            state = asyncio.run(self.state_manager.load_deployment(stack_name))
        except Exception:  # noqa: BLE001
            state = None
        if not state:
            messages.info("No deployment state found; nothing to clean up.")
            return
        with spinner("Destroying created resources"):
            destroyer = DestructionService(
                client_factory=self.client_factory,
                state_manager=self.state_manager,
                region=region,
            )
            destroyer.destroy(state)
        messages.success("Cleanup complete.")

    def _show_summary(self, state: DeploymentState) -> None:
        host = state.public_ip or state.private_ip
        
        # Build URLs based on tier
        if state.config.tier == "dev":
            # Tier 1: HTTPS through Nginx proxy
            protocol = "https"
            n8n_url = f"{protocol}://{host}" if host else "-"
            qdrant_ui_url = f"{protocol}://{host}/qdrant-ui/" if host else "-"
        elif state.config.tier == "automation":
            # Tier 2: Use ALB DNS (already in n8n_url)
            n8n_url = state.n8n_url or "-"
            # Extract host from n8n_url for qdrant-ui
            if state.n8n_url:
                parsed = urlparse(state.n8n_url)
                qdrant_ui_url = f"{parsed.scheme}://{parsed.netloc}/qdrant-ui/"
            else:
                qdrant_ui_url = "-"
        else:  # Tier 3 (gpu)
            # Tier 3: Use CloudFront domain (already in n8n_url)
            n8n_url = state.n8n_url or "-"
            if state.n8n_url:
                parsed = urlparse(state.n8n_url)
                qdrant_ui_url = f"{parsed.scheme}://{parsed.netloc}/qdrant-ui/"
            else:
                qdrant_ui_url = "-"
        
        summary = [
            f"Status: {state.status}",
            f"Region: {state.config.region}",
            f"Public IP: {state.public_ip or '-'}",
            f"SSH: ssh ubuntu@{host or 'unknown'}",
            f"n8n: {n8n_url}",
            f"Qdrant Dashboard: {qdrant_ui_url}",
        ]
        tables.resource_recommendations_panel(summary)

    def _maybe_export_config(self, config: DeploymentConfig) -> None:
        from geusemaker.cli.interactive.prompts import InteractivePrompts

        prompts = InteractivePrompts()
        if not prompts.confirm_export():
            return
        path = self._export_config(config)
        messages.success(f"Config exported to {path}")

    def _export_config(self, config: DeploymentConfig) -> Path:
        target_dir = self.state_manager.config_path
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{config.stack_name}.yaml"
        data = config.model_dump(mode="json", exclude_none=True)
        target.write_text(yaml.safe_dump(data, sort_keys=False))
        return target


__all__ = ["InteractiveDeployer"]
