"""Tier 1 deployment orchestrator."""

from __future__ import annotations

import asyncio
import gzip
import secrets
import string
from datetime import UTC, datetime
from decimal import Decimal

from geusemaker.infra import AWSClientFactory, StateManager
from geusemaker.models import CostTracking, DeploymentConfig, DeploymentState
from geusemaker.models.userdata import UserDataConfig
from geusemaker.orchestration.errors import OrchestrationError
from geusemaker.services.ec2 import EC2Service
from geusemaker.services.efs import EFSService
from geusemaker.services.sg import SecurityGroupService
from geusemaker.services.userdata import UserDataGenerator
from geusemaker.services.vpc import VPCService


class Tier1Orchestrator:
    """Coordinate VPC/EFS/SG/EC2 provisioning for dev tier deployments (minimal happy path)."""

    def __init__(
        self,
        client_factory: AWSClientFactory | None = None,
        region: str = "us-east-1",
        state_manager: StateManager | None = None,
    ):
        self.client_factory = client_factory or AWSClientFactory()
        self.region = region
        self.state_manager = state_manager or StateManager()
        self.vpc_service = VPCService(self.client_factory, region=region)
        self.efs_service = EFSService(self.client_factory, region=region)
        self.sg_service = SecurityGroupService(self.client_factory, region=region)
        self.ec2_service = EC2Service(self.client_factory, region=region)
        self.userdata_generator = UserDataGenerator()

    def _generate_postgres_password(self, length: int = 32) -> str:
        """Generate a secure random password for PostgreSQL."""
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        return "".join(secrets.choice(alphabet) for _ in range(length))

    def deploy(self, config: DeploymentConfig) -> DeploymentState:
        """Deploy minimal Tier1 stack: VPC + SG + EFS + EC2."""
        if config.tier != "dev":
            raise OrchestrationError("Only dev tier is supported in the stub orchestrator.")

        # Create or configure VPC and subnets
        if config.vpc_id:
            vpc = self.vpc_service.configure_existing_vpc(
                config.vpc_id,
                name=config.stack_name,
                deployment=config.stack_name,
                tier=config.tier,
                attach_internet_gateway=config.attach_internet_gateway,
            )
        else:
            vpc = self.vpc_service.create_vpc_with_subnets(
                "10.0.0.0/16",
                config.stack_name,
                deployment=config.stack_name,
                tier=config.tier,
            )
        public_subnet_ids = config.public_subnet_ids or [subnet.subnet_id for subnet in vpc.public_subnets]
        private_subnet_ids = config.private_subnet_ids or [subnet.subnet_id for subnet in vpc.private_subnets]

        if not public_subnet_ids:
            raise OrchestrationError(f"No public subnets available in VPC {vpc.vpc_id}")

        if config.subnet_id:
            if config.subnet_id not in public_subnet_ids:
                raise OrchestrationError(
                    f"Configured subnet {config.subnet_id} is not a public subnet in VPC {vpc.vpc_id}",
                )
            chosen_public_subnet_id = config.subnet_id
        else:
            chosen_public_subnet_id = public_subnet_ids[0]

        # CRITICAL: EFS mount targets must be in the same subnet (or at least same AZ) as EC2 instance
        # to enable DNS resolution and NFS connectivity. Use storage_subnet_id if explicitly provided,
        # otherwise always use the same subnet where EC2 will launch.
        if config.storage_subnet_id:
            chosen_storage_subnet_id = config.storage_subnet_id
            if chosen_storage_subnet_id not in (public_subnet_ids + private_subnet_ids):
                raise OrchestrationError(
                    f"Configured storage subnet {chosen_storage_subnet_id} is not part of VPC {vpc.vpc_id}",
                )
        else:
            # Default: use the same subnet as EC2 instance to guarantee same-AZ placement
            chosen_storage_subnet_id = chosen_public_subnet_id

        # Use existing SG when provided; otherwise create a minimal one.
        if config.security_group_id:
            sg_id = config.security_group_id
            sg_provenance = "reused"
        else:
            ingress = [
                {"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
                {"IpProtocol": "tcp", "FromPort": 80, "ToPort": 80, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
                {"IpProtocol": "tcp", "FromPort": 5678, "ToPort": 5678, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
                {"IpProtocol": "tcp", "FromPort": 2049, "ToPort": 2049, "IpRanges": [{"CidrIp": vpc.cidr_block}]},
            ]
            sg_resp = self.sg_service.create_security_group(
                name=f"{config.stack_name}-sg",
                description="GeuseMaker dev SG",
                vpc_id=vpc.vpc_id,
                ingress_rules=ingress,
            )
            sg_id = sg_resp["group_id"]
            sg_provenance = "created"

        # Create EFS and mount target in first public subnet
        efs = self.efs_service.create_filesystem(tags=[{"Key": "Name", "Value": config.stack_name}])
        efs_id = efs["FileSystemId"]

        # Wait for EFS to transition from "creating" to "available" state
        # This is required before creating mount targets
        self.efs_service.wait_for_available(efs_id)

        # Create mount target in the same subnet as EC2 instance (or storage subnet if specified)
        mt_id = self.efs_service.create_mount_target(
            fs_id=efs_id,
            subnet_id=chosen_storage_subnet_id,
            security_groups=[sg_id],
        )

        # Wait for mount target to transition from "creating" to "available" state
        # This is required before EC2 instances can successfully mount the filesystem via DNS
        self.efs_service.wait_for_mount_target_available(mt_id)

        # Save partial state after EFS creation to prevent orphaned resources if deployment fails
        # This allows cleanup/rollback to find and delete the EFS if instance launch fails
        partial_state = DeploymentState(
            stack_name=config.stack_name,
            status="creating",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            vpc_id=vpc.vpc_id,
            subnet_ids=public_subnet_ids + private_subnet_ids,
            storage_subnet_id=chosen_storage_subnet_id,
            security_group_id=sg_id,
            efs_id=efs_id,
            efs_mount_target_id=mt_id,
            instance_id="",  # Not created yet
            keypair_name=config.keypair_name or "",
            public_ip=None,
            private_ip="",
            n8n_url="",
            cost=CostTracking(
                instance_type=config.instance_type,
                is_spot=config.use_spot,
                on_demand_price_per_hour=Decimal("0.00"),
                estimated_monthly_cost=Decimal("0.00"),
            ),
            config=config,
            resource_provenance={
                "vpc": "created" if vpc.created_by_geusemaker else "reused",
                "subnets": "created" if vpc.created_by_geusemaker else "reused",
                "security_group": sg_provenance,
                "efs": "created",
                "efs_mount_target": "created",
                "instance": "pending",
                "key_pair": "reused" if config.keypair_name else "created",
            },
        )
        asyncio.run(self.state_manager.save_deployment(partial_state))

        # Generate UserData script for EC2 instance initialization
        postgres_password = self._generate_postgres_password()
        efs_dns = f"{efs_id}.efs.{self.region}.amazonaws.com"

        userdata_config = UserDataConfig(
            efs_id=efs_id,
            efs_dns=efs_dns,
            tier=config.tier,
            stack_name=config.stack_name,
            region=self.region,
            postgres_password=postgres_password,
        )
        userdata_script = self.userdata_generator.generate(userdata_config)
        userdata_payload = self._compress_userdata(userdata_script)

        # Launch EC2 in first public subnet with UserData
        ami_id = self.ec2_service.get_latest_dlami(
            os_type=config.os_type,
            architecture=config.architecture,
            ami_type=config.ami_type,
            instance_type=config.instance_type,
        )
        ec2_resp = self.ec2_service.launch_instance(
            ImageId=ami_id,
            InstanceType=config.instance_type,
            SubnetId=chosen_public_subnet_id,
            SecurityGroupIds=[sg_id],
            UserData=userdata_payload,
            TagSpecifications=[
                {
                    "ResourceType": "instance",
                    "Tags": [
                        {"Key": "Name", "Value": config.stack_name},
                        {"Key": "Stack", "Value": config.stack_name},
                        {"Key": "Tier", "Value": config.tier},
                    ],
                },
                {
                    "ResourceType": "network-interface",
                    "Tags": [
                        {"Key": "Name", "Value": f"{config.stack_name}-eni"},
                        {"Key": "Stack", "Value": config.stack_name},
                        {"Key": "Tier", "Value": config.tier},
                    ],
                },
            ],
        )
        instance_id = ec2_resp["Instances"][0]["InstanceId"]
        self.ec2_service.wait_for_running(instance_id)
        instance_desc = self.ec2_service.describe_instance(instance_id)
        public_ip = instance_desc.get("PublicIpAddress")
        private_ip = instance_desc.get("PrivateIpAddress", "")

        # Assemble state (placeholder values for IPs/URLs)
        cost = CostTracking(
            instance_type=config.instance_type,
            is_spot=config.use_spot,
            on_demand_price_per_hour=Decimal("0.00"),
            estimated_monthly_cost=Decimal("0.00"),
        )
        resource_provenance = {
            "vpc": "created" if vpc.created_by_geusemaker else "reused",
            "subnets": "created" if vpc.created_by_geusemaker else "reused",
            "security_group": sg_provenance,
            "efs": "created",
            "efs_mount_target": "created",
            "instance": "created",
            "key_pair": "reused" if config.keypair_name else "created",
        }
        state = DeploymentState(
            stack_name=config.stack_name,
            status="creating",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            vpc_id=vpc.vpc_id,
            subnet_ids=public_subnet_ids + private_subnet_ids,
            storage_subnet_id=chosen_storage_subnet_id,
            security_group_id=sg_id,
            efs_id=efs_id,
            efs_mount_target_id=mt_id,
            instance_id=instance_id,
            keypair_name=config.keypair_name or "",
            public_ip=public_ip,
            private_ip=private_ip,
            n8n_url=f"http://{public_ip or private_ip}:5678" if (public_ip or private_ip) else "",
            cost=cost,
            config=config,
            resource_provenance=resource_provenance,
        )
        # Save final state
        asyncio.run(self.state_manager.save_deployment(state))
        return state

    @staticmethod
    def _compress_userdata(userdata_script: str) -> bytes:
        """Gzip-compress UserData to stay within AWS 16KB limit (SDK base64-encodes for us)."""
        compressed = gzip.compress(userdata_script.encode("utf-8"))
        limit_bytes = 16_384
        if len(compressed) > limit_bytes:
            raise OrchestrationError(
                f"Compressed user data is {len(compressed)} bytes which exceeds the AWS limit of {limit_bytes} bytes.",
            )
        return compressed


__all__ = ["Tier1Orchestrator"]
