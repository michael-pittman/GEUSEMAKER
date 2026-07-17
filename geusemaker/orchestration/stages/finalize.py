"""Deployment-state assembly stage helpers for Tier1 deployments.

Pure builders extracted from ``Tier1Orchestrator._save_partial_state`` and
``_build_final_state``. They construct ``DeploymentState`` objects; the
coordinator still owns persistence (``state_manager.save_deployment``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from geusemaker.models import CostTracking, DeploymentConfig, DeploymentState, VPCInfo
from geusemaker.models.compute import InstanceSelection


def build_partial_state(
    config: DeploymentConfig,
    vpc_info: dict[str, Any],
    sg_id: str,
    sg_provenance: str,
    efs_id: str,
    mt_id: str,
    mt_ip: str,
    selection: InstanceSelection,
) -> DeploymentState:
    """Build the partial state saved after EFS creation, before EC2 launch.

    This lets cleanup/rollback find and delete the EFS if the instance launch
    fails.
    """
    vpc: VPCInfo = vpc_info["vpc"]
    public_subnet_ids = vpc_info["public_subnet_ids"]
    private_subnet_ids = vpc_info["private_subnet_ids"]
    chosen_storage_subnet_id = vpc_info["chosen_storage_subnet_id"]

    hourly_price = selection.price_per_hour
    monthly_price = hourly_price * Decimal("730")

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
        efs_mount_target_ids=vpc_info.get("efs_mount_target_ids", [mt_id]),
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


def build_final_state(
    config: DeploymentConfig,
    vpc_info: dict[str, Any],
    sg_id: str,
    sg_provenance: str,
    efs_id: str,
    mt_id: str,
    mt_ip: str,
    iam_info: dict[str, str],
    instance_info: dict[str, Any],
    selection: InstanceSelection,
) -> DeploymentState:
    """Build the complete deployment state after a successful instance launch."""
    vpc: VPCInfo = vpc_info["vpc"]
    public_subnet_ids = vpc_info["public_subnet_ids"]
    private_subnet_ids = vpc_info["private_subnet_ids"]
    chosen_storage_subnet_id = vpc_info["chosen_storage_subnet_id"]

    instance_id = instance_info["instance_id"]
    public_ip = instance_info["public_ip"]
    private_ip = instance_info["private_ip"]

    # Direct-instance URL scheme: host NGINX only serves HTTPS on Tier 1 with the
    # self-signed cert; otherwise (HTTPS disabled, or Tier 2/3 where the ALB/CDN
    # terminates TLS) the instance itself serves plain HTTP on port 80.
    # Tier 2/3 orchestrators overwrite n8n_url with the ALB/CloudFront endpoint.
    instance_https = config.tier == "dev" and bool(config.enable_https and config.tier1_use_self_signed)
    url_scheme = "https" if instance_https else "http"

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
        efs_mount_target_ids=vpc_info.get("efs_mount_target_ids", [mt_id]),
        efs_mount_target_ip=mt_ip,
        iam_role_name=iam_info["role_name"],
        iam_role_arn=iam_info["role_arn"],
        iam_instance_profile_name=iam_info["profile_name"],
        iam_instance_profile_arn=iam_info["profile_arn"],
        instance_id=instance_id,
        launch_template_id=instance_info.get("launch_template_id"),
        auto_scaling_group_name=instance_info.get("auto_scaling_group_name"),
        spot_event_log_group=instance_info.get("spot_event_log_group"),
        spot_event_rule_names=instance_info.get("spot_event_rule_names", []),
        spot_lease_table_name=instance_info.get("spot_lease_table_name"),
        spot_lifecycle_hook_names=instance_info.get("spot_lifecycle_hook_names", []),
        spot_coordinator_function_name=instance_info.get("spot_coordinator_function_name"),
        spot_coordinator_role_name=instance_info.get("spot_coordinator_role_name"),
        keypair_name=config.keypair_name or "",
        public_ip=public_ip,
        private_ip=private_ip,
        n8n_url=f"{url_scheme}://{public_ip or private_ip}" if (public_ip or private_ip) else "",
        cost=cost,
        config=config,
        resource_provenance=resource_provenance,
    )
