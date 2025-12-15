"""Rollback service for state/version reverts (not resource cleanup)."""

from __future__ import annotations

from time import monotonic

from geusemaker.infra import AWSClientFactory, StateManager
from geusemaker.models import DeploymentState, RollbackRecord
from geusemaker.models.rollback import RollbackResult
from geusemaker.services.update import ContainerUpdater, InstanceUpdater


class RollbackService:
    """Rollback a deployment to a previous saved snapshot (state versioning, not resource deletion)."""

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

    def rollback(
        self,
        state: DeploymentState,
        to_version: int = 1,
        trigger: str = "manual",
    ) -> RollbackResult:
        """Rollback to a previous known-good state."""
        start = monotonic()
        if not state.previous_states:
            raise ValueError("No rollback history available.")
        if to_version < 1 or to_version > len(state.previous_states):
            raise ValueError(f"Rollback version {to_version} is out of range (max {len(state.previous_states)}).")

        history = list(state.previous_states)
        target_snapshot = history[to_version - 1]
        target_state = DeploymentState.model_validate(target_snapshot)

        current_snapshot = state.model_dump()
        history.insert(0, current_snapshot)
        state.previous_states = history[:5]
        state.status = "rolling_back"
        self.state_manager.save_deployment_sync(state)

        changes: list[str] = []

        if target_state.config.instance_type != state.config.instance_type:
            changes.extend(
                self.instance_updater.update_instance_type(state, target_state.config.instance_type),
            )

        if target_state.container_images != state.container_images:
            state.container_images = dict(target_state.container_images)
            changes.append("container_images:rolled_back")

        state.config = target_state.config
        state.cost.instance_type = target_state.config.instance_type
        state.last_healthy_state = target_snapshot
        state.status = "running"

        state.rollback_history.append(
            RollbackRecord(
                timestamp=state.updated_at,
                trigger=trigger,  # type: ignore[arg-type]
                resources_deleted=[],
                success=True,
                previous_state_version=to_version,
                rolled_back_changes=changes,
            ),
        )
        self.state_manager.save_deployment_sync(state)

        duration = monotonic() - start
        return RollbackResult(
            success=True,
            trigger=trigger,
            changes_reverted=changes,
            duration_seconds=duration,
            health_status={},
        )


__all__ = ["RollbackService"]
