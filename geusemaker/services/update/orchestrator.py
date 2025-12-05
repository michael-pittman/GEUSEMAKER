"""Update orchestrator coordinates instance and container updates."""

from __future__ import annotations

import asyncio
from time import monotonic

from geusemaker.infra import AWSClientFactory, StateManager
from geusemaker.models import DeploymentState
from geusemaker.models.update import UpdateRequest, UpdateResult
from geusemaker.services.update.containers import ContainerUpdater
from geusemaker.services.update.instance import InstanceUpdater


class UpdateOrchestrator:
    """Apply updates to an existing deployment."""

    def __init__(
        self,
        client_factory: AWSClientFactory | None = None,
        state_manager: StateManager | None = None,
        region: str = "us-east-1",
        instance_updater: InstanceUpdater | None = None,
        container_updater: ContainerUpdater | None = None,
    ):
        self.client_factory = client_factory or AWSClientFactory()
        self.state_manager = state_manager or StateManager()
        self.region = region
        self.instance_updater = instance_updater or InstanceUpdater(self.client_factory, region=region)
        self.container_updater = container_updater or ContainerUpdater(self.client_factory, region=region)

    def update(self, request: UpdateRequest, state: DeploymentState | None = None) -> UpdateResult:
        """Apply requested changes and persist updated state."""
        start = monotonic()
        deployment = state or asyncio.run(self.state_manager.load_deployment(request.deployment_name))
        if deployment is None:
            raise ValueError(f"Deployment '{request.deployment_name}' not found.")

        errors = self._validate_request(deployment, request)
        if errors:
            raise ValueError("; ".join(errors))

        previous_state = deployment.model_dump()
        deployment.last_healthy_state = previous_state
        deployment.previous_states.insert(0, previous_state)
        deployment.previous_states = deployment.previous_states[:5]
        deployment.status = "updating"
        asyncio.run(self.state_manager.save_deployment(deployment))

        changes: list[str] = []
        warnings: list[str] = []

        if request.instance_type:
            if request.instance_type == deployment.config.instance_type:
                warnings.append("Instance type unchanged; skipping instance update.")
            else:
                changes.extend(self.instance_updater.update_instance_type(deployment, request.instance_type))

        if request.container_images:
            changed_images = {
                name: ref
                for name, ref in request.container_images.items()
                if deployment.container_images.get(name) != ref
            }
            if changed_images:
                changes.extend(self.container_updater.update_container_images(deployment, changed_images))
            else:
                warnings.append("Container images unchanged; skipping container update.")

        if not changes:
            raise ValueError("No update actions to apply.")

        deployment.status = "running"
        asyncio.run(self.state_manager.save_deployment(deployment))

        duration = monotonic() - start
        return UpdateResult(
            success=True,
            changes_applied=changes,
            previous_state=previous_state,
            new_state=deployment.model_dump(),
            duration_seconds=duration,
            warnings=warnings,
        )

    def _validate_request(self, deployment: DeploymentState, request: UpdateRequest) -> list[str]:
        errors: list[str] = []

        if not request.instance_type and not request.container_images:
            errors.append("At least one update option (--instance-type or --image) is required.")

        if request.instance_type and len(request.instance_type) < 2:
            errors.append("Instance type must be a valid EC2 instance family (e.g., t3.medium).")

        if request.container_images:
            for name, ref in request.container_images.items():
                if not name or not ref:
                    errors.append("Container image overrides must include a name and reference.")
        if not deployment.efs_id:
            errors.append("Deployment does not have an EFS ID; cannot ensure data preservation.")

        return errors


__all__ = ["UpdateOrchestrator"]
