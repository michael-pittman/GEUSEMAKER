from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from geusemaker.models import CostTracking, DeploymentConfig, DeploymentState
from geusemaker.services.update.containers import ContainerUpdater


class StubSSM:
    def __init__(self) -> None:
        self.last_commands: list[str] | None = None
        self.last_instance: str | None = None

    def run_shell_script(self, instance_id, commands, comment=None, timeout_seconds=900):  # type: ignore[no-untyped-def]
        self.last_instance = instance_id
        self.last_commands = commands
        return {"Status": "Success", "CommandId": "cmd-1"}


def _state(instance_id: str = "i-123") -> DeploymentState:
    config = DeploymentConfig(stack_name="demo", tier="dev")
    cost = CostTracking(
        instance_type="t3.medium",
        is_spot=True,
        spot_price_per_hour=Decimal("0.0125"),
        on_demand_price_per_hour=Decimal("0.0416"),
        estimated_monthly_cost=Decimal("25.0"),
    )
    return DeploymentState(
        stack_name="demo",
        status="running",
        vpc_id="vpc-1",
        subnet_ids=["subnet-1"],
        security_group_id="sg-1",
        efs_id="fs-1",
        efs_mount_target_id="mt-1",
        instance_id=instance_id,
        keypair_name="kp",
        private_ip="10.0.0.10",
        public_ip="1.2.3.4",
        n8n_url="http://example.com",
        cost=cost,
        config=config,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def test_container_updater_invokes_ssm_and_updates_state() -> None:
    state = _state()
    ssm = StubSSM()
    updater = ContainerUpdater(ssm_service=ssm)

    changes = updater.update_container_images(state, {"n8n": "n8nio/n8n:latest"})

    assert "n8n" in state.container_images
    assert ssm.last_instance == "i-123"
    assert ssm.last_commands and "docker compose" in ssm.last_commands[0]
    assert changes == ["n8n -> n8nio/n8n:latest"]
