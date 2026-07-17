"""Production Spot instance automation backed by EC2 Auto Scaling."""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from typing import Any

from geusemaker.infra import AWSClientFactory
from geusemaker.services.base import BaseService


@dataclass(frozen=True)
class SpotAutomationResources:
    """AWS resources created for a production Spot worker."""

    launch_template_id: str
    auto_scaling_group_name: str
    instance_id: str
    log_group_name: str
    event_rule_names: tuple[str, ...]


class SpotAutomationService(BaseService):
    """Create and manage the low-footprint production Spot control plane."""

    def __init__(self, client_factory: AWSClientFactory, region: str = "us-east-1"):
        super().__init__(client_factory, region)
        self._ec2 = self._client("ec2")
        self._autoscaling = self._client("autoscaling")
        self._events = self._client("events")
        self._logs = self._client("logs")

    def create(
        self,
        *,
        stack_name: str,
        image_id: str,
        instance_type: str,
        subnet_ids: list[str],
        security_group_ids: list[str],
        instance_profile_name: str,
        user_data: bytes,
        block_device_mappings: list[dict[str, Any]],
        tags: dict[str, str],
        key_name: str | None = None,
        timeout_seconds: int = 600,
    ) -> SpotAutomationResources:
        """Create a desired-capacity-one Spot ASG and wait for its first instance."""
        template_name = f"{stack_name}-spot-lt"[:128]
        asg_name = f"{stack_name}-spot-asg"
        tag_list = [{"Key": key, "Value": value} for key, value in tags.items()]
        template_data: dict[str, Any] = {
            "ImageId": image_id,
            "InstanceType": instance_type,
            "SecurityGroupIds": security_group_ids,
            "IamInstanceProfile": {"Name": instance_profile_name},
            "UserData": base64.b64encode(user_data).decode("ascii"),
            "BlockDeviceMappings": block_device_mappings,
            "InstanceMarketOptions": {
                "MarketType": "spot",
                "SpotOptions": {"SpotInstanceType": "one-time", "InstanceInterruptionBehavior": "terminate"},
            },
            "TagSpecifications": [
                {"ResourceType": "instance", "Tags": tag_list},
                {"ResourceType": "network-interface", "Tags": tag_list},
            ],
        }
        if key_name:
            template_data["KeyName"] = key_name

        response = self._ec2.create_launch_template(
            LaunchTemplateName=template_name,
            VersionDescription="GeuseMaker production Spot automation",
            LaunchTemplateData=template_data,
            TagSpecifications=[{"ResourceType": "launch-template", "Tags": tag_list}],
        )
        launch_template_id = response["LaunchTemplate"]["LaunchTemplateId"]

        self._autoscaling.create_auto_scaling_group(
            AutoScalingGroupName=asg_name,
            MinSize=1,
            MaxSize=2,
            DesiredCapacity=1,
            DefaultInstanceWarmup=300,
            HealthCheckType="EC2",
            HealthCheckGracePeriod=600,
            VPCZoneIdentifier=",".join(subnet_ids),
            CapacityRebalance=True,
            MixedInstancesPolicy={
                "LaunchTemplate": {
                    "LaunchTemplateSpecification": {
                        "LaunchTemplateId": launch_template_id,
                        "Version": "$Latest",
                    },
                    "Overrides": [{"InstanceType": instance_type}],
                },
                "InstancesDistribution": {
                    "OnDemandBaseCapacity": 0,
                    "OnDemandPercentageAboveBaseCapacity": 0,
                    "SpotAllocationStrategy": "price-capacity-optimized",
                },
            },
            Tags=[
                {"Key": key, "Value": value, "PropagateAtLaunch": True, "ResourceType": "auto-scaling-group"}
                for key, value in tags.items()
            ],
        )
        log_group_name, rule_names = self._create_event_monitoring(stack_name, asg_name, tags)
        instance_id = self.wait_for_instance(asg_name, timeout_seconds=timeout_seconds)
        return SpotAutomationResources(
            launch_template_id=launch_template_id,
            auto_scaling_group_name=asg_name,
            instance_id=instance_id,
            log_group_name=log_group_name,
            event_rule_names=rule_names,
        )

    def wait_for_instance(self, asg_name: str, timeout_seconds: int = 600) -> str:
        """Wait for an ASG instance to enter InService."""
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            groups = self._autoscaling.describe_auto_scaling_groups(
                AutoScalingGroupNames=[asg_name]
            ).get("AutoScalingGroups", [])
            if groups:
                for instance in groups[0].get("Instances", []):
                    if instance.get("LifecycleState") == "InService" and instance.get("HealthStatus") == "Healthy":
                        return str(instance["InstanceId"])
            time.sleep(5)
        raise RuntimeError(f"Auto Scaling group {asg_name} did not produce a healthy instance in time")

    def attach_target_group(self, asg_name: str, target_group_arn: str) -> None:
        """Route current and replacement instances through the existing ALB target group."""
        self._autoscaling.attach_load_balancer_target_groups(
            AutoScalingGroupName=asg_name,
            TargetGroupARNs=[target_group_arn],
        )
        self._autoscaling.update_auto_scaling_group(
            AutoScalingGroupName=asg_name,
            HealthCheckType="ELB",
            HealthCheckGracePeriod=600,
        )

    def delete(self, *, asg_name: str | None, launch_template_id: str | None, rule_names: list[str], log_group_name: str | None) -> None:
        """Delete Spot automation resources in dependency order."""
        for rule_name in rule_names:
            targets = self._events.list_targets_by_rule(Rule=rule_name).get("Targets", [])
            if targets:
                self._events.remove_targets(Rule=rule_name, Ids=[target["Id"] for target in targets], Force=True)
            self._events.delete_rule(Name=rule_name, Force=True)
        if asg_name:
            self._autoscaling.delete_auto_scaling_group(AutoScalingGroupName=asg_name, ForceDelete=True)
            deadline = time.monotonic() + 300
            while time.monotonic() < deadline:
                groups = self._autoscaling.describe_auto_scaling_groups(
                    AutoScalingGroupNames=[asg_name]
                ).get("AutoScalingGroups", [])
                if not groups:
                    break
                time.sleep(5)
            else:
                raise RuntimeError(f"Auto Scaling group {asg_name} did not finish deleting in time")
        if launch_template_id:
            self._ec2.delete_launch_template(LaunchTemplateId=launch_template_id)
        if log_group_name:
            self._logs.delete_log_group(logGroupName=log_group_name)

    def _create_event_monitoring(
        self, stack_name: str, asg_name: str, tags: dict[str, str]
    ) -> tuple[str, tuple[str, ...]]:
        log_group_name = f"/geusemaker/{stack_name}/spot-events"
        self._logs.create_log_group(logGroupName=log_group_name, tags=tags)
        self._logs.put_retention_policy(logGroupName=log_group_name, retentionInDays=30)
        log_group_arn = self._logs.describe_log_groups(logGroupNamePrefix=log_group_name)["logGroups"][0][
            "arn"
        ].removesuffix(":*")

        account_id = log_group_arn.split(":")[4]
        policy_document = {
            "Version": "2012-10-17",
            "Statement": [{
                "Sid": "GeuseMakerSpotEvents",
                "Effect": "Allow",
                "Principal": {"Service": ["events.amazonaws.com", "delivery.logs.amazonaws.com"]},
                "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                "Resource": f"arn:aws:logs:{self.region}:{account_id}:log-group:/geusemaker/*/spot-events:*",
            }],
        }
        self._logs.put_resource_policy(
            policyName="geusemaker-eventbridge-spot-logs",
            policyDocument=json.dumps(policy_document),
        )

        patterns = {
            f"{stack_name[:44]}-spot-interruption": {
                "source": ["aws.ec2"],
                "detail-type": ["EC2 Spot Instance Interruption Warning", "EC2 Instance Rebalance Recommendation"],
            },
            f"{stack_name[:50]}-asg-lifecycle": {
                "source": ["aws.autoscaling"],
                "detail-type": [
                    "EC2 Instance Launch Successful",
                    "EC2 Instance Launch Unsuccessful",
                    "EC2 Instance Terminate Successful",
                    "EC2 Instance Terminate Unsuccessful",
                ],
                "detail": {"AutoScalingGroupName": [asg_name]},
            },
        }
        for rule_name, pattern in patterns.items():
            self._events.put_rule(Name=rule_name, EventPattern=json.dumps(pattern), State="ENABLED", Tags=[
                {"Key": key, "Value": value} for key, value in tags.items()
            ])
            self._events.put_targets(
                Rule=rule_name,
                Targets=[{"Id": "spot-event-log", "Arn": log_group_arn}],
            )
        return log_group_name, tuple(patterns)


__all__ = ["SpotAutomationResources", "SpotAutomationService"]
