"""Tier 2 deployment orchestrator with ALB support."""

from __future__ import annotations

import asyncio
import logging
import time

from geusemaker.infra import AWSClientFactory, StateManager
from geusemaker.models import DeploymentConfig, DeploymentState
from geusemaker.orchestration.errors import OrchestrationError
from geusemaker.orchestration.stages import (
    build_n8n_url_patch_commands,
    build_tier2_state,
    create_alb,
    select_alb_subnets,
)
from geusemaker.orchestration.tier1 import Tier1Orchestrator
from geusemaker.progress import ProgressCallback
from geusemaker.services.alb import ALBService
from geusemaker.services.route53 import Route53Service
from geusemaker.services.ssm import SSMService

LOGGER = logging.getLogger(__name__)


class Tier2Orchestrator(Tier1Orchestrator):
    """Coordinate Tier 2 deployments with ALB support."""

    # NGINX reverse proxy port on the EC2 host.  All tiers now run NGINX for
    # path-based routing; the ALB target group forwards to this port.
    _NGINX_PORT = 80

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
        self.alb_service = ALBService(self.client_factory, region=region)
        # Used to gate ALB registration until instance init completes (best-effort; may be stubbed in tests).
        self.ssm_service = SSMService(self.client_factory, region=region)

    def _deploy_impl(self, config: DeploymentConfig) -> DeploymentState:
        """
        Internal implementation of Tier2 deployment with ALB.

        Args:
            config: Deployment configuration

        Returns:
            DeploymentState with all resource IDs and metadata

        Raises:
            OrchestrationError: If deployment validation or resource creation fails
        """
        if config.tier not in ("automation", "dev", "gpu"):
            raise OrchestrationError(
                f"Tier2Orchestrator supports 'dev', 'automation', and 'gpu' tiers, got: {config.tier}"
            )

        start_time = self._deploy_start_time or time.monotonic()

        # Step 1-7: Execute Tier 1 deployment (VPC, SG, EFS, IAM, EC2)
        LOGGER.info("Executing Tier 1 deployment steps...")
        tier1_state = super()._deploy_impl(config)

        # If ALB not enabled, return Tier 1 state
        if not config.enable_alb:
            LOGGER.info("ALB not enabled for this deployment. Skipping Tier 2 resources.")
            return tier1_state

        # Tier 2 HTTPS is terminated at the ALB, which requires an ACM certificate.
        # Without a certificate ARN we can still serve HTTP, so degrade instead of failing
        # (pre-HTTPS configs set enable_https=True by default).
        if config.enable_https and not config.alb_certificate_arn:
            LOGGER.warning(
                "No ACM certificate ARN available; ALB will serve HTTP only. "
                "Provide alb_certificate_arn (regional ACM cert) to enable HTTPS."
            )

        self._check_timeout(start_time, config.rollback_timeout_minutes, "before ALB setup")

        # Step 8: Wait for UserData to complete before registering with ALB
        self._emit_progress("userdata", "Waiting for instance initialization to complete")
        LOGGER.info("Waiting for instance initialization to complete...")

        ssm_ready = False
        try:
            LOGGER.debug("Waiting for SSM agent to be ready...")
            ssm_ready = self.ssm_service.wait_for_ssm_agent(
                tier1_state.instance_id,
                timeout_seconds=120,  # 2 minutes max for SSM agent
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning(f"SSM check failed ({exc}); proceeding with ALB registration...")

        if not ssm_ready:
            LOGGER.warning("SSM agent not ready, proceeding with ALB registration...")
        else:
            try:
                userdata_status = self.ssm_service.wait_for_userdata_completion(
                    tier1_state.instance_id,
                    timeout_seconds=600,  # 10 minutes max
                    poll_interval=15.0,  # Check every 15 seconds
                )
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning(f"UserData completion check failed ({exc}); proceeding with ALB registration...")
                userdata_status = "timeout"

            if userdata_status == "error":
                raise OrchestrationError("UserData script failed. Check instance logs for details.")
            if userdata_status == "timeout":
                LOGGER.warning("UserData completion timeout, proceeding with ALB registration anyway...")
            else:
                LOGGER.info("Instance initialization complete")

        # Step 9: Create ALB infrastructure
        self._emit_progress("alb", "Creating Application Load Balancer")
        LOGGER.info("Creating Application Load Balancer...")
        alb_info = self._create_alb(config, tier1_state)
        self._emit_progress("alb", f"ALB created: {alb_info['alb_dns']}", resource_id=alb_info["alb_arn"])

        # Step 9b: Save state with ALB info immediately so rollback can clean it up
        # This is critical -- if health checks or registration fail, the ALB
        # must be recorded in state so DestructionService can delete it.
        partial_tier2_state = self._build_tier2_state(tier1_state, alb_info)
        # Use a valid in-progress status; "deploying" is not part of the persisted schema.
        partial_tier2_state.status = "creating"
        asyncio.run(self.state_manager.save_deployment(partial_tier2_state))

        # Step 10: Register EC2 instance with target group
        LOGGER.info("Registering EC2 instance with target group...")
        self._register_instance(tier1_state.instance_id, alb_info)
        if tier1_state.auto_scaling_group_name:
            self.spot_automation_service.attach_target_group(
                tier1_state.auto_scaling_group_name,
                alb_info["target_group_arn"],
            )
            LOGGER.info("Auto Scaling replacements will register with the target group automatically")

        # Step 11: Wait for instance to become healthy
        self._emit_progress("health", "Waiting for target health checks to pass")
        LOGGER.info("Waiting for target health checks to pass...")
        self._wait_for_healthy_targets(alb_info["target_group_arn"], [tier1_state.instance_id])

        if tier1_state.auto_scaling_group_name:
            runtime_check = self.ssm_service.run_shell_script(
                instance_id=tier1_state.instance_id,
                commands=[
                    "systemctl is-active --quiet geusemaker-spot-guard.service",
                    "test -f /var/lib/geusemaker/spot-lease-acquired",
                ],
                comment="Verify GeuseMaker production Spot protection",
                timeout_seconds=60,
            )
            if runtime_check.get("Status") != "Success":
                raise OrchestrationError(
                    "Production Spot guard verification failed; refusing to report an unprotected deployment"
                )
            self.spot_automation_service.verify(
                asg_name=tier1_state.auto_scaling_group_name,
                instance_id=tier1_state.instance_id,
                lease_table_name=tier1_state.spot_lease_table_name or "",
                lifecycle_hook_names=tier1_state.spot_lifecycle_hook_names,
                event_rule_names=tier1_state.spot_event_rule_names,
            )
            LOGGER.info("Production Spot protection verified")

        # Step 11a: Ensure n8n knows its public URL when behind an ALB.
        # UserData runs before the ALB exists, so Tier 2 must patch runtime.env after ALB DNS/domain is known.
        self._best_effort_configure_n8n_public_url(
            instance_id=tier1_state.instance_id,
            host=(config.alb_domain_name or alb_info["alb_dns"]),
            protocol=("https" if alb_info.get("https_enabled") else "http"),
            proxy_hops=(2 if config.enable_cdn else 1),
        )

        # Step 11b: Bind custom domain (Route 53 ALIAS) if provided.
        # Note: The ACM validation record was created earlier; this creates the user-facing A/AAAA.
        if config.enable_https and config.alb_domain_name and config.alb_hosted_zone_id:
            alb_zone_id = alb_info.get("alb_zone_id")
            if alb_zone_id:
                # ACM/Route 53 work is folded into the alb stage for the timeline.
                self._emit_progress("alb", f"Creating Route 53 alias for {config.alb_domain_name}")
                LOGGER.info(f"Creating Route 53 ALIAS record for {config.alb_domain_name}...")
                r53 = Route53Service(self.client_factory)
                change_a = r53.upsert_alias(
                    hosted_zone_id=config.alb_hosted_zone_id,
                    record_name=config.alb_domain_name,
                    dns_name=alb_info["alb_dns"],
                    target_hosted_zone_id=alb_zone_id,
                    record_type="A",
                )
                if change_a:
                    r53.wait_for_change(change_a)
                change_aaaa = r53.upsert_alias(
                    hosted_zone_id=config.alb_hosted_zone_id,
                    record_name=config.alb_domain_name,
                    dns_name=alb_info["alb_dns"],
                    target_hosted_zone_id=alb_zone_id,
                    record_type="AAAA",
                )
                if change_aaaa:
                    r53.wait_for_change(change_aaaa)
            else:
                LOGGER.warning("ALB hosted zone id missing; skipping Route 53 domain binding.")

        # Step 12: Build final Tier 2 state with ALB info
        final_state = self._build_tier2_state(tier1_state, alb_info)
        asyncio.run(self.state_manager.save_deployment(final_state))

        LOGGER.info("Tier 2 deployment complete with ALB!")
        LOGGER.info(f"ALB DNS: {alb_info['alb_dns']}")

        return final_state

    def _best_effort_configure_n8n_public_url(
        self,
        instance_id: str,
        host: str,
        protocol: str,
        proxy_hops: int,
    ) -> None:
        """
        Patch runtime.env on the instance so n8n generates correct webhook URLs behind proxies (ALB/CDN).

        Notes:
        - n8n uses WEBHOOK_URL and N8N_EDITOR_BASE_URL.
        - This is best-effort: deployment should not fail if SSM is unavailable.
        """
        try:
            cmd_lines = build_n8n_url_patch_commands(host, protocol, proxy_hops)

            result = self.ssm_service.run_shell_script(
                instance_id=instance_id,
                commands=cmd_lines,
                comment="Configure n8n public URL env (WEBHOOK_URL/N8N_EDITOR_BASE_URL)",
                timeout_seconds=180,
            )
            if result.get("Status") != "Success":
                LOGGER.warning(f"Failed to configure n8n public URL via SSM (status={result.get('Status')}).")
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning(f"Best-effort n8n public URL configuration failed: {exc}")

    def _create_alb(
        self,
        config: DeploymentConfig,
        tier1_state: DeploymentState,
    ) -> dict[str, str]:
        """
        Create ALB with target group and listener (delegates to stages.alb).

        Args:
            config: Deployment configuration
            tier1_state: State from Tier 1 deployment

        Returns:
            Dict containing ALB ARN, DNS, target group ARN, listener ARN

        Raises:
            RuntimeError: If ALB creation fails
        """
        return create_alb(
            self.alb_service,
            config,
            tier1_state,
            self._select_alb_subnets(tier1_state),
            self._NGINX_PORT,
        )

    def _select_alb_subnets(self, tier1_state: DeploymentState) -> list[str]:
        """Pick ALB subnets (delegates to stages.alb.select_alb_subnets).

        The storage subnet is co-located with compute (same AZ as the selected
        spot instance), so it identifies the AZ the ALB should prefer including.
        """
        return select_alb_subnets(
            self.ec2_service,
            tier1_state,
            preferred_subnet_id=tier1_state.storage_subnet_id,
        )

    def _register_instance(
        self,
        instance_id: str,
        alb_info: dict[str, str],
    ) -> None:
        """
        Register EC2 instance with ALB target group.

        Args:
            instance_id: EC2 instance ID to register
            alb_info: ALB information dict with target_group_arn

        Raises:
            RuntimeError: If registration fails
        """
        self.alb_service.register_targets(
            target_group_arn=alb_info["target_group_arn"],
            instance_ids=[instance_id],
        )
        LOGGER.debug(f"Instance {instance_id} registered")

    def _wait_for_healthy_targets(
        self,
        target_group_arn: str,
        instance_ids: list[str],
        max_wait_seconds: int = 600,  # Increased to 10 minutes to allow for UserData completion
    ) -> None:
        """
        Wait for registered targets to pass health checks.

        Args:
            target_group_arn: Target group ARN
            instance_ids: List of instance IDs to monitor
            max_wait_seconds: Maximum time to wait (default: 5 minutes)

        Raises:
            RuntimeError: If targets don't become healthy in time
        """
        max_attempts = max_wait_seconds // 5
        self.alb_service.wait_for_healthy(
            target_group_arn=target_group_arn,
            instance_ids=instance_ids,
            max_attempts=max_attempts,
            delay=5,
        )
        LOGGER.info("All targets healthy in target group")

    def _build_tier2_state(
        self,
        tier1_state: DeploymentState,
        alb_info: dict[str, str],
    ) -> DeploymentState:
        """Build final Tier 2 deployment state (delegates to stages.alb.build_tier2_state)."""
        return build_tier2_state(tier1_state, alb_info)


__all__ = ["Tier2Orchestrator"]
