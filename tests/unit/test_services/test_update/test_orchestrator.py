from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from geusemaker.models import CostTracking, DeploymentConfig, DeploymentState
from geusemaker.models.update import UpdateRequest
from geusemaker.services.update.orchestrator import UpdateOrchestrator


class StubStateManager:
    def __init__(self, state: DeploymentState):
        self.state = state
        self.saved_state: DeploymentState | None = None

    async def load_deployment(self, stack_name: str) -> DeploymentState | None:  # noqa: ARG002
        return self.state

    async def save_deployment(self, state: DeploymentState) -> None:
        self.saved_state = state


class StubInstanceUpdater:
    def __init__(self) -> None:
        self.called_with: str | None = None

    def update_instance_type(self, state: DeploymentState, new_type: str):  # type: ignore[no-untyped-def]
        self.called_with = new_type
        state.config = state.config.model_copy(update={"instance_type": new_type})
        return [f"instance_type:{new_type}"]


class StubContainerUpdater:
    def __init__(self) -> None:
        self.updates: dict[str, str] = {}

    def update_container_images(self, state: DeploymentState, images: dict[str, str]):  # type: ignore[no-untyped-def]
        self.updates.update(images)
        state.container_images.update(images)
        return [f"{k} -> {v}" for k, v in images.items()]


def _state(instance_type: str = "t3.medium") -> DeploymentState:
    config = DeploymentConfig(stack_name="demo", tier="dev", instance_type=instance_type)
    cost = CostTracking(
        instance_type=instance_type,
        is_spot=True,
        spot_price_per_hour=Decimal("0.0125"),
        on_demand_price_per_hour=Decimal("0.0416"),
        estimated_monthly_cost=Decimal("25.0"),
    )
    return DeploymentState(
        stack_name=config.stack_name,
        status="running",
        vpc_id="vpc-1",
        subnet_ids=["subnet-1"],
        security_group_id="sg-1",
        efs_id="fs-1",
        efs_mount_target_id="mt-1",
        instance_id="i-1",
        keypair_name="kp",
        private_ip="10.0.0.10",
        public_ip="1.2.3.4",
        n8n_url="http://example.com",
        cost=cost,
        config=config,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def test_update_changes_instance_type_and_records_history() -> None:
    state = _state()
    manager = StubStateManager(state)
    orchestrator = UpdateOrchestrator(
        state_manager=manager,
        instance_updater=StubInstanceUpdater(),
        container_updater=StubContainerUpdater(),
    )

    request = UpdateRequest(deployment_name="demo", instance_type="t3.large")
    result = orchestrator.update(request, state=state)

    assert manager.saved_state is not None
    assert manager.saved_state.config.instance_type == "t3.large"
    assert result.success is True
    assert result.changes_applied == ["instance_type:t3.large"]
    assert manager.saved_state.previous_states


def test_update_errors_when_no_changes_requested() -> None:
    state = _state()
    orchestrator = UpdateOrchestrator(
        state_manager=StubStateManager(state),
        instance_updater=StubInstanceUpdater(),
        container_updater=StubContainerUpdater(),
    )
    request = UpdateRequest(deployment_name="demo")

    with pytest.raises(ValueError):
        orchestrator.update(request, state=state)


def test_update_updates_container_images() -> None:
    state = _state()
    orchestrator = UpdateOrchestrator(
        state_manager=StubStateManager(state),
        instance_updater=StubInstanceUpdater(),
        container_updater=StubContainerUpdater(),
    )
    request = UpdateRequest(deployment_name="demo", container_images={"n8n": "n8nio/n8n:1.0.0"})

    result = orchestrator.update(request, state=state)

    assert "n8n" in state.container_images
    assert result.success is True
