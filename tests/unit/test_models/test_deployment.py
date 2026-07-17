from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from geusemaker.models import (
    CostTracking,
    DeploymentConfig,
    DeploymentSnapshot,
    DeploymentState,
    RollbackRecord,
)


def _build_state(
    config: DeploymentConfig,
    cost: CostTracking,
    *,
    container_images: dict[str, str] | None = None,
) -> DeploymentState:
    return DeploymentState(
        stack_name=config.stack_name,
        status="running",
        vpc_id="vpc-123456",
        subnet_ids=["subnet-aaa"],
        security_group_id="sg-123456",
        efs_id="fs-123456",
        efs_mount_target_id="mt-123456",
        instance_id="i-123456",
        keypair_name="kp-test",
        private_ip="10.0.0.10",
        public_ip="1.2.3.4",
        n8n_url="http://example.com",
        cost=cost,
        config=config,
        container_images=container_images or {},
    )


def test_deployment_config_defaults(sample_config: DeploymentConfig) -> None:
    assert sample_config.region == "us-east-1"
    assert sample_config.instance_type == "t3.medium"
    assert sample_config.use_spot is True
    assert sample_config.os_type == "ubuntu-22.04"
    assert sample_config.architecture == "x86_64"
    assert sample_config.ami_type == "base"
    assert sample_config.enable_alb is False
    assert sample_config.enable_cdn is False
    assert sample_config.auto_rollback_on_failure is True
    assert sample_config.rollback_timeout_minutes == 15


def test_deployment_config_invalid_stack_name() -> None:
    with pytest.raises(ValidationError):
        DeploymentConfig(stack_name="1bad-name", tier="dev")


def test_deployment_config_invalid_ami_values() -> None:
    with pytest.raises(ValidationError):
        DeploymentConfig(stack_name="stack", tier="dev", os_type="windows")  # type: ignore[arg-type]


def test_deployment_state_round_trip(
    sample_config: DeploymentConfig,
    sample_cost: CostTracking,
) -> None:
    state = DeploymentState(
        stack_name=sample_config.stack_name,
        status="creating",
        vpc_id="vpc-123456",
        subnet_ids=["subnet-aaa", "subnet-bbb"],
        security_group_id="sg-123456",
        efs_id="fs-123456",
        efs_mount_target_id="mt-123456",
        instance_id="i-123456",
        keypair_name="kp-test",
        private_ip="10.0.0.10",
        n8n_url="http://example.com",
        cost=sample_cost,
        config=sample_config,
        rollback_history=[
            RollbackRecord(
                timestamp=datetime.now(UTC),
                trigger="manual",
                resources_deleted=[],
                success=True,
            ),
        ],
    )

    serialized = state.model_dump_json()
    restored = DeploymentState.model_validate_json(serialized)

    assert restored.stack_name == state.stack_name
    assert restored.status == state.status
    assert restored.config.tier == sample_config.tier
    assert len(restored.subnet_ids) == 2
    assert restored.cost.instance_type == "t3.medium"


def test_deployment_state_requires_subnet_ids(
    sample_config: DeploymentConfig,
    sample_cost: CostTracking,
) -> None:
    with pytest.raises(ValidationError):
        DeploymentState(
            stack_name=sample_config.stack_name,
            status="creating",
            vpc_id="vpc-123456",
            subnet_ids=[],
            security_group_id="sg-123456",
            efs_id="fs-123456",
            efs_mount_target_id="mt-123456",
            instance_id="i-123456",
            keypair_name="kp-test",
            private_ip="10.0.0.10",
            n8n_url="http://example.com",
            cost=sample_cost,
            config=sample_config,
        )


def test_cost_tracking_runtime_defaults(sample_cost: CostTracking) -> None:
    assert sample_cost.total_runtime_hours == 0.0
    assert sample_cost.estimated_cost_to_date == Decimal("0.0")
    assert sample_cost.instance_start_time is None


