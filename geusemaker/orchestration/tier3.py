"""Tier 3 deployment orchestrator with CloudFront CDN support."""

from __future__ import annotations

import asyncio
import logging
import time

from geusemaker.infra import AWSClientFactory, StateManager
from geusemaker.models import DeploymentConfig, DeploymentState
from geusemaker.orchestration.errors import OrchestrationError
from geusemaker.orchestration.stages import (
    build_tier3_state,
    create_cloudfront,
    wait_for_cloudfront,
)
from geusemaker.orchestration.tier2 import Tier2Orchestrator
from geusemaker.progress import ProgressCallback
from geusemaker.services import CloudFrontService

LOGGER = logging.getLogger(__name__)


class Tier3Orchestrator(Tier2Orchestrator):
    """Coordinate Tier 3 deployments with CloudFront CDN support."""

    def __init__(
        self,
        client_factory: AWSClientFactory | None = None,
        region: str = "us-east-1",
        state_manager: StateManager | None = None,
        pricing_service=None,
        spot_selector=None,
        on_progress: ProgressCallback | None = None,
    ):
        super().__init__(
            client_factory,
            region,
            state_manager,
            pricing_service=pricing_service,
            spot_selector=spot_selector,
            on_progress=on_progress,
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

        # CloudFront validates the origin's TLS certificate against the origin domain name,
        # and ALB certificates never cover the raw *.elb.amazonaws.com name.  An HTTPS ALB
        # origin therefore requires a custom domain covered by the certificate; failing fast
        # here beats a 30-minute deploy that 502s on every request.
        if config.enable_https and config.alb_certificate_arn and not config.alb_domain_name:
            raise OrchestrationError(
                "Tier 3 HTTPS requires alb_domain_name matching the ALB certificate: CloudFront "
                "cannot validate the certificate against the raw ALB DNS name. Provide "
                "alb_domain_name (plus alb_hosted_zone_id for automatic DNS) or set enable_https=false.",
            )

        # Step 1-10: Execute Tier 2 deployment (VPC, SG, EFS, IAM, EC2, ALB)
        LOGGER.info("Executing Tier 2 deployment steps...")
        tier2_state = super()._deploy_impl(config)

        start_time = self._deploy_start_time or time.monotonic()
        self._check_timeout(start_time, config.rollback_timeout_minutes, "before CloudFront setup")

        # Verify ALB was created (should always be true given enable_alb check above)
        if not tier2_state.alb_dns:
            raise OrchestrationError("Tier 2 deployment did not create ALB. Cannot proceed with CloudFront creation.")

        # Step 11: Create CloudFront distribution with ALB as origin
        self._emit_progress("cdn", "Creating CloudFront distribution")
        LOGGER.info("Creating CloudFront distribution...")
        cloudfront_info = self._create_cloudfront(config, tier2_state)

        # Step 12: Wait for CloudFront to deploy (15-30 minutes typical)
        self._emit_progress(
            "cdn",
            "Waiting for CloudFront deployment",
            resource_id=cloudfront_info["distribution_id"],
        )
        LOGGER.info("Waiting for CloudFront deployment (this can take 15-30 minutes)...")
        self._wait_for_cloudfront(
            cloudfront_info["distribution_id"],
            max_wait_minutes=config.rollback_timeout_minutes,
        )

        # Step 12a: Ensure n8n knows its public URL when behind CloudFront -> ALB.
        # CloudFront's domain is only known after creation, so patch runtime.env post-deploy.
        # When a custom domain is configured, Tier 2 already set it as the public URL and
        # Route 53 points it at the ALB -- overwriting it with the ephemeral CloudFront
        # domain would break webhook/OAuth URLs users registered against their domain.
        if not config.alb_domain_name:
            self._best_effort_configure_n8n_public_url(
                instance_id=tier2_state.instance_id,
                host=cloudfront_info["cloudfront_domain"],
                protocol="https",  # CloudFront is always reachable via HTTPS
                proxy_hops=2,  # CloudFront -> ALB
            )
        else:
            LOGGER.info(f"Keeping n8n public URL on custom domain {config.alb_domain_name}")

        # Step 13: Build final Tier 3 state with CloudFront info
        final_state = self._build_tier3_state(tier2_state, cloudfront_info)
        asyncio.run(self.state_manager.save_deployment(final_state))

        LOGGER.info("Tier 3 deployment complete with CloudFront CDN!")
        LOGGER.info(f"CloudFront Domain: {cloudfront_info['cloudfront_domain']}")

        return final_state

    def _create_cloudfront(
        self,
        config: DeploymentConfig,
        tier2_state: DeploymentState,
    ) -> dict[str, str]:
        """Create CloudFront distribution (delegates to stages.cloudfront.create_cloudfront)."""
        return create_cloudfront(self.cloudfront_service, config, tier2_state)

    def _wait_for_cloudfront(
        self,
        distribution_id: str,
        max_wait_minutes: int = 40,
    ) -> None:
        """Wait for CloudFront deployment (delegates to stages.cloudfront.wait_for_cloudfront)."""
        wait_for_cloudfront(self.cloudfront_service, distribution_id, max_wait_minutes)

    def _build_tier3_state(
        self,
        tier2_state: DeploymentState,
        cloudfront_info: dict[str, str],
    ) -> DeploymentState:
        """Build final Tier 3 deployment state (delegates to stages.cloudfront.build_tier3_state)."""
        return build_tier3_state(tier2_state, cloudfront_info)


__all__ = ["Tier3Orchestrator"]
