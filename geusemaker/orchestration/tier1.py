"""Tier 1 deployment orchestrator."""

from __future__ import annotations

import asyncio
import logging
import secrets
import string
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from geusemaker.infra import AWSClientFactory, StateManager
from geusemaker.models import DeploymentConfig, DeploymentState
from geusemaker.models.compute import InstanceSelection, SavingsComparison
from geusemaker.orchestration.errors import OrchestrationError
from geusemaker.orchestration.stages import (
    build_block_device_mappings,
    build_final_state,
    build_partial_state,
    build_userdata_config,
    compress_userdata,
    create_storage,
    detect_root_device,
    launch_instance,
    resolve_ami,
    resolve_networking,
    resolve_security_group,
)
from geusemaker.progress import ProgressCallback, ProgressEvent, ProgressLevel, Stage
from geusemaker.services.compute.spot import SpotSelectionService
from geusemaker.services.destruction import DestructionService
from geusemaker.services.ec2 import EC2Service
from geusemaker.services.efs import EFSService
from geusemaker.services.iam import IAMService
from geusemaker.services.pricing import PricingService
from geusemaker.services.sg import SecurityGroupService
from geusemaker.services.spot_automation import SpotAutomationService
from geusemaker.services.userdata import UserDataGenerator
from geusemaker.services.vpc import VPCService

LOGGER = logging.getLogger(__name__)


