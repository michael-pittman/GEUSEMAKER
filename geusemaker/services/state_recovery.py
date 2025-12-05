"""AWS resource state recovery service for lost state files."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from geusemaker.infra import AWSClientFactory
from geusemaker.models import CostTracking, DeploymentConfig, DeploymentState
from geusemaker.services.base import BaseService


class StateRecoveryService(BaseService):
    """Recover GeuseMaker deployment state from AWS resources when state files are missing."""

    def __init__(self, client_factory: AWSClientFactory, region: str = "us-east-1"):
        super().__init__(client_factory, region)
        self._ec2 = self._client("ec2")
        self._efs = self._client("efs")

    def discover_deployments(self) -> list[DeploymentState]:
        """Discover all GeuseMaker deployments by scanning AWS resources.

        Returns:
            List of discovered deployment states

        """

        def _call() -> list[DeploymentState]:
            # Find all EC2 instances with Stack tag
            instances = self._ec2.describe_instances(
                Filters=[
                    {"Name": "tag-key", "Values": ["Stack"]},
                    {"Name": "instance-state-name", "Values": ["running", "stopped", "stopping", "pending"]},
                ]
            ).get("Reservations", [])

            deployments: list[DeploymentState] = []
            seen_stacks: set[str] = set()

            for reservation in instances:
                for instance in reservation.get("Instances", []):
                    stack_name = self._get_tag(instance, "Stack")
                    if not stack_name or stack_name in seen_stacks:
                        continue

                    seen_stacks.add(stack_name)
                    state = self._discover_from_instance(instance, stack_name)
                    if state:
                        deployments.append(state)

            return deployments

        return self._safe_call(_call)

    def discover_deployment(self, stack_name: str) -> DeploymentState | None:
        """Discover a specific deployment by stack name.

        Args:
            stack_name: Name of the stack to discover

        Returns:
            Discovered deployment state or None if not found

        """

        def _call() -> DeploymentState | None:
            # Find EC2 instance with matching Stack tag
            instances = self._ec2.describe_instances(
                Filters=[
                    {"Name": "tag:Stack", "Values": [stack_name]},
                    {"Name": "instance-state-name", "Values": ["running", "stopped", "stopping", "pending"]},
                ]
            ).get("Reservations", [])

            if not instances or not instances[0].get("Instances"):
                return None

            instance = instances[0]["Instances"][0]
            return self._discover_from_instance(instance, stack_name)

        return self._safe_call(_call)

    def _discover_from_instance(self, instance: dict[str, Any], stack_name: str) -> DeploymentState | None:
        """Reconstruct deployment state from EC2 instance and related resources."""
        instance_id = instance.get("InstanceId", "")
        instance_type = instance.get("InstanceType", "")
        public_ip = instance.get("PublicIpAddress")
        private_ip = instance.get("PrivateIpAddress", "")

        # Extract VPC and subnet info
        vpc_id = instance.get("VpcId", "")
        subnet_id = instance.get("SubnetId", "")

        # Extract security group
        sg_ids = [sg.get("GroupId", "") for sg in instance.get("SecurityGroups", [])]
        security_group_id = sg_ids[0] if sg_ids else ""

        # Extract tier from tags (default to "dev" if not found)
        tier = self._get_tag(instance, "Tier") or "dev"

        # Discover EFS mount from instance
        efs_id, efs_mount_target_id = self._discover_efs_from_instance(instance_id, vpc_id)

        # Get all subnet IDs in the VPC
        subnets = self._ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]).get("Subnets", [])
        subnet_ids = [s["SubnetId"] for s in subnets]

        # Build minimal config
        config = DeploymentConfig(
            stack_name=stack_name,
            tier=tier,  # type: ignore[arg-type]
            region=self.region,
            instance_type=instance_type,
            vpc_id=vpc_id,
            subnet_id=subnet_id,
            security_group_id=security_group_id,
        )

        # Build cost tracking (placeholder values)
        cost = CostTracking(
            instance_type=instance_type,
            is_spot=False,  # Can't easily determine from instance metadata
            on_demand_price_per_hour=Decimal("0.00"),
            estimated_monthly_cost=Decimal("0.00"),
        )

        # Determine resource provenance (assume everything was discovered/reused)
        resource_provenance = {
            "vpc": "discovered",
            "subnets": "discovered",
            "security_group": "discovered",
            "efs": "discovered" if efs_id else "none",
            "efs_mount_target": "discovered" if efs_mount_target_id else "none",
            "instance": "discovered",
            "key_pair": "discovered",
        }

        # Build deployment state
        state = DeploymentState(
            stack_name=stack_name,
            status="discovered",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            vpc_id=vpc_id,
            subnet_ids=subnet_ids,
            storage_subnet_id=subnet_id,
            security_group_id=security_group_id,
            efs_id=efs_id or "",
            efs_mount_target_id=efs_mount_target_id or "",
            instance_id=instance_id,
            keypair_name=instance.get("KeyName", ""),
            public_ip=public_ip,
            private_ip=private_ip,
            n8n_url=f"http://{public_ip or private_ip}:5678" if (public_ip or private_ip) else "",
            cost=cost,
            config=config,
            resource_provenance=resource_provenance,
        )

        return state

    def _discover_efs_from_instance(self, instance_id: str, vpc_id: str) -> tuple[str, str]:
        """Discover EFS filesystem and mount target associated with instance.

        Args:
            instance_id: EC2 instance ID
            vpc_id: VPC ID where instance is running

        Returns:
            Tuple of (efs_id, mount_target_id) or ("", "") if not found

        """
        try:
            # List all EFS filesystems
            filesystems = self._efs.describe_file_systems().get("FileSystems", [])

            # For each filesystem, check if it has a mount target in the same VPC
            for fs in filesystems:
                fs_id = fs.get("FileSystemId", "")
                mount_targets = self._efs.describe_mount_targets(FileSystemId=fs_id).get("MountTargets", [])

                for mt in mount_targets:
                    # Check if mount target is in the same VPC
                    mt_subnet = mt.get("SubnetId", "")
                    subnet_info = self._ec2.describe_subnets(SubnetIds=[mt_subnet]).get("Subnets", [])

                    if subnet_info and subnet_info[0].get("VpcId") == vpc_id:
                        # Found a mount target in the same VPC
                        return fs_id, mt.get("MountTargetId", "")

        except Exception:  # noqa: BLE001, S110
            # If EFS discovery fails, return empty strings (acceptable fallback for discovery)
            pass

        return "", ""

    @staticmethod
    def _get_tag(resource: dict[str, Any], key: str) -> str | None:
        """Extract tag value from AWS resource."""
        tags = resource.get("Tags", [])
        for tag in tags:
            if tag.get("Key") == key:
                return tag.get("Value")
        return None


__all__ = ["StateRecoveryService"]
