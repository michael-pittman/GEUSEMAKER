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
from geusemaker.services.ec2 import EC2Service
from geusemaker.services.efs import EFSService
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
        self._ec2_raw = ec2_client or self.client_factory.get_client("ec2", region)

    def destroy(
        self,
        state: DeploymentState,
        dry_run: bool = False,
        progress_callback: Callable[[str], None] | None = None,
    ) -> DestructionResult:
        """Delete created resources and archive state.

        Args:
            state: Deployment state to destroy
            dry_run: If True, preview deletion without making changes
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

        try:
            if state.efs_id:
                if provenance.get("efs") == "reused":
                    _progress("Preserving reused EFS mount targets")
                    if state.efs_mount_target_id:
                        preserved.append(
                            PreservedResource(
                                resource_type="efs_mount_target",
                                resource_id=state.efs_mount_target_id,
                                reason="reused",
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
                if provenance.get("efs") == "reused":
                    _progress("Preserving reused EFS filesystem")
                    preserved.append(PreservedResource(resource_type="efs", resource_id=state.efs_id, reason="reused"))
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
