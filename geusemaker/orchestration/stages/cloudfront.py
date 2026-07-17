"""CloudFront CDN stage helpers for Tier3 deployments.

Pure, stateless logic extracted from ``Tier3Orchestrator``'s private methods
(``_create_cloudfront``, ``_wait_for_cloudfront``, ``_build_tier3_state``).
Service objects and resource ids are passed explicitly rather than via ``self``
so the coordinator stays a thin sequencer and the bulk logic is unit-testable in
isolation.

No module here imports ``geusemaker.cli`` — presentation depends on
orchestration, never the reverse (enforced by the import-direction guard test).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from geusemaker.models import DeploymentConfig, DeploymentState
from geusemaker.services import CloudFrontService

LOGGER = logging.getLogger(__name__)


def create_cloudfront(
    cloudfront_service: CloudFrontService,
    config: DeploymentConfig,
    tier2_state: DeploymentState,
) -> dict[str, str]:
    """Create a CloudFront distribution with the ALB as custom origin.

    Returns the distribution id and domain name.
    """
    stack_name = config.stack_name
    caller_reference = f"{stack_name}-{datetime.now(UTC).timestamp()}"

    # Create distribution with ALB as origin
    LOGGER.debug("Creating CloudFront distribution with ALB origin...")

    # CloudFront can only use an HTTPS origin when the origin domain is covered by the
    # ALB certificate, i.e. the custom domain (Route 53 alias -> ALB, created in Tier 2).
    # Without one, reach the ALB over HTTP on its raw DNS name.
    https_origin = bool(tier2_state.https_enabled and config.alb_domain_name)
    origin_domain = config.alb_domain_name if https_origin else tier2_state.alb_dns
    if not https_origin:
        LOGGER.info(
            "CloudFront will reach the ALB origin over HTTP (no custom-domain certificate available for the origin)."
        )

    # For Tier 3, we use default caching (TTL=0) to forward all requests to ALB
    # Users can customize cache behaviors in future iterations
    cf_resp = cloudfront_service.create_distribution_with_alb_origin(
        alb_dns_name=origin_domain,
        origin_protocol_policy="https-only" if https_origin else "http-only",
        caller_reference=caller_reference,
        enabled=True,
        comment=f"GeuseMaker CDN for {stack_name}",
        default_ttl=0,  # No caching by default - forward all to ALB
        min_ttl=0,
        max_ttl=0,
        compress=True,  # Enable compression for better performance
        price_class="PriceClass_100",  # US, Canada, Europe (cheapest)
    )

    distribution = cf_resp["Distribution"]
    distribution_id = distribution["Id"]
    cloudfront_domain = distribution["DomainName"]

    LOGGER.info(f"CloudFront distribution created: {distribution_id}")

    return {
        "distribution_id": distribution_id,
        "cloudfront_domain": cloudfront_domain,
    }


def wait_for_cloudfront(
    cloudfront_service: CloudFrontService,
    distribution_id: str,
    max_wait_minutes: int = 40,
) -> None:
    """Wait for the CloudFront distribution to reach 'Deployed' status.

    Polls every 30 seconds via the service's wait method.
    """
    max_attempts = max_wait_minutes * 2  # Poll every 30 seconds
    delay = 30

    LOGGER.info("CloudFront deployment typically takes 15-30 minutes...")

    # Call the service's wait method which handles polling
    cloudfront_service.wait_for_deployed(
        distribution_id=distribution_id,
        max_attempts=max_attempts,
        delay=delay,
    )

    LOGGER.info("CloudFront distribution deployed successfully")


def build_tier3_state(
    tier2_state: DeploymentState,
    cloudfront_info: dict[str, str],
) -> DeploymentState:
    """Build the final Tier 3 deployment state with CloudFront information."""
    # Prefer the custom domain (kept as n8n's public URL and DNS target); otherwise
    # the CloudFront domain is the public entry point (TLS by default).
    if tier2_state.https_enabled and tier2_state.config.alb_domain_name:
        n8n_url = f"https://{tier2_state.config.alb_domain_name}"
    else:
        n8n_url = f"https://{cloudfront_info['cloudfront_domain']}"

    # Update resource provenance
    resource_provenance = tier2_state.resource_provenance.copy()
    resource_provenance.update(
        {
            "cloudfront": "created",
        }
    )

    return DeploymentState(
        stack_name=tier2_state.stack_name,
        status="running",
        created_at=tier2_state.created_at,
        updated_at=datetime.now(UTC),
        vpc_id=tier2_state.vpc_id,
        subnet_ids=tier2_state.subnet_ids,
        storage_subnet_id=tier2_state.storage_subnet_id,
        security_group_id=tier2_state.security_group_id,
        efs_id=tier2_state.efs_id,
        efs_mount_target_id=tier2_state.efs_mount_target_id,
        efs_mount_target_ids=tier2_state.efs_mount_target_ids,
        efs_mount_target_ip=tier2_state.efs_mount_target_ip,
        iam_role_name=tier2_state.iam_role_name,
        iam_role_arn=tier2_state.iam_role_arn,
        iam_instance_profile_name=tier2_state.iam_instance_profile_name,
        iam_instance_profile_arn=tier2_state.iam_instance_profile_arn,
        instance_id=tier2_state.instance_id,
        launch_template_id=tier2_state.launch_template_id,
        auto_scaling_group_name=tier2_state.auto_scaling_group_name,
        spot_event_log_group=tier2_state.spot_event_log_group,
        spot_event_rule_names=tier2_state.spot_event_rule_names,
        spot_lease_table_name=tier2_state.spot_lease_table_name,
        spot_lifecycle_hook_names=tier2_state.spot_lifecycle_hook_names,
        spot_coordinator_function_name=tier2_state.spot_coordinator_function_name,
        spot_coordinator_role_name=tier2_state.spot_coordinator_role_name,
        keypair_name=tier2_state.keypair_name,
        public_ip=tier2_state.public_ip,
        private_ip=tier2_state.private_ip,
        # Tier 2 ALB fields
        alb_arn=tier2_state.alb_arn,
        alb_dns=tier2_state.alb_dns,
        target_group_arn=tier2_state.target_group_arn,
        # Tier 3 CloudFront fields
        cloudfront_id=cloudfront_info["distribution_id"],
        cloudfront_domain=cloudfront_info["cloudfront_domain"],
        n8n_url=n8n_url,
        # Carry HTTPS/TLS fields forward (destroy needs certificate_arn for cleanup)
        https_enabled=tier2_state.https_enabled,
        https_endpoint=tier2_state.https_endpoint,
        certificate_arn=tier2_state.certificate_arn,
        nginx_proxy_enabled=tier2_state.nginx_proxy_enabled,
        cost=tier2_state.cost,
        config=tier2_state.config,
        resource_provenance=resource_provenance,
    )
