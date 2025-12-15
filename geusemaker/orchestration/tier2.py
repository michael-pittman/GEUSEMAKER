"""Tier 2 deployment orchestrator with ALB support."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

from geusemaker.cli import console
from geusemaker.cli.branding import EMOJI
from geusemaker.infra import AWSClientFactory, StateManager
from geusemaker.models import DeploymentConfig, DeploymentState
from geusemaker.orchestration.errors import OrchestrationError
from geusemaker.orchestration.tier1 import Tier1Orchestrator
from geusemaker.services.alb import ALBService


class Tier2Orchestrator(Tier1Orchestrator):
    """Coordinate Tier 2 deployments with ALB support."""

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
        self.alb_service = ALBService(self.client_factory, region=region)

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
        console.print(f"{EMOJI['info']} Executing Tier 1 deployment steps...", verbosity="info")
        tier1_state = super()._deploy_impl(config)

        # If ALB not enabled, return Tier 1 state
        if not config.enable_alb:
            console.print(
                f"{EMOJI['info']} ALB not enabled for this deployment. Skipping Tier 2 resources.",
                verbosity="info",
            )
            return tier1_state

        self._check_timeout(start_time, config.rollback_timeout_minutes, "before ALB setup")

        # Step 8: Create ALB infrastructure
        console.print(f"\n{EMOJI['rocket']} Creating Application Load Balancer...", verbosity="info")
        alb_info = self._create_alb(config, tier1_state)

        # Step 9: Register EC2 instance with target group
        console.print(f"{EMOJI['info']} Registering EC2 instance with target group...", verbosity="info")
        self._register_instance(tier1_state.instance_id, alb_info)

        # Step 10: Wait for instance to become healthy
        console.print(f"{EMOJI['check']} Waiting for target health checks to pass...", verbosity="info")
        self._wait_for_healthy_targets(alb_info["target_group_arn"], [tier1_state.instance_id])

        # Step 11: Build final Tier 2 state with ALB info
        final_state = self._build_tier2_state(tier1_state, alb_info)
        asyncio.run(self.state_manager.save_deployment(final_state))

        console.print(
            f"\n{EMOJI['check']} Tier 2 deployment complete with ALB!",
            verbosity="info",
        )
        console.print(f"{EMOJI['info']} ALB DNS: {alb_info['alb_dns']}", verbosity="info")

        return final_state

    def _create_alb(
        self,
        config: DeploymentConfig,
        tier1_state: DeploymentState,
    ) -> dict[str, str]:
        """
        Create ALB with target group and listener.

        Args:
            config: Deployment configuration
            tier1_state: State from Tier 1 deployment

        Returns:
            Dict containing ALB ARN, DNS, target group ARN, listener ARN

        Raises:
            RuntimeError: If ALB creation fails
        """
        stack_name = config.stack_name
        tags = [
            {"Key": "Name", "Value": f"{stack_name}-alb"},
            {"Key": "Stack", "Value": stack_name},
            {"Key": "Tier", "Value": config.tier},
            {"Key": "ManagedBy", "Value": "GeuseMaker"},
        ]

        # Create ALB (requires at least 2 subnets in different AZs)
        if len(tier1_state.subnet_ids) < 2:
            raise OrchestrationError(
                f"ALB requires at least 2 subnets in different Availability Zones. "
                f"Found {len(tier1_state.subnet_ids)} subnet(s)."
            )

        console.print(f"{EMOJI['info']} Creating load balancer...", verbosity="debug")
        alb_resp = self.alb_service.create_alb(
            name=f"{stack_name}-alb",
            subnets=tier1_state.subnet_ids[:2],  # Use first 2 subnets
            security_groups=[tier1_state.security_group_id],
            scheme="internet-facing",
            tags=tags,
        )
        alb_arn = alb_resp["LoadBalancers"][0]["LoadBalancerArn"]
        alb_dns = alb_resp["LoadBalancers"][0]["DNSName"]

        # Create target group
        console.print(f"{EMOJI['info']} Creating target group...", verbosity="debug")
        tg_resp = self.alb_service.create_target_group(
            name=f"{stack_name}-tg",
            vpc_id=tier1_state.vpc_id,
            port=80,
            protocol="HTTP",
            health_check_path="/",
            health_check_interval=30,
            health_check_timeout=5,
            healthy_threshold=2,
            unhealthy_threshold=3,
            tags=tags,
        )
        target_group_arn = tg_resp["TargetGroups"][0]["TargetGroupArn"]

        # Create listeners (HTTP and/or HTTPS based on configuration)
        https_enabled = config.enable_https and config.alb_certificate_arn is not None
        listener_arn = None
        https_listener_arn = None

        if https_enabled:
            # Create HTTPS listener with ACM certificate
            console.print(f"{EMOJI['info']} Creating HTTPS listener (port 443)...", verbosity="debug")
            https_resp = self.alb_service.create_https_listener(
                load_balancer_arn=alb_arn,
                target_group_arn=target_group_arn,
                certificate_arn=config.alb_certificate_arn,
                port=443,
            )
            https_listener_arn = https_resp["Listeners"][0]["ListenerArn"]

            if config.force_https_redirect:
                # Create HTTP→HTTPS redirect listener
                console.print(f"{EMOJI['info']} Creating HTTP→HTTPS redirect listener...", verbosity="debug")
                redirect_resp = self.alb_service.create_redirect_listener(
                    load_balancer_arn=alb_arn,
                    port=80,
                )
                listener_arn = redirect_resp["Listeners"][0]["ListenerArn"]
                console.print(f"{EMOJI['check']} HTTPS enabled with HTTP redirect", verbosity="info")
            else:
                # Keep HTTP listener alongside HTTPS
                console.print(f"{EMOJI['info']} Creating HTTP listener (port 80)...", verbosity="debug")
                listener_resp = self.alb_service.create_listener(
                    load_balancer_arn=alb_arn,
                    target_group_arn=target_group_arn,
                    port=80,
                    protocol="HTTP",
                )
                listener_arn = listener_resp["Listeners"][0]["ListenerArn"]
                console.print(f"{EMOJI['check']} HTTPS enabled with HTTP listener", verbosity="info")
        else:
            # HTTP-only (no certificate or HTTPS disabled)
            console.print(f"{EMOJI['info']} Creating HTTP listener...", verbosity="debug")
            listener_resp = self.alb_service.create_listener(
                load_balancer_arn=alb_arn,
                target_group_arn=target_group_arn,
                port=80,
                protocol="HTTP",
            )
            listener_arn = listener_resp["Listeners"][0]["ListenerArn"]

        console.print(f"{EMOJI['check']} ALB created: {alb_dns}", verbosity="info")

        return {
            "alb_arn": alb_arn,
            "alb_dns": alb_dns,
            "target_group_arn": target_group_arn,
            "listener_arn": listener_arn,
            "https_listener_arn": https_listener_arn,
            "https_enabled": https_enabled,
        }

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
            port=80,
        )
        console.print(f"{EMOJI['check']} Instance {instance_id} registered", verbosity="debug")

    def _wait_for_healthy_targets(
        self,
        target_group_arn: str,
        instance_ids: list[str],
        max_wait_seconds: int = 300,
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
        console.print(
            f"{EMOJI['check']} All targets healthy in target group",
            verbosity="info",
        )

    def _build_tier2_state(
        self,
        tier1_state: DeploymentState,
        alb_info: dict[str, str],
    ) -> DeploymentState:
        """
        Build final Tier 2 deployment state with ALB information.

        Args:
            tier1_state: State from Tier 1 deployment
            alb_info: ALB resource information

        Returns:
            Complete Tier 2 DeploymentState
        """
        # Build n8n URL and HTTPS endpoint based on HTTPS configuration
        https_enabled = alb_info.get("https_enabled", False)
        if https_enabled:
            n8n_url = f"https://{alb_info['alb_dns']}"
            https_endpoint = n8n_url
        else:
            n8n_url = f"http://{alb_info['alb_dns']}:80"
            https_endpoint = None

        # Update resource provenance
        resource_provenance = tier1_state.resource_provenance.copy()
        resource_provenance.update(
            {
                "alb": "created",
                "target_group": "created",
                "listener": "created",
            }
        )
        if https_enabled:
            resource_provenance["https_listener"] = "created"

        return DeploymentState(
            stack_name=tier1_state.stack_name,
            status="running",
            created_at=tier1_state.created_at,
            updated_at=datetime.now(UTC),
            vpc_id=tier1_state.vpc_id,
            subnet_ids=tier1_state.subnet_ids,
            storage_subnet_id=tier1_state.storage_subnet_id,
            security_group_id=tier1_state.security_group_id,
            efs_id=tier1_state.efs_id,
            efs_mount_target_id=tier1_state.efs_mount_target_id,
            efs_mount_target_ip=tier1_state.efs_mount_target_ip,
            iam_role_name=tier1_state.iam_role_name,
            iam_role_arn=tier1_state.iam_role_arn,
            iam_instance_profile_name=tier1_state.iam_instance_profile_name,
            iam_instance_profile_arn=tier1_state.iam_instance_profile_arn,
            instance_id=tier1_state.instance_id,
            keypair_name=tier1_state.keypair_name,
            public_ip=tier1_state.public_ip,
            private_ip=tier1_state.private_ip,
            # Tier 2 ALB fields
            alb_arn=alb_info["alb_arn"],
            alb_dns=alb_info["alb_dns"],
            target_group_arn=alb_info["target_group_arn"],
            n8n_url=n8n_url,
            # HTTPS/TLS fields
            https_enabled=https_enabled,
            https_endpoint=https_endpoint,
            certificate_arn=tier1_state.config.alb_certificate_arn if https_enabled else None,
            nginx_proxy_enabled=False,  # Tier 2 uses ALB, not NGINX proxy
            cost=tier1_state.cost,
            config=tier1_state.config,
            resource_provenance=resource_provenance,
        )


__all__ = ["Tier2Orchestrator"]
