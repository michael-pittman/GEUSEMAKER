"""Tier 3 deployment orchestrator with CloudFront CDN support."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

from geusemaker.cli import console
from geusemaker.cli.branding import EMOJI
from geusemaker.infra import AWSClientFactory, StateManager
from geusemaker.models import DeploymentConfig, DeploymentState
from geusemaker.orchestration.errors import OrchestrationError
from geusemaker.orchestration.tier2 import Tier2Orchestrator
from geusemaker.services import CloudFrontService


class Tier3Orchestrator(Tier2Orchestrator):
    """Coordinate Tier 3 deployments with CloudFront CDN support."""

    def __init__(
        self,
        client_factory: AWSClientFactory | None = None,
        region: str = "us-east-1",
        state_manager: StateManager | None = None,
        pricing_service=None,
        spot_selector=None,
    ):
        super().__init__(
            client_factory,
            region,
            state_manager,
            pricing_service=pricing_service,
            spot_selector=spot_selector,
        )
        self.cloudfront_service = CloudFrontService(self.client_factory, region=region)

    def _deploy_impl(self, config: DeploymentConfig) -> DeploymentState:
        """
        Internal implementation of Tier3 deployment with CloudFront CDN.

        Args:
            config: Deployment configuration

        Returns:
            DeploymentState with all resource IDs and metadata including CloudFront

        Raises:
            OrchestrationError: If deployment validation or resource creation fails
        """
        if config.tier not in ("gpu", "automation", "dev"):
            raise OrchestrationError(
                f"Tier3Orchestrator supports 'dev', 'automation', and 'gpu' tiers, got: {config.tier}"
            )

        # Validate ALB is enabled for Tier 3 (CloudFront requires ALB origin)
        if not config.enable_alb:
            raise OrchestrationError("Tier 3 deployments require enable_alb=True. CloudFront needs ALB as origin.")

        # Step 1-10: Execute Tier 2 deployment (VPC, SG, EFS, IAM, EC2, ALB)
        console.print(f"{EMOJI['info']} Executing Tier 2 deployment steps...", verbosity="info")
        tier2_state = super()._deploy_impl(config)

        start_time = self._deploy_start_time or time.monotonic()
        self._check_timeout(start_time, config.rollback_timeout_minutes, "before CloudFront setup")

        # Verify ALB was created (should always be true given enable_alb check above)
        if not tier2_state.alb_dns:
            raise OrchestrationError("Tier 2 deployment did not create ALB. Cannot proceed with CloudFront creation.")

        # Step 11: Create CloudFront distribution with ALB as origin
        console.print(f"\n{EMOJI['rocket']} Creating CloudFront distribution...", verbosity="info")
        cloudfront_info = self._create_cloudfront(config, tier2_state)

        # Step 12: Wait for CloudFront to deploy (15-30 minutes typical)
        console.print(
            f"{EMOJI['info']} Waiting for CloudFront deployment (this can take 15-30 minutes)...",
            verbosity="info",
        )
        self._wait_for_cloudfront(
            cloudfront_info["distribution_id"],
            max_wait_minutes=config.rollback_timeout_minutes,
        )

        # Step 13: Build final Tier 3 state with CloudFront info
        final_state = self._build_tier3_state(tier2_state, cloudfront_info)
        asyncio.run(self.state_manager.save_deployment(final_state))

        console.print(
            f"\n{EMOJI['check']} Tier 3 deployment complete with CloudFront CDN!",
            verbosity="info",
        )
        console.print(f"{EMOJI['info']} CloudFront Domain: {cloudfront_info['cloudfront_domain']}", verbosity="info")

        return final_state

    def _create_cloudfront(
        self,
        config: DeploymentConfig,
        tier2_state: DeploymentState,
    ) -> dict[str, str]:
        """
        Create CloudFront distribution with ALB as custom origin.

        Args:
            config: Deployment configuration
            tier2_state: State from Tier 2 deployment (includes ALB DNS)

        Returns:
            Dict containing CloudFront distribution ID and domain name

        Raises:
            RuntimeError: If CloudFront creation fails
        """
        stack_name = config.stack_name
        caller_reference = f"{stack_name}-{datetime.now(UTC).timestamp()}"

        # Create distribution with ALB as origin
        console.print(f"{EMOJI['info']} Creating CloudFront distribution with ALB origin...", verbosity="debug")

        # For Tier 3, we use default caching (TTL=0) to forward all requests to ALB
        # Users can customize cache behaviors in future iterations
        cf_resp = self.cloudfront_service.create_distribution_with_alb_origin(
            alb_dns_name=tier2_state.alb_dns,
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

        console.print(
            f"{EMOJI['check']} CloudFront distribution created: {distribution_id}",
            verbosity="info",
        )

        return {
            "distribution_id": distribution_id,
            "cloudfront_domain": cloudfront_domain,
        }

    def _wait_for_cloudfront(
        self,
        distribution_id: str,
        max_wait_minutes: int = 40,
    ) -> None:
        """
        Wait for CloudFront distribution to reach 'Deployed' status with progress reporting.

        Args:
            distribution_id: CloudFront distribution ID
            max_wait_minutes: Maximum time to wait in minutes (default: 40 minutes)

        Raises:
            RuntimeError: If distribution doesn't deploy in time
        """
        max_attempts = max_wait_minutes * 2  # Poll every 30 seconds
        delay = 30

        console.print(
            f"{EMOJI['info']} CloudFront deployment typically takes 15-30 minutes...",
            verbosity="info",
        )

        # Call the service's wait method which handles polling
        self.cloudfront_service.wait_for_deployed(
            distribution_id=distribution_id,
            max_attempts=max_attempts,
            delay=delay,
        )

        console.print(
            f"{EMOJI['check']} CloudFront distribution deployed successfully",
            verbosity="info",
        )

    def _build_tier3_state(
        self,
        tier2_state: DeploymentState,
        cloudfront_info: dict[str, str],
    ) -> DeploymentState:
        """
        Build final Tier 3 deployment state with CloudFront information.

        Args:
            tier2_state: State from Tier 2 deployment
            cloudfront_info: CloudFront resource information

        Returns:
            Complete Tier 3 DeploymentState
        """
        # Update n8n URL to use CloudFront domain
        n8n_url = f"http://{cloudfront_info['cloudfront_domain']}:80"

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
            efs_mount_target_ip=tier2_state.efs_mount_target_ip,
            iam_role_name=tier2_state.iam_role_name,
            iam_role_arn=tier2_state.iam_role_arn,
            iam_instance_profile_name=tier2_state.iam_instance_profile_name,
            iam_instance_profile_arn=tier2_state.iam_instance_profile_arn,
            instance_id=tier2_state.instance_id,
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
            cost=tier2_state.cost,
            config=tier2_state.config,
            resource_provenance=resource_provenance,
        )


__all__ = ["Tier3Orchestrator"]
