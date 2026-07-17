"""Application Load Balancer stage helpers for Tier2 deployments.

Pure, stateless logic extracted from ``Tier2Orchestrator``'s private methods
(``_create_alb``, ``_select_alb_subnets``, ``_build_tier2_state`` and the
``runtime.env`` patch-script builder used by
``_best_effort_configure_n8n_public_url``). Service objects and resource ids are
passed explicitly rather than via ``self`` so the coordinator stays a thin
sequencer and the bulk logic is unit-testable in isolation.

No module here imports ``geusemaker.cli`` — presentation depends on
orchestration, never the reverse (enforced by the import-direction guard test).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from geusemaker.models import DeploymentConfig, DeploymentState
from geusemaker.orchestration.errors import OrchestrationError
from geusemaker.services.alb import ALBService

LOGGER = logging.getLogger(__name__)


def select_alb_subnets(ec2_service: Any, tier1_state: DeploymentState) -> list[str]:
    """Pick two subnets for the internet-facing ALB, preferring public ones in distinct AZs.

    tier1 state stores public and private subnet ids in one list, so blindly
    slicing can hand the ALB a private subnet or two subnets in the same AZ
    (both rejected or broken).  Falls back to the first two ids when subnet
    details cannot be fetched (e.g. stub services in tests).
    """
    subnet_ids = tier1_state.subnet_ids
    describe = getattr(ec2_service, "describe_subnets", None)
    if describe is None:
        return subnet_ids[:2]
    try:
        subnets = describe(subnet_ids)
    except RuntimeError as exc:
        LOGGER.debug(f"Could not inspect subnets for ALB placement ({exc}); using first two.")
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


def create_alb(
    alb_service: ALBService,
    config: DeploymentConfig,
    tier1_state: DeploymentState,
    subnets: list[str],
    nginx_port: int,
) -> dict[str, Any]:
    """Create the ALB, target group and listener(s), returning resource ids.

    ``subnets`` is the pre-selected subnet list (see :func:`select_alb_subnets`);
    ``nginx_port`` is the host NGINX reverse-proxy port the target group forwards
    to. Raises ``OrchestrationError`` when fewer than two subnets are available.
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

    LOGGER.debug("Creating load balancer...")
    alb_resp = alb_service.create_alb(
        name=f"{stack_name}-alb",
        subnets=subnets,
        security_groups=[tier1_state.security_group_id],
        scheme="internet-facing",
        tags=tags,
    )
    alb_arn = alb_resp["LoadBalancers"][0]["LoadBalancerArn"]
    alb_dns = alb_resp["LoadBalancers"][0]["DNSName"]
    alb_zone_id = alb_resp["LoadBalancers"][0].get("CanonicalHostedZoneId")

    # Create target group
    LOGGER.debug("Creating target group...")
    tg_resp = alb_service.create_target_group(
        name=f"{stack_name}-tg",
        vpc_id=tier1_state.vpc_id,
        # NGINX reverse proxy on the host handles path routing to all services.
        port=nginx_port,
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
        LOGGER.debug("Creating HTTPS listener (port 443)...")
        https_resp = alb_service.create_https_listener(
            load_balancer_arn=alb_arn,
            target_group_arn=target_group_arn,
            certificate_arn=config.alb_certificate_arn,
            port=443,
        )
        https_listener_arn = https_resp["Listeners"][0]["ListenerArn"]

        if config.force_https_redirect:
            # Create HTTP→HTTPS redirect listener
            LOGGER.debug("Creating HTTP→HTTPS redirect listener...")
            redirect_resp = alb_service.create_redirect_listener(
                load_balancer_arn=alb_arn,
                port=80,
            )
            listener_arn = redirect_resp["Listeners"][0]["ListenerArn"]
            LOGGER.info("HTTPS enabled with HTTP redirect")
        else:
            # Keep HTTP listener alongside HTTPS
            LOGGER.debug("Creating HTTP listener (port 80)...")
            listener_resp = alb_service.create_listener(
                load_balancer_arn=alb_arn,
                target_group_arn=target_group_arn,
                port=80,
                protocol="HTTP",
            )
            listener_arn = listener_resp["Listeners"][0]["ListenerArn"]
            LOGGER.info("HTTPS enabled with HTTP listener")
    else:
        # HTTP-only (no certificate or HTTPS disabled)
        LOGGER.debug("Creating HTTP listener...")
        listener_resp = alb_service.create_listener(
            load_balancer_arn=alb_arn,
            target_group_arn=target_group_arn,
            port=80,
            protocol="HTTP",
        )
        listener_arn = listener_resp["Listeners"][0]["ListenerArn"]

    LOGGER.info(f"ALB created: {alb_dns}")

    return {
        "alb_arn": alb_arn,
        "alb_dns": alb_dns,
        "alb_zone_id": alb_zone_id,
        "target_group_arn": target_group_arn,
        "listener_arn": listener_arn,
        "https_listener_arn": https_listener_arn,
        "https_enabled": https_enabled,
    }


def build_n8n_url_patch_commands(host: str, protocol: str, proxy_hops: int) -> list[str]:
    """Build the SSM shell commands that patch ``runtime.env`` for n8n's public URL.

    n8n uses ``WEBHOOK_URL``/``N8N_EDITOR_BASE_URL`` to generate webhook/editor
    links; behind an ALB/CDN these must reflect the public host. The returned
    command list is a bash script (bashisms: ``pipefail``, ``set -a``).
    """
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
    return cmd_lines


def build_tier2_state(
    tier1_state: DeploymentState,
    alb_info: dict[str, Any],
) -> DeploymentState:
    """Build the final Tier 2 deployment state with ALB information."""
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
        efs_mount_target_ids=tier1_state.efs_mount_target_ids,
        efs_mount_target_ip=tier1_state.efs_mount_target_ip,
        iam_role_name=tier1_state.iam_role_name,
        iam_role_arn=tier1_state.iam_role_arn,
        iam_instance_profile_name=tier1_state.iam_instance_profile_name,
        iam_instance_profile_arn=tier1_state.iam_instance_profile_arn,
        instance_id=tier1_state.instance_id,
        launch_template_id=tier1_state.launch_template_id,
        auto_scaling_group_name=tier1_state.auto_scaling_group_name,
        spot_event_log_group=tier1_state.spot_event_log_group,
        spot_event_rule_names=tier1_state.spot_event_rule_names,
        spot_lease_table_name=tier1_state.spot_lease_table_name,
        spot_lifecycle_hook_names=tier1_state.spot_lifecycle_hook_names,
        spot_coordinator_function_name=tier1_state.spot_coordinator_function_name,
        spot_coordinator_role_name=tier1_state.spot_coordinator_role_name,
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
