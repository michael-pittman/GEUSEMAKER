"""Pure tier -> feature normalization for deployment configs.

Encodes the topology-driven feature defaults (ALB/CDN enablement and the
rollback timeout floor for CDN deployments) that used to live inline in the CLI
runner. This is a pure function with no AWS side effects: given a config it
returns a possibly-updated config. It lives in ``orchestration`` because it
expresses deployment topology policy alongside orchestrator selection; the CLI
may call it but must not own the coercion.
"""

from __future__ import annotations

from geusemaker.models import DeploymentConfig

# Fields adjusted by normalization; used by callers that want to report changes.
NORMALIZED_FIELDS = ("enable_alb", "enable_cdn", "rollback_timeout_minutes")

# CDN deployments need a longer rollback window: ACM issuance + instance + ALB
# alone take ~15 minutes before CloudFront's 15-30 minute rollout begins, so the
# 15-minute default would abort every healthy Tier 3 deploy.
_CDN_ROLLBACK_TIMEOUT_MINUTES = 60


def normalize_deployment_config(config: DeploymentConfig) -> DeploymentConfig:
    """Return a config with tier-driven feature flags coerced to sane defaults.

    - ``automation`` tier implies an ALB.
    - ``gpu`` tier implies both an ALB and a CDN.
    - CDN deployments raise the rollback timeout floor to 60 minutes unless the
      user already chose a larger value.

    Pure: no AWS calls, no I/O. Returns the same instance when nothing changes.
    """
    updates: dict[str, object] = {}

    if config.tier == "automation" and not config.enable_alb:
        updates["enable_alb"] = True
    if config.tier == "gpu":
        if not config.enable_alb:
            updates["enable_alb"] = True
        if not config.enable_cdn:
            updates["enable_cdn"] = True
    if (config.enable_cdn or config.tier == "gpu") and config.rollback_timeout_minutes <= 15:
        updates["rollback_timeout_minutes"] = _CDN_ROLLBACK_TIMEOUT_MINUTES

    if not updates:
        return config
    return config.model_copy(update=updates)


__all__ = ["NORMALIZED_FIELDS", "normalize_deployment_config"]
