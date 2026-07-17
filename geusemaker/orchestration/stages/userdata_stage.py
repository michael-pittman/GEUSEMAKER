"""UserData assembly stage helpers for Tier1 deployments.

Pure logic extracted from ``Tier1Orchestrator._generate_userdata`` and
``_compress_userdata``. These build the ``UserDataConfig`` and compress the
rendered script; the coordinator still owns password generation and the actual
``UserDataGenerator.generate`` call.
"""

from __future__ import annotations

import gzip
from typing import Literal

from geusemaker.models import DeploymentConfig
from geusemaker.models.userdata import UserDataConfig
from geusemaker.orchestration.errors import OrchestrationError


def build_userdata_config(
    config: DeploymentConfig,
    region: str,
    efs_id: str,
    mt_ip: str,
    postgres_password: str,
    *,
    spot_protection_enabled: bool = False,
) -> UserDataConfig:
    """Assemble the ``UserDataConfig`` for instance initialization.

    Resolves the tier-specific HTTPS flag and n8n external-URL hints, then wires
    the EFS, spot-protection, and runtime-bundle settings into a single config.
    """
    efs_dns = f"{efs_id}.efs.{region}.amazonaws.com"

    # UserData's enable_https flag controls:
    # - Tier 1 (dev): self-signed certificate + NGINX reverse proxy
    # - Service runtime flags (e.g. n8n secure cookies/protocol)
    # For Tier 2/3, HTTPS is terminated at ALB/CloudFront, so only enable it
    # when the external endpoint will actually be HTTPS.
    if config.tier == "dev":
        userdata_enable_https = bool(config.enable_https and config.tier1_use_self_signed)
    elif config.enable_cdn:
        userdata_enable_https = bool(config.enable_https)
    elif config.enable_alb:
        userdata_enable_https = bool(config.enable_https and config.alb_certificate_arn is not None)
    else:
        userdata_enable_https = False

    # Configure n8n external URL hints so it generates webhooks with the right host.
    # For Tier 2/3, we can know the intended domain up front (Route 53 hosted zone selection).
    # For Tier 1, the public IP is only known after launch, so leave unset here.
    n8n_external_host: str | None = None
    n8n_external_protocol: Literal["http", "https"] | None = None
    n8n_proxy_hops: int | None = None
    if config.tier in {"automation", "gpu"} and config.alb_domain_name:
        n8n_external_host = config.alb_domain_name
        n8n_external_protocol = "https" if userdata_enable_https else "http"
        # Tier 2: ALB only (1 hop). Tier 3: CloudFront -> ALB (2 hops).
        n8n_proxy_hops = 2 if config.enable_cdn else 1

    return UserDataConfig(
        efs_id=efs_id,
        efs_dns=efs_dns,
        efs_mount_target_ip=mt_ip,
        tier=config.tier,
        workload=config.effective_workload,
        stack_name=config.stack_name,
        region=region,
        enable_https=userdata_enable_https,
        n8n_external_host=n8n_external_host,
        n8n_external_protocol=n8n_external_protocol,
        n8n_proxy_hops=n8n_proxy_hops,
        postgres_password=postgres_password,
        use_runtime_bundle=config.use_runtime_bundle,
        runtime_bundle_path=config.runtime_bundle_path,
        spot_protection_enabled=spot_protection_enabled,
        spot_lease_table_name=(f"{config.stack_name}-spot-lease"[:255] if spot_protection_enabled else None),
        spot_auto_scaling_group_name=(f"{config.stack_name}-spot-asg" if spot_protection_enabled else None),
        spot_log_group_name=(f"/geusemaker/{config.stack_name}/spot-events" if spot_protection_enabled else None),
        spot_launch_hook_name=(f"{config.stack_name[:42]}-launch" if spot_protection_enabled else None),
        spot_termination_hook_name=(f"{config.stack_name[:39]}-terminate" if spot_protection_enabled else None),
    )


def compress_userdata(userdata_script: str) -> bytes:
    """Gzip-compress UserData to stay within AWS 16KB limit (SDK base64-encodes for us)."""
    compressed = gzip.compress(userdata_script.encode("utf-8"))
    limit_bytes = 16_384
    if len(compressed) > limit_bytes:
        raise OrchestrationError(
            f"Compressed user data is {len(compressed)} bytes which exceeds the AWS limit of {limit_bytes} bytes.",
        )
    return compressed
