"""Tests for production Spot Auto Scaling automation."""

from __future__ import annotations

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
    service._ec2.create_launch_template.return_value = {
        "LaunchTemplate": {"LaunchTemplateId": "lt-1"}
    }
    service._autoscaling.describe_auto_scaling_groups.return_value = {
        "AutoScalingGroups": [{
            "Instances": [{
                "InstanceId": "i-1",
                "LifecycleState": "InService",
                "HealthStatus": "Healthy",
            }]
        }]
    }
    service._logs.describe_log_groups.return_value = {
        "logGroups": [{"arn": "arn:aws:logs:us-east-1:123456789012:log-group:/geusemaker/stack/spot-events:*"}]
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
