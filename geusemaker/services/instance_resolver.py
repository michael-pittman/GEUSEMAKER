"""Resolve the currently active EC2 instance for a deployment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from geusemaker.infra import AWSClientFactory
from geusemaker.models import DeploymentState
from geusemaker.services.base import BaseService


@dataclass(frozen=True)
class ResolvedInstance:
    """Identity and network details for a deployment's active instance."""

    instance_id: str
    public_ip: str | None = None
    private_ip: str | None = None


class InstanceResolver(BaseService):
    """Resolve legacy instances directly and ASG instances dynamically."""

    def __init__(
        self,
        client_factory: AWSClientFactory,
        region: str = "us-east-1",
        autoscaling_client: Any | None = None,
        ec2_client: Any | None = None,
        dynamodb_client: Any | None = None,
    ):
        super().__init__(client_factory, region)
        self._autoscaling = autoscaling_client
        self._ec2 = ec2_client
        self._dynamodb = dynamodb_client

    @property
    def autoscaling(self) -> Any:
        """Create the Auto Scaling client only for ASG-backed deployments."""
        if self._autoscaling is None:
            self._autoscaling = self._client("autoscaling")
        return self._autoscaling

    @property
    def ec2(self) -> Any:
        """Create the EC2 client only when replacement metadata is needed."""
        if self._ec2 is None:
            self._ec2 = self._client("ec2")
        return self._ec2

    @property
    def dynamodb(self) -> Any:
        """Create the DynamoDB client only for fenced Spot deployments."""
        if self._dynamodb is None:
            self._dynamodb = self._client("dynamodb")
        return self._dynamodb

    def resolve(self, state: DeploymentState, *, refresh_state: bool = True) -> ResolvedInstance:
        """Return the current service instance, preserving legacy state behavior."""
        instance_id = state.instance_id
        if state.auto_scaling_group_name:
            response = self._safe_call(
                lambda: self.autoscaling.describe_auto_scaling_groups(
                    AutoScalingGroupNames=[state.auto_scaling_group_name]
                )
            )
            groups = response.get("AutoScalingGroups", [])
            if not groups:
                raise RuntimeError(f"Auto Scaling group {state.auto_scaling_group_name!r} was not found")
            candidates = [
                item
                for item in groups[0].get("Instances", [])
                if item.get("LifecycleState") == "InService"
                and item.get("HealthStatus", "Healthy") == "Healthy"
                and item.get("InstanceId")
            ]
            if not candidates:
                raise RuntimeError(
                    f"Auto Scaling group {state.auto_scaling_group_name!r} has no healthy InService instance"
                )
            selected = None
            if state.spot_lease_table_name:
                lease = self._safe_call(
                    lambda: self.dynamodb.get_item(
                        TableName=state.spot_lease_table_name,
                        Key={"StackName": {"S": state.stack_name}},
                        ConsistentRead=True,
                    )
                ).get("Item", {})
                lease_owner = lease.get("Owner", {}).get("S")
                selected = next(
                    (item for item in candidates if item.get("InstanceId") == lease_owner),
                    None,
                )
                if selected is None:
                    raise RuntimeError(
                        f"Deployment {state.stack_name!r} has no healthy instance holding its active-node lease"
                    )
            selected = selected or next(
                (item for item in candidates if item.get("InstanceId") == state.instance_id),
                candidates[0],
            )
            instance_id = str(selected["InstanceId"])

        if not instance_id:
            raise RuntimeError(f"Deployment {state.stack_name!r} has no active instance")

        public_ip: str | None = state.public_ip
        private_ip: str | None = state.private_ip
        if state.auto_scaling_group_name:
            response = self._safe_call(lambda: self.ec2.describe_instances(InstanceIds=[instance_id]))
            instances = [
                instance
                for reservation in response.get("Reservations", [])
                for instance in reservation.get("Instances", [])
            ]
            if not instances:
                raise RuntimeError(f"Active instance {instance_id!r} was not found")
            instance = instances[0]
            public_ip = instance.get("PublicIpAddress")
            private_ip = instance.get("PrivateIpAddress")

        resolved = ResolvedInstance(instance_id, public_ip, private_ip)
        if refresh_state:
            state.instance_id = resolved.instance_id
            state.public_ip = resolved.public_ip
            if resolved.private_ip:
                state.private_ip = resolved.private_ip
        return resolved


__all__ = ["InstanceResolver", "ResolvedInstance"]
