"""Service that tears down deployments in dependency order."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from time import monotonic
from typing import Any

from geusemaker.infra import AWSClientFactory, StateManager
from geusemaker.models import DeploymentState
from geusemaker.models.destruction import (
    DeletedResource,
    DestructionResult,
    PreservedResource,
)
from geusemaker.services.alb import ALBService
from geusemaker.services.cloudfront import CloudFrontService
from geusemaker.services.ec2 import EC2Service
from geusemaker.services.efs import EFSService
from geusemaker.services.iam import IAMService
from geusemaker.services.sg import SecurityGroupService


class DestructionService:
    """Destroy deployment resources while preserving reused assets."""

    def __init__(
        self,
        client_factory: AWSClientFactory | None = None,
        state_manager: StateManager | None = None,
        region: str = "us-east-1",
        ec2_client: Any | None = None,
        efs_client: Any | None = None,
    ):
        self.client_factory = client_factory or AWSClientFactory()
        self.state_manager = state_manager or StateManager()
        self.region = region
        self.ec2 = EC2Service(self.client_factory, region=region)
        if ec2_client:
            self.ec2._ec2 = ec2_client  # type: ignore[attr-defined]
        self.efs = EFSService(self.client_factory, region=region)
        if efs_client:
            self.efs._efs = efs_client  # type: ignore[attr-defined]
        self.sg_service = SecurityGroupService(self.client_factory, region=region)
        if ec2_client:
            self.sg_service._ec2 = ec2_client  # type: ignore[attr-defined]
        self.iam = IAMService(self.client_factory, region=region)
        self.alb = ALBService(self.client_factory, region=region)
        self.cloudfront = CloudFrontService(self.client_factory, region=region)
        self._ec2_raw = ec2_client or self.client_factory.get_client("ec2", region)
        self._elbv2_raw = self.client_factory.get_client("elbv2", region)

    def destroy(
        self,
        state: DeploymentState,
        dry_run: bool = False,
        preserve_efs: bool = False,
        progress_callback: Callable[[str], None] | None = None,
    ) -> DestructionResult:
        """Delete created resources and archive state.

        Args:
            state: Deployment state to destroy
            dry_run: If True, preview deletion without making changes
            preserve_efs: If True, preserve EFS filesystem and mount targets
            progress_callback: Optional callback to report progress (called with status messages)
        """
        start = monotonic()
        deleted: list[DeletedResource] = []
        preserved: list[PreservedResource] = []
        errors: list[str] = []
        provenance = self._provenance(state)

        def _progress(msg: str) -> None:
            if progress_callback:
                progress_callback(msg)

        # CloudFront cleanup (must be before ALB deletion - CloudFront depends on ALB as origin)
        try:
            if state.cloudfront_id:
                if provenance.get("cloudfront") == "reused":
                    _progress("Preserving reused CloudFront distribution")
                    preserved.append(
                        PreservedResource(
                            resource_type="cloudfront",
                            resource_id=state.cloudfront_id,
                            reason="reused",
                        ),
                    )
                else:
                    _progress(f"Disabling CloudFront distribution {state.cloudfront_id}")
                    if not dry_run:
                        try:
                            # Get current distribution config and ETag
                            dist_resp = self.cloudfront.get_distribution(state.cloudfront_id)
                            etag = dist_resp["ETag"]

                            # Disable the distribution
                            disable_resp = self.cloudfront.disable_distribution(state.cloudfront_id, etag)
                            new_etag = disable_resp["ETag"]

                            _progress("Waiting for CloudFront distribution to deploy (this may take several minutes)")
                            self.cloudfront.wait_for_deployed(
                                distribution_id=state.cloudfront_id,
                                max_attempts=60,  # 30 minutes max
                                delay=30,
                            )

                            # Delete the distribution
                            _progress(f"Deleting CloudFront distribution {state.cloudfront_id}")
                            self.cloudfront.delete_distribution(state.cloudfront_id, new_etag)
                        except Exception as exc:  # noqa: BLE001
                            errors.append(f"CloudFront deletion failed: {exc}")
                    deleted.append(self._deleted("cloudfront", state.cloudfront_id))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"CloudFront cleanup failed: {exc}")

        # ALB cleanup (must be before EC2 instance termination)
        try:
            if state.target_group_arn:
                if provenance.get("target_group") == "reused":
                    _progress("Preserving reused target group")
                    preserved.append(
                        PreservedResource(
                            resource_type="target_group",
                            resource_id=state.target_group_arn,
                            reason="reused",
                        ),
                    )
                else:
                    # Deregister instances from target group first
                    if state.instance_id:
                        _progress(f"Deregistering instance {state.instance_id} from target group")
                        if not dry_run:
                            try:
                                self._elbv2_raw.deregister_targets(
                                    TargetGroupArn=state.target_group_arn,
                                    Targets=[{"Id": state.instance_id}],
                                )
                            except Exception as exc:  # noqa: BLE001
                                errors.append(f"Target deregistration failed: {exc}")

                    _progress("Deleting target group")
                    if not dry_run:
                        try:
                            self._elbv2_raw.delete_target_group(TargetGroupArn=state.target_group_arn)
                        except Exception as exc:  # noqa: BLE001
                            errors.append(f"Target group deletion failed: {exc}")
                    deleted.append(self._deleted("target_group", state.target_group_arn))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Target group cleanup failed: {exc}")

        try:
            if state.alb_arn:
                if provenance.get("alb") == "reused":
                    _progress("Preserving reused ALB")
                    preserved.append(
                        PreservedResource(resource_type="alb", resource_id=state.alb_arn, reason="reused"),
                    )
                else:
                    _progress("Deleting Application Load Balancer")
                    if not dry_run:
                        try:
                            self._elbv2_raw.delete_load_balancer(LoadBalancerArn=state.alb_arn)
                        except Exception as exc:  # noqa: BLE001
                            errors.append(f"ALB deletion failed: {exc}")
                    deleted.append(self._deleted("alb", state.alb_arn))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"ALB cleanup failed: {exc}")

        try:
            if state.instance_id:
                if provenance.get("instance") == "reused":
                    _progress("Preserving reused EC2 instance")
                    preserved.append(
                        PreservedResource(resource_type="ec2_instance", resource_id=state.instance_id, reason="reused"),
                    )
                else:
                    _progress("Terminating EC2 instance")
                    if not dry_run:
                        self.ec2.terminate_instance(state.instance_id)
                        _progress("Waiting for EC2 instance termination")
                        self.ec2.wait_for_terminated(state.instance_id)
                    deleted.append(self._deleted("ec2_instance", state.instance_id))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Instance termination failed: {exc}")

        # IAM cleanup: instance profile and role (must be after EC2 instance termination)
        try:
            if state.iam_instance_profile_name:
                if provenance.get("iam_instance_profile") == "reused":
                    _progress("Preserving reused IAM instance profile")
                    preserved.append(
                        PreservedResource(
                            resource_type="iam_instance_profile",
                            resource_id=state.iam_instance_profile_name,
                            reason="reused",
                        ),
                    )
                else:
                    _progress(f"Deleting IAM instance profile {state.iam_instance_profile_name}")
                    if not dry_run:
                        self.iam.delete_instance_profile(
                            state.iam_instance_profile_name,
                            state.iam_role_name,
                        )
                    deleted.append(self._deleted("iam_instance_profile", state.iam_instance_profile_name))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"IAM instance profile deletion failed: {exc}")

        try:
            if state.iam_role_name:
                if provenance.get("iam_role") == "reused":
                    _progress("Preserving reused IAM role")
                    preserved.append(
                        PreservedResource(
                            resource_type="iam_role",
                            resource_id=state.iam_role_name,
                            reason="reused",
                        ),
                    )
                else:
                    _progress(f"Deleting IAM role {state.iam_role_name}")
                    if not dry_run:
                        self.iam.delete_role(state.iam_role_name)
                    deleted.append(self._deleted("iam_role", state.iam_role_name))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"IAM role deletion failed: {exc}")

        try:
            if state.efs_id:
                if provenance.get("efs") == "reused" or preserve_efs:
                    reason = "preserved by --preserve-efs flag" if preserve_efs else "reused"
                    _progress(f"Preserving EFS mount targets ({reason})")
                    if state.efs_mount_target_id:
                        preserved.append(
                            PreservedResource(
                                resource_type="efs_mount_target",
                                resource_id=state.efs_mount_target_id,
                                reason=reason,
                            ),
                        )
                else:
                    mount_target_ids = self._mount_target_ids(state.efs_id, state.efs_mount_target_id)
                    for mt_id in mount_target_ids:
                        try:
                            _progress(f"Deleting EFS mount target {mt_id}")
                            if not dry_run:
                                self.efs.delete_mount_target(mt_id)
                                _progress(f"Waiting for EFS mount target {mt_id} deletion")
                                self.efs.wait_for_mount_target_deleted(mt_id)
                            deleted.append(self._deleted("efs_mount_target", mt_id))
                        except Exception as exc:  # noqa: BLE001
                            errors.append(f"EFS mount target {mt_id} deletion failed: {exc}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"EFS mount target deletion failed: {exc}")

        try:
            if state.efs_id:
                if provenance.get("efs") == "reused" or preserve_efs:
                    reason = "preserved by --preserve-efs flag" if preserve_efs else "reused"
                    _progress(f"Preserving EFS filesystem ({reason})")
                    preserved.append(PreservedResource(resource_type="efs", resource_id=state.efs_id, reason=reason))
                else:
                    _progress("Deleting EFS filesystem")
                    if not dry_run:
                        self.efs.delete_filesystem(state.efs_id)
                    deleted.append(self._deleted("efs", state.efs_id))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"EFS deletion failed: {exc}")

        try:
            if state.security_group_id:
                if provenance.get("security_group") == "reused":
                    _progress("Preserving reused security group")
                    preserved.append(
                        PreservedResource(
                            resource_type="security_group",
                            resource_id=state.security_group_id,
                            reason="reused",
                        ),
                    )
                else:
                    _progress("Deleting security group")
                    if not dry_run:
                        self.sg_service.delete_security_group(state.security_group_id)
                    deleted.append(self._deleted("security_group", state.security_group_id))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Security group deletion failed: {exc}")

        try:
            if provenance.get("subnets") != "reused":
                _progress("Deleting subnets")
                for subnet_id in state.subnet_ids:
                    if not dry_run:
                        self._ec2_raw.delete_subnet(SubnetId=subnet_id)
                    deleted.append(self._deleted("subnet", subnet_id))
            else:
                _progress("Preserving reused subnets")
                for subnet_id in state.subnet_ids:
                    preserved.append(PreservedResource(resource_type="subnet", resource_id=subnet_id, reason="reused"))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Subnet deletion failed: {exc}")

        try:
            if provenance.get("vpc") != "reused":
                _progress("Deleting VPC dependencies")
                if not dry_run:
                    self._delete_vpc_dependencies(state.vpc_id, errors)
                    _progress("Deleting VPC")
                    self._ec2_raw.delete_vpc(VpcId=state.vpc_id)
                deleted.append(self._deleted("vpc", state.vpc_id))
            else:
                _progress("Preserving reused VPC")
                preserved.append(PreservedResource(resource_type="vpc", resource_id=state.vpc_id, reason="reused"))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"VPC deletion failed: {exc}")

        archived_path: str | None = None
        if not dry_run:
            _progress("Archiving deployment state")
            state.status = "terminated"
            state.terminated_at = datetime.now(UTC)
            archived = asyncio.run(self.state_manager.archive_deployment(state))
            archived_path = str(archived)
            asyncio.run(self.state_manager.delete_deployment(state.stack_name))

        duration = monotonic() - start
        return DestructionResult(
            success=not errors,
            deleted_resources=deleted,
            preserved_resources=preserved,
            errors=errors,
            duration_seconds=duration,
            archived_state_path=archived_path,
        )

    def _deleted(self, resource_type: str, resource_id: str) -> DeletedResource:
        return DeletedResource(
            resource_type=resource_type,
            resource_id=resource_id,
            deleted_at=datetime.now(UTC),
            deletion_time_seconds=0.0,
        )

    def _provenance(self, state: DeploymentState) -> dict[str, str]:
        if state.resource_provenance:
            return state.resource_provenance
        prov = {
            "vpc": "reused" if state.config.vpc_id else "created",
            "subnets": "reused" if state.config.vpc_id else "created",
            "security_group": "created",
            "efs": "created",
            "instance": "created",
        }
        return prov

    def _mount_target_ids(self, fs_id: str, fallback_mt: str | None) -> list[str]:
        """Return all mount target IDs for an EFS, with fallback to state value."""
        mount_targets = self.efs.list_mount_targets(fs_id)
        if not mount_targets and fallback_mt:
            return [fallback_mt]
        return mount_targets

    def _delete_vpc_dependencies(self, vpc_id: str, errors: list[str]) -> None:
        """Detach and delete dependent internet gateways, network interfaces, and non-main route tables."""
        # Delete network interfaces first (must be done before VPC deletion)
        try:
            enis = self._ec2_raw.describe_network_interfaces(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]).get(
                "NetworkInterfaces", []
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Describe network interfaces failed: {exc}")
            enis = []

        for eni in enis:
            eni_id = eni.get("NetworkInterfaceId")
            # Skip network interfaces that are attached to running instances
            # They will be deleted automatically when the instance is terminated
            attachment = eni.get("Attachment", {})
            if attachment.get("Status") == "attached":
                continue

            try:
                # Detach if still attached
                if attachment:
                    attachment_id = attachment.get("AttachmentId")
                    if attachment_id:
                        self._ec2_raw.detach_network_interface(AttachmentId=attachment_id, Force=True)
                # Delete the network interface
                self._ec2_raw.delete_network_interface(NetworkInterfaceId=eni_id)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Network interface {eni_id} deletion failed: {exc}")

        try:
            igws = self._ec2_raw.describe_internet_gateways(
                Filters=[{"Name": "attachment.vpc-id", "Values": [vpc_id]}]
            ).get("InternetGateways", [])
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Describe internet gateways failed: {exc}")
            igws = []

        for igw in igws:
            igw_id = igw.get("InternetGatewayId")
            try:
                attachments = igw.get("Attachments", [])
                if any(att.get("VpcId") == vpc_id for att in attachments):
                    self._ec2_raw.detach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)
                self._ec2_raw.delete_internet_gateway(InternetGatewayId=igw_id)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Internet gateway {igw_id} deletion failed: {exc}")

        try:
            route_tables = self._ec2_raw.describe_route_tables(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]).get(
                "RouteTables", []
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Describe route tables failed: {exc}")
            route_tables = []

        for rt in route_tables:
            rt_id = rt.get("RouteTableId")
            associations = rt.get("Associations", [])
            if any(assoc.get("Main") for assoc in associations):
                continue
            try:
                self._ec2_raw.delete_route_table(RouteTableId=rt_id)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Route table {rt_id} deletion failed: {exc}")


__all__ = ["DestructionService"]
