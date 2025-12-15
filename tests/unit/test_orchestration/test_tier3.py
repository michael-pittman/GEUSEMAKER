"""Unit tests for Tier3Orchestrator."""

from __future__ import annotations

import pytest

from geusemaker.models import DeploymentConfig
from geusemaker.orchestration.errors import OrchestrationError
from geusemaker.orchestration.tier3 import Tier3Orchestrator
from tests.unit.test_orchestration.conftest import (
    StubALBService,
    StubCloudFrontService,
    StubEC2Service,
    StubEFSService,
    StubIAMService,
    StubSecurityGroupService,
    StubStateManager,
    StubUserDataGenerator,
    StubVPCService,
)


def test_tier3_orchestrator_creates_cloudfront_with_alb() -> None:
    """Test that Tier3Orchestrator creates CloudFront distribution with ALB origin."""
    config = DeploymentConfig(
        stack_name="test-tier3",
        tier="gpu",
        instance_type="g4dn.xlarge",
        enable_alb=True,
    )

    state_manager = StubStateManager()
    orchestrator = Tier3Orchestrator(client_factory=None, region="us-east-1", state_manager=state_manager)  # type: ignore[arg-type]

    # Replace services with stubs
    orchestrator.vpc_service = StubVPCService()  # type: ignore[assignment]
    orchestrator.sg_service = StubSecurityGroupService()  # type: ignore[assignment]
    orchestrator.efs_service = StubEFSService()  # type: ignore[assignment]
    orchestrator.iam_service = StubIAMService()  # type: ignore[assignment]
    orchestrator.ec2_service = StubEC2Service()  # type: ignore[assignment]
    orchestrator.alb_service = StubALBService()  # type: ignore[assignment]
    orchestrator.cloudfront_service = StubCloudFrontService()  # type: ignore[assignment]
    orchestrator.userdata_generator = StubUserDataGenerator()  # type: ignore[assignment]

    # Execute deployment
    state = orchestrator.deploy(config, enable_rollback=False)

    # Verify Tier 1 resources were created
    assert orchestrator.vpc_service.created  # type: ignore[attr-defined]
    assert orchestrator.efs_service.waited_for_available  # type: ignore[attr-defined]
    assert orchestrator.iam_service.role_created  # type: ignore[attr-defined]
    assert orchestrator.ec2_service.launched  # type: ignore[attr-defined]

    # Verify Tier 2 ALB resources were created
    assert orchestrator.alb_service.alb_created  # type: ignore[attr-defined]
    assert orchestrator.alb_service.target_group_created  # type: ignore[attr-defined]
    assert orchestrator.alb_service.listener_created  # type: ignore[attr-defined]
    assert orchestrator.alb_service.targets_registered  # type: ignore[attr-defined]
    assert orchestrator.alb_service.waited_for_healthy  # type: ignore[attr-defined]

    # Verify Tier 3 CloudFront resources were created
    assert orchestrator.cloudfront_service.distribution_created  # type: ignore[attr-defined]
    assert orchestrator.cloudfront_service.waited_for_deployed  # type: ignore[attr-defined]

    # Verify state has CloudFront information
    assert state.cloudfront_id is not None
    assert state.cloudfront_domain is not None
    assert "cloudfront.net" in state.cloudfront_domain


def test_tier3_orchestrator_requires_alb_enabled() -> None:
    """Test that Tier3Orchestrator raises error if enable_alb=False."""
    config = DeploymentConfig(
        stack_name="test-tier3-no-alb",
        tier="gpu",
        instance_type="g4dn.xlarge",
        enable_alb=False,
    )

    state_manager = StubStateManager()
    orchestrator = Tier3Orchestrator(client_factory=None, region="us-east-1", state_manager=state_manager)  # type: ignore[arg-type]

    # Deployment should fail with ALB requirement error
    with pytest.raises(OrchestrationError, match="Tier 3 deployments require enable_alb=True"):
        orchestrator.deploy(config, enable_rollback=False)


