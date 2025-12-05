"""EFS discovery and validation."""

from __future__ import annotations

from typing import Any

from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from geusemaker.infra import AWSClientFactory
from geusemaker.models.discovery import (
    EFSInfo,
    MountTargetInfo,
    ValidationResult,
)
from geusemaker.services.base import BaseService
from geusemaker.services.discovery.cache import DiscoveryCache


def _tags_to_dict(tags: list[dict[str, Any]] | None) -> dict[str, str]:
    return {tag["Key"]: tag["Value"] for tag in tags or [] if "Key" in tag and "Value" in tag}


class EFSDiscoveryService(BaseService):
    """Discover EFS file systems and validate subnet coverage."""

    def __init__(
        self,
        client_factory: AWSClientFactory,
        region: str = "us-east-1",
        cache: DiscoveryCache | None = None,
    ):
        super().__init__(client_factory, region)
        self._efs = self._client("efs")
        self._cache = cache or DiscoveryCache()

    def list_file_systems(self, use_cache: bool = True) -> list[EFSInfo]:
        """List EFS file systems with mount targets."""
        cache_key = f"efs:{self.region}"
        cached = self._cache.get(cache_key) if use_cache else None
        if cached is not None:
            return cached  # type: ignore[return-value]

        def _call() -> list[EFSInfo]:
            paginator = self._efs.get_paginator("describe_file_systems")
            items: list[EFSInfo] = []
            for page in paginator.paginate():
                for fs in page.get("FileSystems", []):
                    fs_id = fs["FileSystemId"]
                    tags = _tags_to_dict(fs.get("Tags"))
                    mount_targets = self._describe_mount_targets(fs_id)
                    items.append(
                        EFSInfo(
                            file_system_id=fs_id,
                            name=tags.get("Name"),
                            lifecycle_state=fs.get("LifeCycleState", "available"),
                            throughput_mode=fs.get("ThroughputMode", "bursting"),
                            encrypted=fs.get("Encrypted", False),
                            kms_key_id=fs.get("KmsKeyId"),
                            size_in_bytes=int(
                                fs.get("SizeInBytes", {}).get("Value", 0),
                            ),
                            mount_targets=mount_targets,
                            tags=tags,
                        ),
                    )
            return items

        items = self._safe_call(_call)
        if use_cache:
            self._cache.set(cache_key, items)
        return items

    def validate_efs_for_subnets(
        self,
        efs_id: str,
        subnet_ids: list[str],
    ) -> ValidationResult:
        """Validate EFS mount target coverage for selected subnets."""
        efs = next((fs for fs in self.list_file_systems() if fs.file_system_id == efs_id), None)
        if efs is None:
            return ValidationResult.failed(f"EFS {efs_id} not found in {self.region}")
        result = ValidationResult.ok()
        if efs.lifecycle_state != "available":
            result.add_issue(
                f"EFS {efs.file_system_id} is in {efs.lifecycle_state} state",
            )
        targets_by_subnet = {mt.subnet_id for mt in efs.mount_targets}
        missing = [subnet for subnet in subnet_ids if subnet not in targets_by_subnet]
        if missing:
            result.add_issue(
                f"EFS {efs.file_system_id} missing mount targets for subnets: {', '.join(missing)}",
            )
        return result

    def _describe_mount_targets(self, file_system_id: str) -> list[MountTargetInfo]:
        paginator = self._efs.get_paginator("describe_mount_targets")
        targets: list[MountTargetInfo] = []
        for page in paginator.paginate(FileSystemId=file_system_id):
            for target in page.get("MountTargets", []):
                mt_id = target["MountTargetId"]
                try:
                    sg_resp = self._efs.describe_mount_target_security_groups(
                        MountTargetId=mt_id,
                    )
                    sgs = sg_resp.get("SecurityGroups", [])
                except ClientError:
                    sgs = []
                targets.append(
                    MountTargetInfo(
                        mount_target_id=mt_id,
                        file_system_id=target.get("FileSystemId", file_system_id),
                        subnet_id=target["SubnetId"],
                        availability_zone=target.get("AvailabilityZoneId") or target.get("AvailabilityZoneName", ""),
                        ip_address=target.get("IpAddress", ""),
                        lifecycle_state=target.get("LifeCycleState", "available"),
                        security_groups=sgs,
                    ),
                )
        return targets


__all__ = ["EFSDiscoveryService"]
