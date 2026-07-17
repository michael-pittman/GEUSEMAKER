"""Networking and security-group stage helpers for Tier1 deployments.

Pure logic extracted from ``Tier1Orchestrator._setup_networking`` and
``_create_security_group``. Service objects are passed explicitly.
"""

from __future__ import annotations

import logging
from typing import Any

from geusemaker.models import DeploymentConfig, VPCInfo
from geusemaker.models.compute import InstanceSelection
from geusemaker.orchestration.errors import OrchestrationError
from geusemaker.services.sg import SecurityGroupService
from geusemaker.services.vpc import VPCService

LOGGER = logging.getLogger(__name__)


def resolve_networking(
    vpc_service: VPCService,
    config: DeploymentConfig,
    selection: InstanceSelection,
) -> dict[str, Any]:
    """Configure/create the VPC and select the compute and storage subnets.

    Returns a dict with the ``VPCInfo``, all subnet ids, and the chosen public
    and storage subnet ids/AZ used by downstream stages.
    """
    # Create or configure VPC
    if config.vpc_id:
        vpc = vpc_service.configure_existing_vpc(
            config.vpc_id,
            name=config.stack_name,
            deployment=config.stack_name,
            tier=config.tier,
            attach_internet_gateway=config.attach_internet_gateway,
        )
    else:
        vpc = vpc_service.create_vpc_with_subnets(
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
                LOGGER.info(f"Placing compute in {selection.availability_zone} to match spot pricing.")
            else:
                fallback_subnet = subnet_lookup.get(chosen_public_subnet_id)
                fallback_az = fallback_subnet.availability_zone if fallback_subnet else "unknown"
                LOGGER.warning(
                    f"No public subnet in {selection.availability_zone} where spot "
                    f"pricing/capacity was validated; launching in {fallback_az} instead. "
                    "Actual spot price and capacity may differ."
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


def resolve_security_group(
    sg_service: SecurityGroupService,
    config: DeploymentConfig,
    vpc_info: dict[str, Any],
) -> tuple[str, str]:
    """Create or reuse the security group, returning ``(group_id, provenance)``."""
    if config.security_group_id:
        # When reusing a security group with HTTPS enabled, ensure port 443 is open
        if config.enable_https:
            port_added = sg_service.ensure_https_port(config.security_group_id)
            if port_added:
                LOGGER.info("HTTPS port 443 added to security group")
            else:
                LOGGER.info("Port 443 (HTTPS) already open")
        return config.security_group_id, "reused"

    vpc: VPCInfo = vpc_info["vpc"]
    # Service containers bind to 127.0.0.1 and all traffic flows through host
    # NGINX on 80/443, so no service ports (5678 etc.) are opened externally.
    ingress = [
        {"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
        {"IpProtocol": "tcp", "FromPort": 80, "ToPort": 80, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
        {"IpProtocol": "tcp", "FromPort": 2049, "ToPort": 2049, "IpRanges": [{"CidrIp": vpc.cidr_block}]},
    ]
    # Add HTTPS port when HTTPS is enabled
    if config.enable_https:
        ingress.append(
            {"IpProtocol": "tcp", "FromPort": 443, "ToPort": 443, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
        )
    sg_resp = sg_service.create_security_group(
        name=f"{config.stack_name}-sg",
        description="GeuseMaker dev SG",
        vpc_id=vpc.vpc_id,
        ingress_rules=ingress,
    )
    return sg_resp["group_id"], "created"
