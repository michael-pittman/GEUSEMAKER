"""EFS storage stage helper for Tier1 deployments.

Pure logic extracted from ``Tier1Orchestrator._create_storage``. The EFS
service object is passed explicitly.
"""

from __future__ import annotations

from typing import Any

from geusemaker.models import DeploymentConfig
from geusemaker.services.efs import EFSService


def create_storage(
    efs_service: EFSService,
    config: DeploymentConfig,
    vpc_info: dict[str, Any],
    sg_id: str,
) -> tuple[str, str, str]:
    """Create the EFS filesystem and mount target(s).

    Provisions one mount target per public AZ for production Spot tiers (a Spot
    replacement may land in any AZ), otherwise a single mount target in the
    chosen storage subnet. Mutates ``vpc_info['efs_mount_target_ids']`` with all
    created mount-target ids and returns ``(efs_id, first_mt_id, first_mt_ip)``.
    """
    # Create EFS filesystem
    efs = efs_service.create_filesystem(tags=[{"Key": "Name", "Value": config.stack_name}])
    efs_id = efs["FileSystemId"]

    # Wait for EFS to transition from "creating" to "available" state
    efs_service.wait_for_available(efs_id)

    # A production Spot replacement may land in any configured public AZ. EFS
    # requires one mount target per AZ, so provision that coverage up front.
    chosen_storage_subnet_id = vpc_info["chosen_storage_subnet_id"]
    mount_subnet_ids = [chosen_storage_subnet_id]
    if config.tier in {"automation", "gpu"} and config.use_spot:
        seen_azs: set[str] = set()
        mount_subnet_ids = []
        for subnet in vpc_info["vpc"].public_subnets:
            if subnet.availability_zone not in seen_azs:
                mount_subnet_ids.append(subnet.subnet_id)
                seen_azs.add(subnet.availability_zone)

    mount_target_ids = [
        efs_service.create_mount_target(fs_id=efs_id, subnet_id=subnet_id, security_groups=[sg_id])
        for subnet_id in mount_subnet_ids
    ]
    for mount_target_id in mount_target_ids:
        efs_service.wait_for_mount_target_available(mount_target_id)
    mt_id = mount_target_ids[0]
    mt_ip = efs_service.get_mount_target_ip(mt_id)
    vpc_info["efs_mount_target_ids"] = mount_target_ids

    return efs_id, mt_id, mt_ip