def test_deployment_snapshot_from_state(
    sample_config: DeploymentConfig,
    sample_cost: CostTracking,
) -> None:
    state = _build_state(sample_config, sample_cost, container_images={"n8n": "n8nio/n8n:1.0"})

    snapshot = DeploymentSnapshot.from_state(state)

    assert snapshot.config == state.config
    assert snapshot.container_images == {"n8n": "n8nio/n8n:1.0"}
    # Non-recursive: a snapshot must never contain nested history fields.
    assert not hasattr(snapshot, "previous_states")
    assert snapshot.status == "running"
    assert snapshot.created_at == state.updated_at
    # Mutating the state afterwards must not alter the captured snapshot.
    state.container_images["ollama"] = "ollama:latest"
    assert snapshot.container_images == {"n8n": "n8nio/n8n:1.0"}


def test_deployment_state_snapshot_json_round_trip(
    sample_config: DeploymentConfig,
    sample_cost: CostTracking,
) -> None:
    state = _build_state(sample_config, sample_cost, container_images={"n8n": "n8nio/n8n:1.0"})
    snapshot = DeploymentSnapshot.from_state(state)
    state.last_healthy_state = snapshot
    state.previous_states = [snapshot]

    restored = DeploymentState.model_validate_json(state.model_dump_json())

    assert isinstance(restored.previous_states[0], DeploymentSnapshot)
    assert restored.previous_states == state.previous_states
    assert restored.last_healthy_state == state.last_healthy_state
    assert restored.previous_states[0].config == sample_config
    assert restored.previous_states[0].container_images == {"n8n": "n8nio/n8n:1.0"}


def test_deployment_state_loads_legacy_full_dump_snapshots(
    sample_config: DeploymentConfig,
    sample_cost: CostTracking,
) -> None:
    """Legacy state files stored full DeploymentState dumps as snapshots.

    Loading such a file into the typed snapshot fields must not raise; ``extra="ignore"``
    drops the surplus keys while recovering ``config`` and ``container_images``.
    """
    legacy_config = sample_config.model_copy(update={"instance_type": "t3.small"})
    state = _build_state(sample_config, sample_cost, container_images={"n8n": "n8nio/n8n:new"})

    # A legacy snapshot is a FULL DeploymentState dump with many extra keys, including a
    # nested previous_states list (the historical bloat this refactor removes).
    legacy_snapshot = _build_state(
        legacy_config,
        sample_cost,
        container_images={"n8n": "n8nio/n8n:old"},
    ).model_dump(mode="json")
    legacy_snapshot["previous_states"] = [{"config": legacy_config.model_dump(mode="json")}]
    assert "public_ip" in legacy_snapshot and "n8n_url" in legacy_snapshot and "cost" in legacy_snapshot

    legacy_dict = state.model_dump(mode="json")
    legacy_dict["previous_states"] = [legacy_snapshot]
    legacy_dict["last_healthy_state"] = legacy_snapshot

    restored = DeploymentState.model_validate(legacy_dict)

    assert isinstance(restored.previous_states[0], DeploymentSnapshot)
    assert restored.previous_states[0].config.instance_type == "t3.small"
    assert restored.previous_states[0].container_images == {"n8n": "n8nio/n8n:old"}
    assert restored.last_healthy_state is not None
    assert restored.last_healthy_state.config.instance_type == "t3.small"
    # Surplus keys dropped, not retained.
    assert not hasattr(restored.previous_states[0], "public_ip")


def test_workload_and_topology_are_independent_with_legacy_defaults() -> None:
    legacy_gpu = DeploymentConfig(stack_name="legacy", tier="gpu")
    assert legacy_gpu.effective_workload == "gpu"
    assert legacy_gpu.topology == "global"

    cpu_global = DeploymentConfig(stack_name="cpu-global", tier="gpu", workload="cpu")
    gpu_dev = DeploymentConfig(stack_name="gpu-dev", tier="dev", workload="gpu")
    assert cpu_global.effective_workload == "cpu"
    assert gpu_dev.effective_workload == "gpu"
    assert gpu_dev.instance_preference == "balanced"
