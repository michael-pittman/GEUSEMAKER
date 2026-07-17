"""Tests for pure tier -> feature normalization."""

from __future__ import annotations

from geusemaker.models import DeploymentConfig
from geusemaker.orchestration.normalization import normalize_deployment_config


def _config(**overrides: object) -> DeploymentConfig:
    base = {"stack_name": "stack", "tier": "dev", "use_spot": False}
    base.update(overrides)
    return DeploymentConfig(**base)  # type: ignore[arg-type]


def test_dev_tier_is_unchanged() -> None:
    config = _config(tier="dev", enable_alb=False, enable_cdn=False)
    result = normalize_deployment_config(config)
    assert result is config  # no updates -> same instance
    assert result.enable_alb is False
    assert result.enable_cdn is False
    assert result.rollback_timeout_minutes == 15


def test_automation_tier_enables_alb() -> None:
    config = _config(tier="automation", enable_alb=False)
    result = normalize_deployment_config(config)
    assert result.enable_alb is True
    assert result.enable_cdn is False
    # Not a CDN deploy: rollback timeout stays at default.
    assert result.rollback_timeout_minutes == 15


def test_automation_tier_preserves_explicit_alb() -> None:
    config = _config(tier="automation", enable_alb=True)
    result = normalize_deployment_config(config)
    assert result.enable_alb is True


def test_gpu_tier_enables_alb_cdn_and_bumps_rollback_timeout() -> None:
    config = _config(tier="gpu", instance_type="g4dn.xlarge", enable_alb=False, enable_cdn=False)
    result = normalize_deployment_config(config)
    assert result.enable_alb is True
    assert result.enable_cdn is True
    assert result.rollback_timeout_minutes == 60


def test_gpu_tier_respects_larger_user_rollback_timeout() -> None:
    config = _config(tier="gpu", instance_type="g4dn.xlarge", rollback_timeout_minutes=45)
    result = normalize_deployment_config(config)
    assert result.rollback_timeout_minutes == 45


def test_cdn_flag_on_non_gpu_tier_bumps_rollback_timeout() -> None:
    config = _config(tier="automation", enable_alb=True, enable_cdn=True)
    result = normalize_deployment_config(config)
    assert result.rollback_timeout_minutes == 60
