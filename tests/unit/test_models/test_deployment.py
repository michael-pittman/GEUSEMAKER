from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from geusemaker.models import (
    CostTracking,
    DeploymentConfig,
    DeploymentState,
    RollbackRecord,
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