def test_tier3_orchestrator_accepts_gpu_tier() -> None:
    """Test that Tier3Orchestrator accepts GPU tier."""
    config = DeploymentConfig(
        stack_name="test-tier3-gpu",
        tier="gpu",
        instance_type="g4dn.xlarge",
        enable_alb=True,
    )

    state_manager = StubStateManager()
    orchestrator = Tier3Orchestrator(client_factory=None, region="us-east-1", state_manager=state_manager)  # type: ignore[arg-type]

    # Replace services with stubs
    orchestrator.vpc_service = StubVPCService()  # type: ignore[assignment]
    orchestrator.sg_service = StubSecurityGroupService()  # type: ignore[assignment]
    orchestrator.efs_service = StubEFSService()  # type: ignore[assignment]
    orchestrator.iam_service = StubIAMService()  # type: ignore[assignment]
    orchestrator.ec2_service = StubEC2Service()  # type: ignore[assignment]
    orchestrator.alb_service = StubALBService()  # type: ignore[assignment]
    orchestrator.cloudfront_service = StubCloudFrontService()  # type: ignore[assignment]
    orchestrator.userdata_generator = StubUserDataGenerator()  # type: ignore[assignment]

    # Execute deployment - should succeed
    state = orchestrator.deploy(config, enable_rollback=False)

    # Verify deployment succeeded
    assert state.stack_name == "test-tier3-gpu"
    assert state.cloudfront_id is not None


def test_tier3_orchestrator_accepts_automation_tier() -> None:
    """Test that Tier3Orchestrator accepts automation tier."""
    config = DeploymentConfig(
        stack_name="test-tier3-automation",
        tier="automation",
        instance_type="t3.medium",
        enable_alb=True,
    )

    state_manager = StubStateManager()
    orchestrator = Tier3Orchestrator(client_factory=None, region="us-east-1", state_manager=state_manager)  # type: ignore[arg-type]

    # Replace services with stubs
    orchestrator.vpc_service = StubVPCService()  # type: ignore[assignment]
    orchestrator.sg_service = StubSecurityGroupService()  # type: ignore[assignment]
    orchestrator.efs_service = StubEFSService()  # type: ignore[assignment]
    orchestrator.iam_service = StubIAMService()  # type: ignore[assignment]
    orchestrator.ec2_service = StubEC2Service()  # type: ignore[assignment]
    orchestrator.alb_service = StubALBService()  # type: ignore[assignment]
    orchestrator.cloudfront_service = StubCloudFrontService()  # type: ignore[assignment]
    orchestrator.userdata_generator = StubUserDataGenerator()  # type: ignore[assignment]

    # Execute deployment - should succeed
    state = orchestrator.deploy(config, enable_rollback=False)

    # Verify deployment succeeded
    assert state.stack_name == "test-tier3-automation"
    assert state.cloudfront_id is not None


def test_tier3_orchestrator_n8n_url_uses_cloudfront_domain() -> None:
    """Test that n8n_url uses CloudFront domain."""
    config = DeploymentConfig(
        stack_name="test-tier3-url",
        tier="gpu",
        instance_type="g4dn.xlarge",
        enable_alb=True,
    )

    state_manager = StubStateManager()
    orchestrator = Tier3Orchestrator(client_factory=None, region="us-east-1", state_manager=state_manager)  # type: ignore[arg-type]

    # Replace services with stubs
    orchestrator.vpc_service = StubVPCService()  # type: ignore[assignment]
    orchestrator.sg_service = StubSecurityGroupService()  # type: ignore[assignment]
    orchestrator.efs_service = StubEFSService()  # type: ignore[assignment]
    orchestrator.iam_service = StubIAMService()  # type: ignore[assignment]
    orchestrator.ec2_service = StubEC2Service()  # type: ignore[assignment]
    orchestrator.alb_service = StubALBService()  # type: ignore[assignment]
    orchestrator.cloudfront_service = StubCloudFrontService()  # type: ignore[assignment]
    orchestrator.userdata_generator = StubUserDataGenerator()  # type: ignore[assignment]

    # Execute deployment
    state = orchestrator.deploy(config, enable_rollback=False)

    # Verify n8n URL uses CloudFront domain
    assert "cloudfront.net" in state.n8n_url
    assert state.n8n_url.startswith("http://")
    assert ":80" in state.n8n_url
