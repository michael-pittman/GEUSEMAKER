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
from geusemaker.services.route53 import Route53Service
from geusemaker.services.ssm import SSMService


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
    ):
        super().__init__(
            client_factory,
            region,
            state_manager,
            pricing_service=pricing_service,
            spot_selector=spot_selector,
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
        console.print(f"{EMOJI['info']} Executing Tier 1 deployment steps...", verbosity="info")
        tier1_state = super()._deploy_impl(config)

        # If ALB not enabled, return Tier 1 state
        if not config.enable_alb:
            console.print(
                f"{EMOJI['info']} ALB not enabled for this deployment. Skipping Tier 2 resources.",
                verbosity="info",
            )
            return tier1_state

        # Tier 2 HTTPS is terminated at the ALB, which requires an ACM certificate.
        # Without a certificate ARN we can still serve HTTP, so degrade instead of failing
        # (pre-HTTPS configs set enable_https=True by default).
        if config.enable_https and not config.alb_certificate_arn:
            console.print(
                f"{EMOJI['warning']} No ACM certificate ARN available; ALB will serve HTTP only. "
                "Provide alb_certificate_arn (regional ACM cert) to enable HTTPS.",
                verbosity="warning",
            )

        self._check_timeout(start_time, config.rollback_timeout_minutes, "before ALB setup")

        # Step 8: Wait for UserData to complete before registering with ALB
        console.print(f"{EMOJI['info']} Waiting for instance initialization to complete...", verbosity="info")

        ssm_ready = False
        try:
            console.print(f"{EMOJI['info']} Waiting for SSM agent to be ready...", verbosity="debug")
            ssm_ready = self.ssm_service.wait_for_ssm_agent(
                tier1_state.instance_id,
                timeout_seconds=120,  # 2 minutes max for SSM agent
            )
        except Exception as exc:  # noqa: BLE001
            console.print(
                f"{EMOJI['warning']} SSM check failed ({exc}); proceeding with ALB registration...",
                verbosity="warning",
            )

        if not ssm_ready:
            console.print(
                f"{EMOJI['warning']} SSM agent not ready, proceeding with ALB registration...",
                verbosity="warning",
            )
        else:
            try:
                userdata_status = self.ssm_service.wait_for_userdata_completion(
                    tier1_state.instance_id,
                    timeout_seconds=600,  # 10 minutes max
                    poll_interval=15.0,  # Check every 15 seconds
                )
            except Exception as exc:  # noqa: BLE001
                console.print(
                    f"{EMOJI['warning']} UserData completion check failed ({exc}); proceeding with ALB registration...",
                    verbosity="warning",
                )
                userdata_status = "timeout"

            if userdata_status == "error":
                raise OrchestrationError("UserData script failed. Check instance logs for details.")
            if userdata_status == "timeout":
                console.print(
                    f"{EMOJI['warning']} UserData completion timeout, proceeding with ALB registration anyway...",
                    verbosity="warning",
                )
            else:
                console.print(f"{EMOJI['check']} Instance initialization complete", verbosity="info")

        # Step 9: Create ALB infrastructure
        console.print(f"\n{EMOJI['rocket']} Creating Application Load Balancer...", verbosity="info")
        alb_info = self._create_alb(config, tier1_state)

        # Step 9b: Save state with ALB info immediately so rollback can clean it up
        # This is critical -- if health checks or registration fail, the ALB
        # must be recorded in state so DestructionService can delete it.
        partial_tier2_state = self._build_tier2_state(tier1_state, alb_info)
        # Use a valid in-progress status; "deploying" is not part of the persisted schema.
        partial_tier2_state.status = "creating"
        asyncio.run(self.state_manager.save_deployment(partial_tier2_state))

        # Step 10: Register EC2 instance with target group
        console.print(f"{EMOJI['info']} Registering EC2 instance with target group...", verbosity="info")
        self._register_instance(tier1_state.instance_id, alb_info)

        # Step 11: Wait for instance to become healthy
        console.print(f"{EMOJI['check']} Waiting for target health checks to pass...", verbosity="info")
        self._wait_for_healthy_targets(alb_info["target_group_arn"], [tier1_state.instance_id])

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
                console.print(
                    f"{EMOJI['info']} Creating Route 53 ALIAS record for {config.alb_domain_name}...",
                    verbosity="info",
                )
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
                console.print(
                    f"{EMOJI['warning']} ALB hosted zone id missing; skipping Route 53 domain binding.",
                    verbosity="warning",
                )

        # Step 12: Build final Tier 2 state with ALB info
        final_state = self._build_tier2_state(tier1_state, alb_info)
        asyncio.run(self.state_manager.save_deployment(final_state))

        console.print(
            f"\n{EMOJI['check']} Tier 2 deployment complete with ALB!",
            verbosity="info",
        )
        console.print(f"{EMOJI['info']} ALB DNS: {alb_info['alb_dns']}", verbosity="info")

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
            url = f"{protocol}://{host}"
            env_updates = {
                "N8N_HOST": host,
                "N8N_PROTOCOL": protocol,
                "WEBHOOK_URL": f"{url}/",
                "N8N_EDITOR_BASE_URL": url,
                "N8N_SECURE_COOKIE": "true" if protocol == "https" else "false",
                "N8N_PROXY_HOPS": str(proxy_hops),
            }

            # Prefer runtime bundle location when present.
            # UserData uses COMPOSE_FILE_PATH in /root (no bundle) or /opt/geusemaker/runtime (bundle).
            cmd_lines = [
                # SSM runs scripts with /bin/sh (dash on Ubuntu) unless a shebang says
                # otherwise; the script below uses bashisms (pipefail, set -a).
                "#!/bin/bash",
                "set -euo pipefail",
                'if [ -f /opt/geusemaker/runtime/runtime.env ]; then ENV_FILE="/opt/geusemaker/runtime/runtime.env"; COMPOSE_FILE="/opt/geusemaker/runtime/docker-compose.yml"; '
                'else ENV_FILE="/root/runtime.env"; COMPOSE_FILE="/root/docker-compose.yml"; fi',
                'if [ ! -f "$ENV_FILE" ]; then echo "runtime.env not found at $ENV_FILE" >&2; exit 2; fi',
                'TMP="$(mktemp)"',
                # Drop existing keys then append new values to avoid partial/duplicate updates.
                r'grep -vE "^(N8N_HOST|N8N_PROTOCOL|WEBHOOK_URL|N8N_EDITOR_BASE_URL|N8N_SECURE_COOKIE|N8N_PROXY_HOPS)=" "$ENV_FILE" > "$TMP" || true',
            ]
            for k, v in env_updates.items():
                # Basic shell-safe (no spaces expected in these values).
                cmd_lines.append(f'printf "%s\\n" "{k}={v}" >> "$TMP"')
            cmd_lines += [
                'mv "$TMP" "$ENV_FILE"',
                'cd "$(dirname "$COMPOSE_FILE")"',
                # Export runtime.env into the shell: compose interpolation (e.g.
                # ${POSTGRES_PASSWORD:?...}) and the compose "environment:" entries read the
                # process env, not env_file, so without this the restart fails or keeps defaults.
                "set -a; while IFS='=' read -r k v; do "
                '[ -z "$k" ] && continue; case "$k" in "#"*) continue;; esac; export "$k=$v"; '
                'done < "$ENV_FILE"; set +a',
                # Recreate n8n so the updated env takes effect.
                'if command -v docker-compose >/dev/null 2>&1; then docker-compose -f "$COMPOSE_FILE" up -d --force-recreate n8n; '
                'else docker compose -f "$COMPOSE_FILE" up -d --force-recreate n8n; fi',
            ]

            result = self.ssm_service.run_shell_script(
                instance_id=instance_id,
                commands=cmd_lines,
                comment="Configure n8n public URL env (WEBHOOK_URL/N8N_EDITOR_BASE_URL)",
                timeout_seconds=180,
            )
            if result.get("Status") != "Success":
                console.print(
                    f"{EMOJI['warning']} Failed to configure n8n public URL via SSM (status={result.get('Status')}).",
                    verbosity="warning",
                )
        except Exception as exc:  # noqa: BLE001
            console.print(
                f"{EMOJI['warning']} Best-effort n8n public URL configuration failed: {exc}",
                verbosity="warning",
            )

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
            subnets=self._select_alb_subnets(tier1_state),
            security_groups=[tier1_state.security_group_id],
            scheme="internet-facing",
            tags=tags,
        )
        alb_arn = alb_resp["LoadBalancers"][0]["LoadBalancerArn"]
        alb_dns = alb_resp["LoadBalancers"][0]["DNSName"]
        alb_zone_id = alb_resp["LoadBalancers"][0].get("CanonicalHostedZoneId")

        # Create target group
        console.print(f"{EMOJI['info']} Creating target group...", verbosity="debug")
        tg_resp = self.alb_service.create_target_group(
            name=f"{stack_name}-tg",
            vpc_id=tier1_state.vpc_id,
            # NGINX reverse proxy on the host handles path routing to all services.
            port=self._NGINX_PORT,
            protocol="HTTP",
            health_check_path="/healthz",
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
            "alb_zone_id": alb_zone_id,
            "target_group_arn": target_group_arn,
            "listener_arn": listener_arn,
            "https_listener_arn": https_listener_arn,
            "https_enabled": https_enabled,
        }

    def _select_alb_subnets(self, tier1_state: DeploymentState) -> list[str]:
        """Pick two subnets for the internet-facing ALB, preferring public ones in distinct AZs.

        tier1 state stores public and private subnet ids in one list, so blindly
        slicing can hand the ALB a private subnet or two subnets in the same AZ
        (both rejected or broken).  Falls back to the first two ids when subnet
        details cannot be fetched (e.g. stub services in tests).
        """
        subnet_ids = tier1_state.subnet_ids
        describe = getattr(self.ec2_service, "describe_subnets", None)
        if describe is None:
            return subnet_ids[:2]
        try:
            subnets = describe(subnet_ids)
        except RuntimeError as exc:
            console.print(
                f"{EMOJI['warning']} Could not inspect subnets for ALB placement ({exc}); using first two.",
                verbosity="debug",
            )
            return subnet_ids[:2]

        # Public subnets first, then one subnet per AZ.
        ordered = sorted(subnets, key=lambda s: not s.get("MapPublicIpOnLaunch", False))
        chosen: list[str] = []
        seen_azs: set[str] = set()
        for subnet in ordered:
            az = subnet.get("AvailabilityZone")
            if not az or az in seen_azs:
                continue
            chosen.append(subnet["SubnetId"])
            seen_azs.add(az)
            if len(chosen) == 2:
                return chosen
        return subnet_ids[:2]

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
        console.print(f"{EMOJI['check']} Instance {instance_id} registered", verbosity="debug")

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
            # Prefer user-provided custom domain when available.
            domain = tier1_state.config.alb_domain_name or alb_info["alb_dns"]
            n8n_url = f"https://{domain}"
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
            nginx_proxy_enabled=True,  # NGINX on host handles path routing; ALB terminates TLS
            cost=tier1_state.cost,
            config=tier1_state.config,
            resource_provenance=resource_provenance,
        )


__all__ = ["Tier2Orchestrator"]
