"""Tests for production Spot Auto Scaling automation."""

from __future__ import annotations

import io
import zipfile
from unittest.mock import MagicMock

from geusemaker.services.spot_automation import SpotAutomationService


def test_create_uses_low_footprint_capacity_rebalancing() -> None:
    """The group normally runs one Spot instance and permits one replacement overlap."""
    service = SpotAutomationService.__new__(SpotAutomationService)
    service.region = "us-east-1"
    service._ec2 = MagicMock()
    service._autoscaling = MagicMock()
    service._events = MagicMock()
    service._logs = MagicMock()
    service._dynamodb = MagicMock()
    service._iam = MagicMock()
    service._lambda = MagicMock()
    service._ec2.create_launch_template.return_value = {"LaunchTemplate": {"LaunchTemplateId": "lt-1"}}
    service._autoscaling.describe_auto_scaling_groups.return_value = {
        "AutoScalingGroups": [
            {
                "Instances": [
                    {
                        "InstanceId": "i-1",
                        "LifecycleState": "InService",
                        "HealthStatus": "Healthy",
                    }
                ]
            }
        ]
    }
    service._logs.describe_log_groups.return_value = {
        "logGroups": [{"arn": "arn:aws:logs:us-east-1:123456789012:log-group:/geusemaker/stack/spot-events:*"}]
    }
    service._iam.create_role.return_value = {"Role": {"Arn": "arn:aws:iam::123456789012:role/stack-spot-coordinator"}}
    service._lambda.create_function.return_value = {
        "FunctionArn": "arn:aws:lambda:us-east-1:123456789012:function:stack-spot-coordinator"
    }
    service._events.describe_rule.side_effect = lambda Name: {
        "Arn": f"arn:aws:events:us-east-1:123456789012:rule/{Name}"
    }

    resources = service.create(
        stack_name="stack",
        image_id="ami-1",
        instance_type="t3.medium",
        subnet_ids=["subnet-a", "subnet-b"],
        security_group_ids=["sg-1"],
        instance_profile_name="profile",
        user_data=b"data",
        block_device_mappings=[],
        tags={"Stack": "stack"},
    )

    request = service._autoscaling.create_auto_scaling_group.call_args.kwargs
    assert request["MinSize"] == 1
    assert request["DesiredCapacity"] == 1
    assert request["MaxSize"] == 2
    assert request["CapacityRebalance"] is True
    assert request["MixedInstancesPolicy"]["InstancesDistribution"]["SpotAllocationStrategy"] == (
        "price-capacity-optimized"
    )
    assert resources.instance_id == "i-1"
    assert resources.lease_table_name == "stack-spot-lease"
    assert resources.lifecycle_hook_names == ("stack-launch", "stack-terminate")
    assert service._autoscaling.put_lifecycle_hook.call_count == 2
    service._dynamodb.update_time_to_live.assert_called_once_with(
        TableName="stack-spot-lease",
        TimeToLiveSpecification={"Enabled": True, "AttributeName": "ExpiresAt"},
    )
    assert service._events.put_targets.call_count == 2
    assert all(
        call.kwargs["Targets"][0]["Id"] == "spot-coordinator" for call in service._events.put_targets.call_args_list
    )
    table_request = service._dynamodb.create_table.call_args.kwargs
    assert table_request["KeySchema"] == [{"AttributeName": "StackName", "KeyType": "HASH"}]
    lifecycle_pattern = service._events.put_rule.call_args_list[1].kwargs["EventPattern"]
    assert "EC2 Instance-launch Lifecycle Action" in lifecycle_pattern
    assert "EC2 Instance-terminate Lifecycle Action" in lifecycle_pattern


def test_coordinator_scopes_events_and_signals_runtime_guard() -> None:
    """The coordinator validates tags and lets the on-node guard complete hooks."""
    package = SpotAutomationService._coordinator_zip()
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        source = archive.read("index.py").decode()

    assert 'tags.get("ManagedBy")!="GeuseMaker"' in source
    assert "systemctl start geusemaker-spot-drain.service" in source
    assert "complete_lifecycle_action" not in source
    assert 'os.environ["LOG_GROUP"]' in source


def test_attach_target_group_enables_elb_health_replacement() -> None:
    """ASG-managed replacements are automatically registered and health checked."""
    service = SpotAutomationService.__new__(SpotAutomationService)
    service._autoscaling = MagicMock()

    service.attach_target_group("stack-asg", "tg-arn")

    service._autoscaling.attach_load_balancer_target_groups.assert_called_once_with(
        AutoScalingGroupName="stack-asg", TargetGroupARNs=["tg-arn"]
    )
    service._autoscaling.update_auto_scaling_group.assert_called_once_with(
        AutoScalingGroupName="stack-asg", HealthCheckType="ELB", HealthCheckGracePeriod=600
    )


def test_verify_requires_active_lease_hooks_and_event_targets() -> None:
    service = SpotAutomationService.__new__(SpotAutomationService)
    service._autoscaling = MagicMock()
    service._dynamodb = MagicMock()
    service._events = MagicMock()
    service._autoscaling.describe_auto_scaling_groups.return_value = {
        "AutoScalingGroups": [{
            "CapacityRebalance": True,
            "DesiredCapacity": 1,
            "Tags": [{"Key": "Stack", "Value": "stack"}],
            "Instances": [{
                "InstanceId": "i-1", "LifecycleState": "InService", "HealthStatus": "Healthy"
            }],
        }]
    }
    service._dynamodb.get_item.return_value = {"Item": {"Owner": {"S": "i-1"}}}
    service._autoscaling.describe_lifecycle_hooks.return_value = {
        "LifecycleHooks": [
            {"LifecycleHookName": "stack-launch"},
            {"LifecycleHookName": "stack-terminate"},
        ]
    }
    service._events.list_targets_by_rule.return_value = {"Targets": [{"Id": "spot-coordinator"}]}

    service.verify(
        asg_name="stack-asg",
        instance_id="i-1",
        lease_table_name="stack-spot-lease",
        lifecycle_hook_names=["stack-launch", "stack-terminate"],
        event_rule_names=["stack-events"],
    )
