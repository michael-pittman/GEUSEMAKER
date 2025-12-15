"""Tier 1 deployment orchestrator."""

from __future__ import annotations

import asyncio
import gzip
import secrets
import string
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from geusemaker.cli import console
from geusemaker.cli.branding import EMOJI
from geusemaker.infra import AWSClientFactory, StateManager
from geusemaker.models import CostTracking, DeploymentConfig, DeploymentState, VPCInfo
from geusemaker.models.compute import InstanceSelection
from geusemaker.models.userdata import UserDataConfig
from geusemaker.orchestration.errors import OrchestrationError
from geusemaker.services.compute.spot import SpotSelectionService
from geusemaker.services.destruction import DestructionService
from geusemaker.services.ec2 import EC2Service
from geusemaker.services.efs import EFSService
from geusemaker.services.iam import IAMService
from geusemaker.services.pricing import PricingService
from geusemaker.services.sg import SecurityGroupService
from geusemaker.services.userdata import UserDataGenerator
from geusemaker.services.vpc import VPCService


class Tier1Orchestrator:
    """Coordinate VPC/EFS/SG/EC2 provisioning for dev tier deployments."""

    def __init__(
        self,
        client_factory: AWSClientFactory | None = None,
        region: str = "us-east-1",
        state_manager: StateManager | None = None,
        pricing_service: PricingService | None = None,
        spot_selector: SpotSelectionService | None = None,
    ):
        self.client_factory = client_factory or AWSClientFactory()
        self.region = region
        self.state_manager = state_manager or StateManager()
        self.pricing_service = pricing_service or PricingService(self.client_factory, region=region)
        self._preselected_selection = None
        self._deploy_start_time: float | None = None
        self.vpc_service = VPCService(self.client_factory, region=region)
        self.efs_service = EFSService(self.client_factory, region=region)
        self.sg_service = SecurityGroupService(self.client_factory, region=region)
        self.ec2_service = EC2Service(self.client_factory, region=region)
        self.iam_service = IAMService(self.client_factory, region=region)
        # Initialize spot selector with EC2 service for accurate AMI-based dry-run checks
        self.spot_selector = spot_selector or SpotSelectionService(
            self.client_factory,
            pricing_service=self.pricing_service,
            region=region,
            ec2_service=self.ec2_service,
        )
        self.userdata_generator = UserDataGenerator()

    def _generate_postgres_password(self, length: int = 32) -> str:
        """Generate a secure random password for PostgreSQL."""
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        return "".join(secrets.choice(alphabet) for _ in range(length))

    def _log_selection(self, selection: InstanceSelection) -> None:
        """Log compute selection details."""
        if selection.is_spot:
            console.print(
                f"{EMOJI['money']} Using spot in {selection.availability_zone or 'best AZ'} at "
                f"${selection.price_per_hour:.4f}/hr "
                f"(on-demand ${selection.savings_vs_on_demand.on_demand_hourly:.4f}/hr)",
                verbosity="info",
            )
        else:
            console.print(
                f"{EMOJI['info']} Using on-demand at ${selection.price_per_hour:.4f}/hr "
                f"(reason: {selection.fallback_reason or selection.selection_reason})",
                verbosity="info",
            )

    def _select_instance(self, config: DeploymentConfig) -> InstanceSelection:
        """Choose spot/on-demand placement, reusing any preselected choice."""
        selection = self._preselected_selection or self.spot_selector.select_instance_type(config)
        self._preselected_selection = selection
        self._log_selection(selection)
        return selection

    def _check_timeout(self, start_time: float, timeout_minutes: int, step: str) -> None:
        """Abort if deployment exceeds rollback timeout."""
        elapsed = time.monotonic() - start_time
        if elapsed > timeout_minutes * 60:
            raise OrchestrationError(f"Deployment exceeded rollback timeout ({timeout_minutes} minutes) during {step}.")

    def deploy(self, config: DeploymentConfig, enable_rollback: bool = True) -> DeploymentState:
        """
        Deploy Tier1 stack with automatic rollback on failure.

        Args:
            config: Deployment configuration
            enable_rollback: If True, automatically rollback on deployment failure (default: True)

        Returns:
            DeploymentState with all resource IDs and metadata

        Raises:
            OrchestrationError: If deployment validation or resource creation fails
        """
        try:
            self._deploy_start_time = time.monotonic()
            return self._deploy_impl(config)
        except Exception as exc:
            # Attempt to load partial state to check for created resources
            partial_state = asyncio.run(self.state_manager.load_deployment(config.stack_name))

            # If partial state exists and rollback is enabled, clean up resources
            if partial_state and enable_rollback:
                console.print(
                    f"\n{EMOJI['error']} Deployment failed: {exc}",
                    verbosity="error",
                )
                console.print(
                    f"{EMOJI['warning']} Initiating automatic cleanup of partial deployment...",
                    verbosity="warning",
                )
                try:
                    self._cleanup_partial_deployment(partial_state)
                    console.print(
                        f"{EMOJI['check']} Cleanup completed successfully. Partial resources have been cleaned up.",
                        verbosity="info",
                    )
                except Exception as rollback_exc:  # noqa: BLE001
                    console.print(
                        f"{EMOJI['error']} Rollback failed: {rollback_exc}",
                        verbosity="error",
                    )
                    console.print(
                        f"{EMOJI['warning']} Manual cleanup may be required. Check AWS Console for orphaned resources tagged with Stack: {config.stack_name}",
                        verbosity="warning",
                    )

            # If no rollback or rollback disabled, just save failed state
            elif partial_state:
                console.print(
                    f"\n{EMOJI['error']} Deployment failed: {exc}",
                    verbosity="error",
                )
                console.print(
                    f"{EMOJI['warning']} Rollback disabled. Saving failed state for manual recovery.",
                    verbosity="warning",
                )
                self._save_failed_state(partial_state, exc)

            # Re-raise original error with context
            raise OrchestrationError(
                f"Deployment failed: {exc}. "
                + ("Cleanup completed." if (partial_state and enable_rollback) else "No cleanup performed.")
            ) from exc

    def _cleanup_partial_deployment(self, partial_state: DeploymentState) -> None:
        """
        Clean up a partial deployment by deleting created resources.

        This is operational cleanup (resource destruction) and distinct from
        configuration/state rollback handled by RollbackService.

        Args:
            partial_state: Partial deployment state with created resources

        Raises:
            RuntimeError: If cleanup encounters errors
        """
        destruction_service = DestructionService(
            client_factory=self.client_factory,
            state_manager=self.state_manager,
            region=self.region,
        )

        def progress_callback(msg: str) -> None:
            console.print(f"  {msg}", verbosity="info")

        result = destruction_service.destroy(partial_state, dry_run=False, progress_callback=progress_callback)

        if result.errors:
            error_summary = "; ".join(result.errors)
            raise RuntimeError(f"Rollback encountered errors: {error_summary}")

        # Archive the failed deployment state after successful cleanup
        asyncio.run(self.state_manager.archive_deployment(partial_state.stack_name))

    def _save_failed_state(self, partial_state: DeploymentState, error: Exception) -> None:
        """
        Save failed deployment state with error details.

        Args:
            partial_state: Partial deployment state
            error: The exception that caused the failure
        """
        # Update state to reflect failure
        # Note: Error message is logged and displayed to user, not stored in state
        failed_state = DeploymentState(
            stack_name=partial_state.stack_name,
            status="failed",
            created_at=partial_state.created_at,
            updated_at=datetime.now(UTC),
            vpc_id=partial_state.vpc_id,
            subnet_ids=partial_state.subnet_ids,
            storage_subnet_id=partial_state.storage_subnet_id,
            security_group_id=partial_state.security_group_id,
            efs_id=partial_state.efs_id,
            efs_mount_target_id=partial_state.efs_mount_target_id,
            efs_mount_target_ip=partial_state.efs_mount_target_ip,
            iam_role_name=partial_state.iam_role_name,
            iam_role_arn=partial_state.iam_role_arn,
            iam_instance_profile_name=partial_state.iam_instance_profile_name,
            iam_instance_profile_arn=partial_state.iam_instance_profile_arn,
            instance_id=partial_state.instance_id or "",
            keypair_name=partial_state.keypair_name,
            public_ip=partial_state.public_ip,
            private_ip=partial_state.private_ip,
            n8n_url=partial_state.n8n_url,
            cost=partial_state.cost,
            config=partial_state.config,
            resource_provenance=partial_state.resource_provenance,
        )

        asyncio.run(self.state_manager.save_deployment(failed_state))

        console.print(
            f"{EMOJI['info']} Failed state saved. Use 'geusemaker destroy {partial_state.stack_name}' to clean up orphaned resources.",
            verbosity="info",
        )

    def _deploy_impl(self, config: DeploymentConfig) -> DeploymentState:
        """
        Internal implementation of Tier1 deployment.

        Args:
            config: Deployment configuration

        Returns:
            DeploymentState with all resource IDs and metadata

        Raises:
            OrchestrationError: If deployment validation or resource creation fails
        """
        if config.tier not in ("dev", "automation", "gpu"):
            raise OrchestrationError(
                f"Tier1Orchestrator supports 'dev', 'automation', and 'gpu' tiers, got: {config.tier}"
            )

        start_time = self._deploy_start_time or time.monotonic()
        selection = self._select_instance(config)

        # Step 1: Setup networking (VPC, subnets)
        vpc_info = self._setup_networking(config, selection)
        self._check_timeout(start_time, config.rollback_timeout_minutes, "networking")

        # Step 2: Create or reuse security group
        sg_id, sg_provenance = self._create_security_group(config, vpc_info)
        self._check_timeout(start_time, config.rollback_timeout_minutes, "security group creation")

        # Step 3: Create EFS filesystem and mount target
        efs_id, mt_id, mt_ip = self._create_storage(config, vpc_info, sg_id)
        self._check_timeout(start_time, config.rollback_timeout_minutes, "storage setup")

        # Step 4: Save partial state after EFS creation
        self._save_partial_state(config, vpc_info, sg_id, sg_provenance, efs_id, mt_id, mt_ip, selection)

        # Step 5: Create IAM role and instance profile for EFS mount
        iam_info = self._create_iam_resources(config)
        self._check_timeout(start_time, config.rollback_timeout_minutes, "IAM setup")

        # Step 6: Generate UserData script
        userdata_payload, postgres_password = self._generate_userdata(config, efs_id, mt_ip)
        self._check_timeout(start_time, config.rollback_timeout_minutes, "UserData generation")

        # Step 7: Launch EC2 instance with IAM instance profile
        instance_info = self._launch_instance(
            config,
            vpc_info,
            sg_id,
            userdata_payload,
            iam_info,
            selection,
        )
        self._check_timeout(start_time, config.rollback_timeout_minutes, "instance launch")

        # Step 8: Build and save final state
        final_state = self._build_final_state(
            config,
            vpc_info,
            sg_id,
            sg_provenance,
            efs_id,
            mt_id,
            mt_ip,
            iam_info,
            instance_info,
            selection,
        )
        asyncio.run(self.state_manager.save_deployment(final_state))

        return final_state

    def _setup_networking(self, config: DeploymentConfig, selection: InstanceSelection) -> dict[str, Any]:
        """
        Setup VPC and select subnets for deployment.

        Args:
            config: Deployment configuration
            selection: Instance selection to align AZ choice

        Returns:
            Dict containing VPC info and selected subnet IDs
        """
        # Create or configure VPC
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

        # Extract subnet IDs
        public_subnet_ids = config.public_subnet_ids or [subnet.subnet_id for subnet in vpc.public_subnets]
        private_subnet_ids = config.private_subnet_ids or [subnet.subnet_id for subnet in vpc.private_subnets]

        if not public_subnet_ids:
            raise OrchestrationError(f"No public subnets available in VPC {vpc.vpc_id}")

        subnet_lookup = {subnet.subnet_id: subnet for subnet in (vpc.public_subnets + vpc.private_subnets)}

        # Select public subnet for EC2 instance
        if config.subnet_id:
            if config.subnet_id not in public_subnet_ids:
                raise OrchestrationError(
                    f"Configured subnet {config.subnet_id} is not a public subnet in VPC {vpc.vpc_id}",
                )
            chosen_public_subnet_id = config.subnet_id
        else:
            chosen_public_subnet_id = public_subnet_ids[0]
            if selection.availability_zone:
                az_match = next(
                    (
                        subnet.subnet_id
                        for subnet in vpc.public_subnets
                        if subnet.availability_zone == selection.availability_zone
                    ),
                    None,
                )
                if az_match:
                    chosen_public_subnet_id = az_match
                    console.print(
                        f"{EMOJI['info']} Placing compute in {selection.availability_zone} to match spot pricing.",
                        verbosity="info",
                    )

        # Select storage subnet for EFS mount target
        # CRITICAL: EFS mount targets must be in same subnet/AZ as EC2 instance for DNS resolution
        if config.storage_subnet_id:
            chosen_storage_subnet_id = config.storage_subnet_id
            if chosen_storage_subnet_id not in (public_subnet_ids + private_subnet_ids):
                raise OrchestrationError(
                    f"Configured storage subnet {chosen_storage_subnet_id} is not part of VPC {vpc.vpc_id}",
                )
        else:
            # Default: use same subnet as EC2 instance to guarantee same-AZ placement
            chosen_storage_subnet_id = chosen_public_subnet_id

        chosen_public_subnet = subnet_lookup.get(chosen_public_subnet_id)
        return {
            "vpc": vpc,
            "public_subnet_ids": public_subnet_ids,
            "private_subnet_ids": private_subnet_ids,
            "chosen_public_subnet_id": chosen_public_subnet_id,
            "chosen_storage_subnet_id": chosen_storage_subnet_id,
            "chosen_public_subnet_az": chosen_public_subnet.availability_zone if chosen_public_subnet else None,
        }

    def _create_security_group(
        self,
        config: DeploymentConfig,
        vpc_info: dict[str, Any],
    ) -> tuple[str, str]:
        """
        Create or reuse security group.

        Args:
            config: Deployment configuration
            vpc_info: VPC information from _setup_networking()

        Returns:
            Tuple of (security_group_id, provenance)
        """
        if config.security_group_id:
            # When reusing a security group with HTTPS enabled, ensure port 443 is open
            if config.enable_https:
                port_added = self.sg_service.ensure_https_port(config.security_group_id)
                if port_added:
                    console.print("✓ HTTPS port 443 added to security group", style="green")
                else:
                    console.print("✓ Port 443 (HTTPS) already open", style="green")
            return config.security_group_id, "reused"

        vpc: VPCInfo = vpc_info["vpc"]
        ingress = [
            {"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
            {"IpProtocol": "tcp", "FromPort": 80, "ToPort": 80, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
            {"IpProtocol": "tcp", "FromPort": 5678, "ToPort": 5678, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
            {"IpProtocol": "tcp", "FromPort": 2049, "ToPort": 2049, "IpRanges": [{"CidrIp": vpc.cidr_block}]},
        ]
        # Add HTTPS port when HTTPS is enabled
        if config.enable_https:
            ingress.append(
                {"IpProtocol": "tcp", "FromPort": 443, "ToPort": 443, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
            )
        sg_resp = self.sg_service.create_security_group(
            name=f"{config.stack_name}-sg",
            description="GeuseMaker dev SG",
            vpc_id=vpc.vpc_id,
            ingress_rules=ingress,
        )
        return sg_resp["group_id"], "created"

    def _create_storage(
        self,
        config: DeploymentConfig,
        vpc_info: dict[str, Any],
        sg_id: str,
    ) -> tuple[str, str, str]:
        """
        Create EFS filesystem and mount target.

        Args:
            config: Deployment configuration
            vpc_info: VPC information from _setup_networking()
            sg_id: Security group ID

        Returns:
            Tuple of (efs_id, mount_target_id, mount_target_ip)
        """
        # Create EFS filesystem
        efs = self.efs_service.create_filesystem(tags=[{"Key": "Name", "Value": config.stack_name}])
        efs_id = efs["FileSystemId"]

        # Wait for EFS to transition from "creating" to "available" state
        self.efs_service.wait_for_available(efs_id)

        # Create mount target in the storage subnet
        chosen_storage_subnet_id = vpc_info["chosen_storage_subnet_id"]
        mt_id = self.efs_service.create_mount_target(
            fs_id=efs_id,
            subnet_id=chosen_storage_subnet_id,
            security_groups=[sg_id],
        )

        # Wait for mount target to become available
        self.efs_service.wait_for_mount_target_available(mt_id)
        mt_ip = self.efs_service.get_mount_target_ip(mt_id)

        return efs_id, mt_id, mt_ip

    def _save_partial_state(
        self,
        config: DeploymentConfig,
        vpc_info: dict[str, Any],
        sg_id: str,
        sg_provenance: str,
        efs_id: str,
        mt_id: str,
        mt_ip: str,
        selection: InstanceSelection,
    ) -> None:
        """
        Save partial state after EFS creation.

        This allows cleanup/rollback to find and delete the EFS if instance launch fails.

        Args:
            config: Deployment configuration
            vpc_info: VPC information
            sg_id: Security group ID
            sg_provenance: Security group provenance ("created" or "reused")
            efs_id: EFS filesystem ID
            mt_id: EFS mount target ID
            mt_ip: EFS mount target IP address
        """
        vpc: VPCInfo = vpc_info["vpc"]
        public_subnet_ids = vpc_info["public_subnet_ids"]
        private_subnet_ids = vpc_info["private_subnet_ids"]
        chosen_storage_subnet_id = vpc_info["chosen_storage_subnet_id"]

        hourly_price = selection.price_per_hour
        monthly_price = hourly_price * Decimal("730")

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
            efs_mount_target_ip=mt_ip,
            instance_id="",  # Not created yet
            keypair_name=config.keypair_name or "",
            public_ip=None,
            private_ip="",
            n8n_url="",
            cost=CostTracking(
                instance_type=config.instance_type,
                is_spot=selection.is_spot,
                spot_price_per_hour=hourly_price if selection.is_spot else None,
                on_demand_price_per_hour=selection.savings_vs_on_demand.on_demand_hourly,
                estimated_monthly_cost=monthly_price,
                budget_limit=config.budget_limit,
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

    def _create_iam_resources(self, config: DeploymentConfig) -> dict[str, str]:
        """
        Create IAM role and instance profile for EFS mount with IAM authentication.

        Args:
            config: Deployment configuration

        Returns:
            Dict containing role_name, role_arn, profile_name, profile_arn
        """
        role_name = f"{config.stack_name}-efs-mount-role"
        profile_name = f"{config.stack_name}-instance-profile"

        tags = [
            {"Key": "Name", "Value": role_name},
            {"Key": "Stack", "Value": config.stack_name},
            {"Key": "Tier", "Value": config.tier},
            {"Key": "ManagedBy", "Value": "GeuseMaker"},
        ]

        console.print(f"{EMOJI['info']} Creating IAM role for EFS mount: {role_name}", verbosity="info")
        role_arn = self.iam_service.create_efs_mount_role(role_name, tags)

        console.print(f"{EMOJI['info']} Creating IAM instance profile: {profile_name}", verbosity="info")
        profile_arn = self.iam_service.create_instance_profile(profile_name, tags)

        console.print(f"{EMOJI['info']} Attaching role to instance profile", verbosity="info")
        self.iam_service.attach_role_to_profile(profile_name, role_name)

        console.print(f"{EMOJI['info']} Waiting for instance profile with role attachment", verbosity="info")
        self.iam_service.wait_for_instance_profile(profile_name, role_name)

        return {
            "role_name": role_name,
            "role_arn": role_arn,
            "profile_name": profile_name,
            "profile_arn": profile_arn,
        }

    def _generate_userdata(self, config: DeploymentConfig, efs_id: str, mt_ip: str) -> tuple[bytes, str]:
        """
        Generate UserData script for EC2 instance initialization.

        Args:
            config: Deployment configuration
            efs_id: EFS filesystem ID
            mt_ip: EFS mount target IP address

        Returns:
            Tuple of (compressed_userdata, postgres_password)
        """
        postgres_password = self._generate_postgres_password()
        efs_dns = f"{efs_id}.efs.{self.region}.amazonaws.com"

        userdata_config = UserDataConfig(
            efs_id=efs_id,
            efs_dns=efs_dns,
            efs_mount_target_ip=mt_ip,
            tier=config.tier,
            stack_name=config.stack_name,
            region=self.region,
            postgres_password=postgres_password,
            use_runtime_bundle=config.use_runtime_bundle,
            runtime_bundle_path=config.runtime_bundle_path,
        )
        userdata_script = self.userdata_generator.generate(userdata_config)
        userdata_payload = self._compress_userdata(userdata_script)

        return userdata_payload, postgres_password

    def _launch_instance(
        self,
        config: DeploymentConfig,
        vpc_info: dict[str, Any],
        sg_id: str,
        userdata_payload: bytes,
        iam_info: dict[str, str],
        selection: InstanceSelection,
    ) -> dict[str, str]:
        """
        Launch EC2 instance with UserData and IAM instance profile.

        Args:
            config: Deployment configuration
            vpc_info: VPC information
            sg_id: Security group ID
            userdata_payload: Compressed UserData script
            iam_info: IAM role and instance profile information
            selection: Spot/on-demand selection metadata

        Returns:
            Dict containing instance_id, public_ip, private_ip
        """
        chosen_public_subnet_id = vpc_info["chosen_public_subnet_id"]
        chosen_public_subnet_az = vpc_info.get("chosen_public_subnet_az")

        # Get AMI ID (use custom if provided, otherwise auto-select)
        if config.ami_id:
            ami_id = config.ami_id
            console.print(f"{EMOJI['info']} Using custom AMI: {ami_id}", verbosity="info")
        else:
            ami_id = self.ec2_service.get_latest_dlami(
                os_type=config.os_type,
                architecture=config.architecture,
                ami_type=config.ami_type,
                instance_type=config.instance_type,
            )
            console.print(f"{EMOJI['info']} Auto-selected AMI: {ami_id}", verbosity="info")

        # Ensure root volume is at least the minimum size
        min_root_gb = 75
        try:
            root_device_name = self.ec2_service.get_root_device_name(ami_id)
        except Exception as exc:  # noqa: BLE001
            root_device_name = "/dev/xvda"
            console.print(
                f"{EMOJI['warning']} Could not determine AMI root device; defaulting to {root_device_name}. Details: {exc}",
                verbosity="warning",
            )

        block_device_mappings = [
            {
                "DeviceName": root_device_name,
                "Ebs": {
                    "VolumeSize": min_root_gb,
                    "VolumeType": "gp3",
                    "DeleteOnTermination": True,
                    "Encrypted": True,
                },
            },
        ]

        # Launch instance with IAM instance profile for EFS mount
        # Use Name (simpler and more reliable for newly created profiles in same region)
        # Retry logic handles IAM->EC2 propagation delay
        max_launch_attempts = 5
        launch_delay = 3
        ec2_resp = None

        for attempt in range(max_launch_attempts):
            try:
                launch_kwargs: dict[str, Any] = {
                    "ImageId": ami_id,
                    "InstanceType": config.instance_type,
                    "SubnetId": chosen_public_subnet_id,
                    "SecurityGroupIds": [sg_id],
                    "UserData": userdata_payload,
                    "BlockDeviceMappings": block_device_mappings,
                    "IamInstanceProfile": {"Name": iam_info["profile_name"]},
                    "TagSpecifications": [
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
                }
                if selection.is_spot:
                    launch_kwargs["InstanceMarketOptions"] = {
                        "MarketType": "spot",
                        "SpotOptions": {
                            "SpotInstanceType": "one-time",
                            "InstanceInterruptionBehavior": "terminate",
                        },
                    }
                if chosen_public_subnet_az:
                    launch_kwargs["Placement"] = {"AvailabilityZone": chosen_public_subnet_az}

                ec2_resp = self.ec2_service.launch_instance(**launch_kwargs)
                break  # Success - exit retry loop
            except RuntimeError as e:
                error_msg = str(e)
                # Check for IAM profile propagation errors
                if "InvalidParameterValue" in error_msg or "does not exist" in error_msg:
                    if attempt < max_launch_attempts - 1:
                        console.print(
                            f"{EMOJI['warning']} IAM profile not yet visible to EC2, retrying in {launch_delay}s "
                            f"(attempt {attempt + 1}/{max_launch_attempts})...",
                            verbosity="info",
                        )
                        time.sleep(launch_delay)
                        continue
                # Not a propagation error or last attempt - re-raise
                raise

        if ec2_resp is None:
            raise OrchestrationError(
                f"Failed to launch EC2 instance after {max_launch_attempts} attempts. "
                f"IAM instance profile '{iam_info['profile_name']}' may not be propagated to EC2."
            )

        instance_id = ec2_resp["Instances"][0]["InstanceId"]
        self.ec2_service.wait_for_running(instance_id)

        instance_desc = self.ec2_service.describe_instance(instance_id)
        public_ip = instance_desc.get("PublicIpAddress")
        private_ip = instance_desc.get("PrivateIpAddress", "")

        return {
            "instance_id": instance_id,
            "public_ip": public_ip,
            "private_ip": private_ip,
        }

    def _build_final_state(
        self,
        config: DeploymentConfig,
        vpc_info: dict[str, Any],
        sg_id: str,
        sg_provenance: str,
        efs_id: str,
        mt_id: str,
        mt_ip: str,
        iam_info: dict[str, str],
        instance_info: dict[str, str],
        selection: InstanceSelection,
    ) -> DeploymentState:
        """
        Build final deployment state.

        Args:
            config: Deployment configuration
            vpc_info: VPC information
            sg_id: Security group ID
            sg_provenance: Security group provenance
            efs_id: EFS filesystem ID
            mt_id: EFS mount target ID
            mt_ip: EFS mount target IP address
            iam_info: IAM role and instance profile information
        instance_info: Instance information from _launch_instance()
        selection: Spot/on-demand selection metadata

        Returns:
            Complete DeploymentState object
        """
        vpc: VPCInfo = vpc_info["vpc"]
        public_subnet_ids = vpc_info["public_subnet_ids"]
        private_subnet_ids = vpc_info["private_subnet_ids"]
        chosen_storage_subnet_id = vpc_info["chosen_storage_subnet_id"]

        instance_id = instance_info["instance_id"]
        public_ip = instance_info["public_ip"]
        private_ip = instance_info["private_ip"]

        hourly_price = selection.price_per_hour
        monthly_price = hourly_price * Decimal("730")
        cost = CostTracking(
            instance_type=config.instance_type,
            is_spot=selection.is_spot,
            spot_price_per_hour=hourly_price if selection.is_spot else None,
            on_demand_price_per_hour=selection.savings_vs_on_demand.on_demand_hourly,
            estimated_monthly_cost=monthly_price,
            budget_limit=config.budget_limit,
            instance_start_time=datetime.now(UTC),
        )
        resource_provenance = {
            "vpc": "created" if vpc.created_by_geusemaker else "reused",
            "subnets": "created" if vpc.created_by_geusemaker else "reused",
            "security_group": sg_provenance,
            "efs": "created",
            "efs_mount_target": "created",
            "iam_role": "created",
            "iam_instance_profile": "created",
            "instance": "created",
            "key_pair": "reused" if config.keypair_name else "created",
        }

        return DeploymentState(
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
            efs_mount_target_ip=mt_ip,
            iam_role_name=iam_info["role_name"],
            iam_role_arn=iam_info["role_arn"],
            iam_instance_profile_name=iam_info["profile_name"],
            iam_instance_profile_arn=iam_info["profile_arn"],
            instance_id=instance_id,
            keypair_name=config.keypair_name or "",
            public_ip=public_ip,
            private_ip=private_ip,
            n8n_url=f"https://{public_ip or private_ip}" if (public_ip or private_ip) else "",
            cost=cost,
            config=config,
            resource_provenance=resource_provenance,
        )

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
