"""Tests for HTTPS/TLS configuration in deployment models."""

from geusemaker.models import DeploymentConfig


def test_deployment_config_https_defaults() -> None:
    """Test that HTTPS fields have correct default values."""
    config = DeploymentConfig(
        stack_name="test-stack",
        tier="dev",
    )

    assert config.enable_https is True
    assert config.tier1_use_self_signed is True
    assert config.alb_certificate_arn is None
    assert config.cloudfront_certificate_arn is None
    assert config.force_https_redirect is True


def test_deployment_config_with_alb_certificate() -> None:
    """Test DeploymentConfig with ALB certificate ARN for Tier 2/3."""
    cert_arn = "arn:aws:acm:us-east-1:123456789012:certificate/abc-123-def"
    config = DeploymentConfig(
        stack_name="prod-stack",
        tier="automation",
        enable_https=True,
        alb_certificate_arn=cert_arn,
    )

    assert config.enable_https is True
    assert config.alb_certificate_arn == cert_arn
    assert config.force_https_redirect is True


def test_deployment_config_with_cloudfront_certificate() -> None:
    """Test DeploymentConfig with CloudFront certificate ARN for Tier 3."""
    alb_cert = "arn:aws:acm:us-west-2:123456789012:certificate/alb-cert"
    cf_cert = "arn:aws:acm:us-east-1:123456789012:certificate/cf-cert"

    config = DeploymentConfig(
        stack_name="gpu-stack",
        tier="gpu",
        enable_https=True,
        alb_certificate_arn=alb_cert,
        cloudfront_certificate_arn=cf_cert,
    )

    assert config.enable_https is True
    assert config.alb_certificate_arn == alb_cert
    assert config.cloudfront_certificate_arn == cf_cert
    assert config.force_https_redirect is True


def test_deployment_config_https_disabled() -> None:
    """Test disabling HTTPS for specific use cases."""
    config = DeploymentConfig(
        stack_name="test-stack",
        tier="dev",
        enable_https=False,
    )

    assert config.enable_https is False
    # Other HTTPS fields should still have defaults
    assert config.tier1_use_self_signed is True
    assert config.force_https_redirect is True


def test_deployment_config_no_https_redirect() -> None:
    """Test disabling HTTP→HTTPS redirect while keeping HTTPS enabled."""
    config = DeploymentConfig(
        stack_name="test-stack",
        tier="automation",
        enable_https=True,
        force_https_redirect=False,
    )

    assert config.enable_https is True
    assert config.force_https_redirect is False
