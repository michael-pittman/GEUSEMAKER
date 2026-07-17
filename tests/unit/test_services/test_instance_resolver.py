"""Tests for active deployment instance resolution."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from geusemaker.models import CostTracking, DeploymentConfig, DeploymentState
from geusemaker.services.instance_resolver import InstanceResolver


@pytest.fixture()
def deployment_state(sample_config: DeploymentConfig, sample_cost: CostTracking) -> DeploymentState:
    """Return a minimal running deployment."""
    return DeploymentState(
        stack_name="sample-stack",
        created_at=datetime.now(UTC),
        status="running",
        vpc_id="vpc-1",
        subnet_ids=["subnet-1"],
        security_group_id="sg-1",
        efs_id="fs-1",
        efs_mount_target_id="fsmt-1",
        instance_id="i-old",
        keypair_name="key",
        public_ip="198.51.100.2",
        private_ip="10.0.1.2",
        n8n_url="https://example.test",
        cost=sample_cost,
        config=sample_config,
    )


def test_legacy_deployment_uses_persisted_instance(deployment_state: DeploymentState) -> None:
    factory = MagicMock()
    resolved = InstanceResolver(factory).resolve(deployment_state)

    assert resolved.instance_id == deployment_state.instance_id
    factory.get_client.assert_not_called()


def test_asg_deployment_resolves_and_refreshes_current_instance(deployment_state: DeploymentState) -> None:
    deployment_state.auto_scaling_group_name = "gm-production"
    autoscaling = MagicMock()
    autoscaling.describe_auto_scaling_groups.return_value = {
        "AutoScalingGroups": [{"Instances": [
            {"InstanceId": "i-pending", "LifecycleState": "Pending", "HealthStatus": "Healthy"},
            {"InstanceId": "i-new", "LifecycleState": "InService", "HealthStatus": "Healthy"},
        ]}]
    }
    ec2 = MagicMock()
    ec2.describe_instances.return_value = {"Reservations": [{"Instances": [{
        "InstanceId": "i-new",
        "PublicIpAddress": "203.0.113.9",
        "PrivateIpAddress": "10.0.2.8",
    }]}]}

    resolved = InstanceResolver(MagicMock(), autoscaling_client=autoscaling, ec2_client=ec2).resolve(deployment_state)

    assert resolved.instance_id == "i-new"
    assert deployment_state.instance_id == "i-new"
    assert deployment_state.public_ip == "203.0.113.9"
    assert deployment_state.private_ip == "10.0.2.8"


def test_asg_deployment_rejects_absence_of_healthy_instance(deployment_state: DeploymentState) -> None:
    deployment_state.auto_scaling_group_name = "gm-production"
    autoscaling = MagicMock()
    autoscaling.describe_auto_scaling_groups.return_value = {
        "AutoScalingGroups": [{"Instances": [
            {"InstanceId": "i-old", "LifecycleState": "Terminating", "HealthStatus": "Healthy"}
        ]}]
    }

    with pytest.raises(RuntimeError, match="no healthy InService instance"):
        InstanceResolver(MagicMock(), autoscaling_client=autoscaling).resolve(deployment_state)


def test_fenced_deployment_resolves_lease_owner_during_rebalance(deployment_state: DeploymentState) -> None:
    """Commands follow the single writer rather than the stale persisted member."""
    deployment_state.auto_scaling_group_name = "gm-production"
    deployment_state.spot_lease_table_name = "gm-lease"
    autoscaling = MagicMock()
    autoscaling.describe_auto_scaling_groups.return_value = {
        "AutoScalingGroups": [{"Instances": [
            {"InstanceId": "i-old", "LifecycleState": "InService", "HealthStatus": "Healthy"},
            {"InstanceId": "i-new", "LifecycleState": "InService", "HealthStatus": "Healthy"},
        ]}]
    }
    dynamodb = MagicMock()
    dynamodb.get_item.return_value = {"Item": {"Owner": {"S": "i-new"}}}
    ec2 = MagicMock()
    ec2.describe_instances.return_value = {
        "Reservations": [{"Instances": [{"InstanceId": "i-new", "PrivateIpAddress": "10.0.2.8"}]}]
    }

    resolved = InstanceResolver(
        MagicMock(),
        autoscaling_client=autoscaling,
        ec2_client=ec2,
        dynamodb_client=dynamodb,
    ).resolve(deployment_state)

    assert resolved.instance_id == "i-new"
    dynamodb.get_item.assert_called_once_with(
        TableName="gm-lease",
        Key={"StackName": {"S": "sample-stack"}},
        ConsistentRead=True,
    )


def test_fenced_deployment_fails_when_no_healthy_member_holds_lease(deployment_state: DeploymentState) -> None:
    deployment_state.auto_scaling_group_name = "gm-production"
    deployment_state.spot_lease_table_name = "gm-lease"
    autoscaling = MagicMock()
    autoscaling.describe_auto_scaling_groups.return_value = {
        "AutoScalingGroups": [{"Instances": [
            {"InstanceId": "i-old", "LifecycleState": "InService", "HealthStatus": "Healthy"}
        ]}]
    }
    dynamodb = MagicMock()
    dynamodb.get_item.return_value = {}

    with pytest.raises(RuntimeError, match="active-node lease"):
        InstanceResolver(
            MagicMock(), autoscaling_client=autoscaling, dynamodb_client=dynamodb
        ).resolve(deployment_state)
