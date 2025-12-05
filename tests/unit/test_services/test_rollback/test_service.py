from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from geusemaker.models import CostTracking, DeploymentConfig, DeploymentState
from geusemaker.services.rollback.service import RollbackService


class StubStateManager:
    def __init__(self, state: DeploymentState):
        self.state = state
        self.saved_state: DeploymentState | None = None

    async def save_deployment(self, state: DeploymentState) -> None:
        self.saved_state = state

    async def load_deployment(self, stack_name: str) -> DeploymentState | None:  # noqa: ARG002
        return self.state


class StubInstanceUpdater:
    def __init__(self) -> None:
        self.last_type: str | None = None

    def update_instance_type(self, state: DeploymentState, new_type: str):  # type: ignore[no-untyped-def]
        self.last_type = new_type
        state.config = state.config.model_copy(update={"instance_type": new_type})
        return [f"instance_type:{new_type}"]


class StubContainerUpdater:
    def update_container_images(self, state: DeploymentState, images: dict[str, str]):  # type: ignore[no-untyped-def]
        state.container_images = images
        return ["container_images:rolled_back"]


def _state(instance_type: str = "t3.large") -> DeploymentState:
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
        container_images={"n8n": "n8nio/n8n:new"},
    )


def test_rollback_reverts_to_previous_state() -> None:
    state = _state()
    previous_snapshot = state.model_dump()
    previous_snapshot["config"]["instance_type"] = "t3.medium"
    previous_snapshot["container_images"] = {"n8n": "n8nio/n8n:old"}
    state.previous_states = [previous_snapshot]

    service = RollbackService(
        state_manager=StubStateManager(state),
        instance_updater=StubInstanceUpdater(),
        container_updater=StubContainerUpdater(),
    )

    result = service.rollback(state, to_version=1)

    assert result.success is True
    assert state.config.instance_type == "t3.medium"
    assert state.container_images.get("n8n") == "n8nio/n8n:old"
    assert state.rollback_history


def test_rollback_errors_on_invalid_version() -> None:
    state = _state()
    state.previous_states = []
    service = RollbackService(state_manager=StubStateManager(state))

    with pytest.raises(ValueError):
        service.rollback(state, to_version=2)