class Tier1Orchestrator:
    """Coordinate VPC/EFS/SG/EC2 provisioning for dev tier deployments."""

    def __init__(
        self,
        client_factory: AWSClientFactory | None = None,
        region: str = "us-east-1",
        state_manager: StateManager | None = None,
        pricing_service: PricingService | None = None,
        spot_selector: SpotSelectionService | None = None,
        on_progress: ProgressCallback | None = None,
    ):
        self.client_factory = client_factory or AWSClientFactory()
        self.region = region
        self.state_manager = state_manager or StateManager()
        self.on_progress = on_progress
        self._last_progress_stage: Stage | None = None
        self.pricing_service = pricing_service or PricingService(self.client_factory, region=region)
        self._preselected_selection = None
        self._deploy_start_time: float | None = None
        self.vpc_service = VPCService(self.client_factory, region=region)
        self.efs_service = EFSService(self.client_factory, region=region)
        self.sg_service = SecurityGroupService(self.client_factory, region=region)
        self.ec2_service = EC2Service(self.client_factory, region=region)
        self.iam_service = IAMService(self.client_factory, region=region)
        self.spot_automation_service = SpotAutomationService(self.client_factory, region=region)
        # Initialize spot selector with EC2 service for accurate AMI-based dry-run checks
        self.spot_selector = spot_selector or SpotSelectionService(
            self.client_factory,
            pricing_service=self.pricing_service,
            region=region,
            ec2_service=self.ec2_service,
        )
        self.userdata_generator = UserDataGenerator()

    def _emit_progress(
        self,
        stage: Stage,
        message: str,
        *,
        level: ProgressLevel = "info",
        resource_id: str | None = None,
    ) -> None:
        """Emit a UI-neutral progress event to the optional callback.

        No-op when no callback is registered; tracks the most recent stage so
        failures can be attributed to the stage that was in flight.
        """
        self._last_progress_stage = stage
        if self.on_progress is not None:
            self.on_progress(ProgressEvent(stage=stage, message=message, level=level, resource_id=resource_id))

    def _generate_postgres_password(self, length: int = 32) -> str:
        """Generate a secure random password for PostgreSQL.

        The password is embedded in shell scripts (UserData) and JSON templates,
        so the alphabet must avoid characters that expand or escape there:
        $ ` \\ " ' — a password containing e.g. "$K" aborts UserData with
        "unbound variable" under set -u.
        """
        alphabet = string.ascii_letters + string.digits + "!@#%^*-_+=."
        return "".join(secrets.choice(alphabet) for _ in range(length))

    def _log_selection(self, selection: InstanceSelection) -> None:
        """Log compute selection details."""
        if selection.is_spot:
            LOGGER.info(
                f"Using spot in {selection.availability_zone or 'best AZ'} at "
                f"${selection.price_per_hour:.4f}/hr "
                f"(on-demand ${selection.savings_vs_on_demand.on_demand_hourly:.4f}/hr)"
            )
        else:
            LOGGER.info(
                f"Using on-demand at ${selection.price_per_hour:.4f}/hr "
                f"(reason: {selection.fallback_reason or selection.selection_reason})"
            )

    def _select_instance(self, config: DeploymentConfig) -> InstanceSelection:
        """Choose spot/on-demand placement, reusing any preselected choice."""
        selection = self._preselected_selection or self.spot_selector.select_instance_type(config)
        self._preselected_selection = selection
        self._log_selection(selection)
        return selection

    @staticmethod
    def _on_demand_fallback_selection(selection: InstanceSelection, reason: str) -> InstanceSelection:
        """Rebuild a spot selection as on-demand after a launch-time capacity failure."""
        on_demand = selection.savings_vs_on_demand.on_demand_hourly
        return InstanceSelection(
            instance_type=selection.instance_type,
            availability_zone=selection.availability_zone,
            is_spot=False,
            price_per_hour=on_demand,
            selection_reason="Falling back to on-demand",
            fallback_reason=reason,
            savings_vs_on_demand=SavingsComparison(
                on_demand_hourly=on_demand,
                selected_hourly=on_demand,
                hourly_savings=Decimal("0"),
                monthly_savings=Decimal("0"),
                savings_percentage=0.0,
            ),
            pricing_source="live",
        )

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
            final_state = self._deploy_impl(config)
            self._emit_progress("finalize", f"Deployment state saved for {config.stack_name}")
            return final_state
        except Exception as exc:
            self._emit_progress(
                self._last_progress_stage or "validate",
                f"Deployment failed: {exc}",
                level="error",
            )
            # Attempt to load partial state to check for created resources
            partial_state = asyncio.run(self.state_manager.load_deployment(config.stack_name))

            # If partial state exists and rollback is enabled, clean up resources
            if partial_state and enable_rollback:
                LOGGER.error(f"Deployment failed: {exc}")
                LOGGER.warning("Initiating automatic cleanup of partial deployment...")
                try:
                    self._cleanup_partial_deployment(partial_state)
                    LOGGER.info("Cleanup completed successfully. Partial resources have been cleaned up.")
                except Exception as rollback_exc:  # noqa: BLE001
                    LOGGER.error(f"Rollback failed: {rollback_exc}")
                    LOGGER.warning(
                        f"Manual cleanup may be required. Check AWS Console for orphaned resources tagged with Stack: {config.stack_name}"
                    )

            # If no rollback or rollback disabled, just save failed state
            elif partial_state:
                LOGGER.error(f"Deployment failed: {exc}")
                LOGGER.warning("Rollback disabled. Saving failed state for manual recovery.")
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
            LOGGER.info(msg)

        result = destruction_service.destroy(partial_state, dry_run=False, progress_callback=progress_callback)

        if result.errors:
            error_summary = "; ".join(result.errors)
            raise RuntimeError(f"Rollback encountered errors: {error_summary}")
        # destroy() already archived the state and removed the deployment file.

    def _save_failed_state(self, partial_state: DeploymentState, error: Exception) -> None:
        """
        Save failed deployment state with error details.

        Args:
            partial_state: Partial deployment state
            error: The exception that caused the failure
        """
        # Update state to reflect failure.
        # Copy the WHOLE partial state: rebuilding it field-by-field silently
        # dropped Tier 2/3 fields (alb_arn, target_group_arn, certificate_arn),
        # so a later destroy skipped the ordered ALB teardown and cascaded into
        # subnet/VPC DependencyViolations (observed live).
        # Note: Error message is logged and displayed to user, not stored in state
        failed_state = partial_state.model_copy(
            update={
                "status": "failed",
                "updated_at": datetime.now(UTC),
            }
        )

        asyncio.run(self.state_manager.save_deployment(failed_state))

        LOGGER.info(
            f"Failed state saved. Use 'geusemaker destroy {partial_state.stack_name}' to clean up orphaned resources."
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
        self._emit_progress("spot", f"Selecting compute capacity for {config.instance_type}")
        selection = self._select_instance(config)

        # Step 1: Setup networking (VPC, subnets)
        self._emit_progress("vpc", "Configuring VPC networking")
        vpc_info = self._setup_networking(config, selection)
        self._emit_progress("vpc", "Networking ready", resource_id=vpc_info["vpc"].vpc_id)
        self._check_timeout(start_time, config.rollback_timeout_minutes, "networking")

        # Step 2: Create or reuse security group
        self._emit_progress("sg", "Configuring security group")
        sg_id, sg_provenance = self._create_security_group(config, vpc_info)
        self._emit_progress("sg", "Security group ready", resource_id=sg_id)
        self._check_timeout(start_time, config.rollback_timeout_minutes, "security group creation")

        # Step 3: Create EFS filesystem and mount target
        self._emit_progress("efs", "Creating EFS filesystem and mount targets")
        efs_id, mt_id, mt_ip = self._create_storage(config, vpc_info, sg_id)
        self._emit_progress("efs", "EFS filesystem available", resource_id=efs_id)
        self._check_timeout(start_time, config.rollback_timeout_minutes, "storage setup")

        # Step 4: Save partial state after EFS creation
        self._save_partial_state(config, vpc_info, sg_id, sg_provenance, efs_id, mt_id, mt_ip, selection)

        # Step 5: Create IAM role and instance profile for EFS mount
        self._emit_progress("iam", "Creating IAM role and instance profile")
        iam_info = self._create_iam_resources(config)
        self._check_timeout(start_time, config.rollback_timeout_minutes, "IAM setup")

        if config.tier in {"automation", "gpu"} and selection.is_spot:
            account_id = iam_info["role_arn"].split(":")[4]
            lease_table_name = f"{config.stack_name}-spot-lease"[:255]
            log_group_name = f"/geusemaker/{config.stack_name}/spot-events"
            self.iam_service.attach_spot_runtime_policy(
                iam_info["role_name"],
                lease_table_arn=(f"arn:aws:dynamodb:{self.region}:{account_id}:table/{lease_table_name}"),
                log_group_arn=(f"arn:aws:logs:{self.region}:{account_id}:log-group:{log_group_name}"),
            )

        # Step 6: Generate UserData script
        self._emit_progress("userdata", "Generating instance UserData")
        userdata_payload, postgres_password = self._generate_userdata(
            config,
            efs_id,
            mt_ip,
            spot_protection_enabled=(config.tier in {"automation", "gpu"} and selection.is_spot),
        )
        self._check_timeout(start_time, config.rollback_timeout_minutes, "UserData generation")

        # Step 7: Launch EC2 instance with IAM instance profile
        self._emit_progress("ec2", f"Launching {config.instance_type} instance")
        instance_info = self._launch_instance(
            config,
            vpc_info,
            sg_id,
            userdata_payload,
            iam_info,
            selection,
        )
        self._emit_progress("ec2", "Instance running", resource_id=instance_info["instance_id"])
        self._check_timeout(start_time, config.rollback_timeout_minutes, "instance launch")

        # If spot capacity vanished at launch and we fell back to on-demand,
        # update the selection so cost tracking and state match reality.
        if instance_info.get("spot_fallback_to_on_demand"):
            selection = self._on_demand_fallback_selection(
                selection,
                "Spot capacity unavailable at launch; launched on-demand",
            )
            self._preselected_selection = selection
            self._log_selection(selection)

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
        """Setup VPC and select subnets for deployment (delegates to stages.networking)."""
        return resolve_networking(self.vpc_service, config, selection)

    def _create_security_group(
        self,
        config: DeploymentConfig,
        vpc_info: dict[str, Any],
    ) -> tuple[str, str]:
        """Create or reuse security group (delegates to stages.networking)."""
        return resolve_security_group(self.sg_service, config, vpc_info)

    def _create_storage(
        self,
        config: DeploymentConfig,
        vpc_info: dict[str, Any],
        sg_id: str,
    ) -> tuple[str, str, str]:
        """Create EFS filesystem and mount target (delegates to stages.storage)."""
        return create_storage(self.efs_service, config, vpc_info, sg_id)

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
        partial_state = build_partial_state(config, vpc_info, sg_id, sg_provenance, efs_id, mt_id, mt_ip, selection)
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

        LOGGER.info(f"Creating IAM role for EFS mount: {role_name}")
        role_arn = self.iam_service.create_efs_mount_role(role_name, tags)

        LOGGER.info(f"Creating IAM instance profile: {profile_name}")
        profile_arn = self.iam_service.create_instance_profile(profile_name, tags)

        LOGGER.info("Attaching role to instance profile")
        self.iam_service.attach_role_to_profile(profile_name, role_name)

        LOGGER.info("Waiting for instance profile with role attachment")
        self.iam_service.wait_for_instance_profile(profile_name, role_name)

        return {
            "role_name": role_name,
            "role_arn": role_arn,
            "profile_name": profile_name,
            "profile_arn": profile_arn,
        }

    def _generate_userdata(
        self,
        config: DeploymentConfig,
        efs_id: str,
        mt_ip: str,
        *,
        spot_protection_enabled: bool = False,
    ) -> tuple[bytes, str]:
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
        userdata_config = build_userdata_config(
            config,
            self.region,
            efs_id,
            mt_ip,
            postgres_password,
            spot_protection_enabled=spot_protection_enabled,
        )
        userdata_script = self.userdata_generator.generate(userdata_config)
        userdata_payload = compress_userdata(userdata_script)

        return userdata_payload, postgres_password

    def _launch_instance(
        self,
        config: DeploymentConfig,
        vpc_info: dict[str, Any],
        sg_id: str,
        userdata_payload: bytes,
        iam_info: dict[str, str],
        selection: InstanceSelection,
    ) -> dict[str, Any]:
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
        # AMI resolution + root-device detection (delegates to stages.ami).
        ami_id = resolve_ami(self.ec2_service, config)
        root_device_name = detect_root_device(self.ec2_service, ami_id)
        block_device_mappings = build_block_device_mappings(root_device_name)

        # EC2 launch / Spot ASG creation + IAM-propagation retry (stages.compute_launch).
        return launch_instance(
            self.ec2_service,
            self.spot_automation_service,
            config,
            vpc_info,
            sg_id,
            userdata_payload,
            iam_info,
            selection,
            ami_id,
            block_device_mappings,
        )

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
        return build_final_state(
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


__all__ = ["Tier1Orchestrator"]
