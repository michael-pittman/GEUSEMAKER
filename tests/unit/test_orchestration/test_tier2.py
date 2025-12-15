"""Unit tests for Tier2Orchestrator."""

from __future__ import annotations

import pytest

from geusemaker.models import DeploymentConfig, SubnetResource, VPCResource
from geusemaker.orchestration.errors import OrchestrationError
from geusemaker.orchestration.tier2 import Tier2Orchestrator
from tests.unit.test_orchestration.conftest import (
    StubALBService,
    StubEC2Service,
    StubEFSService,
    StubIAMService,
    StubSecurityGroupService,
    StubStateManager,
    StubUserDataGenerator,
    StubVPCService,
)


class SingleSubnetVPCService(StubVPCService):
    """Return only one subnet to exercise ALB subnet validation."""

    def _build_vpc(self, vpc_id: str, created: bool = True) -> VPCResource:
        public = [
            SubnetResource(
                subnet_id="subnet-public-1",
                vpc_id=vpc_id,
                cidr_block="10.0.1.0/24",
                availability_zone="us-east-1a",
                is_public=True,
                route_table_id="rtb-public",
            ),
        ]
        return VPCResource(
            vpc_id=vpc_id,
            cidr_block="10.0.0.0/16",
            name="test",
            public_subnets=public,
            private_subnets=[],
            internet_gateway_id="igw-1",
            route_table_ids=["rtb-public"],
            created_by_geusemaker=created,
        )


def test_tier2_orchestrator_creates_alb_when_enabled() -> None:
    """Test that Tier2Orchestrator creates ALB resources when enable_alb=True."""
    config = DeploymentConfig(
        stack_name="test-tier2",
        tier="automation",
        instance_type="t3.medium",
        enable_alb=True,
    )

    state_manager = StubStateManager()
    orchestrator = Tier2Orchestrator(client_factory=None, region="us-east-1", state_manager=state_manager)  # type: ignore[arg-type]

    # Replace services with stubs
    orchestrator.vpc_service = StubVPCService()  # type: ignore[assignment]
    orchestrator.sg_service = StubSecurityGroupService()  # type: ignore[assignment]
    orchestrator.efs_service = StubEFSService()  # type: ignore[assignment]
    orchestrator.iam_service = StubIAMService()  # type: ignore[assignment]
    orchestrator.ec2_service = StubEC2Service()  # type: ignore[assignment]
    orchestrator.alb_service = StubALBService()  # type: ignore[assignment]
    orchestrator.userdata_generator = StubUserDataGenerator()  # type: ignore[assignment]

    # Execute deployment
    state = orchestrator.deploy(config, enable_rollback=False)

    # Verify Tier 1 resources were created
    assert orchestrator.vpc_service.created  # type: ignore[attr-defined]
    assert orchestrator.efs_service.waited_for_available  # type: ignore[attr-defined]
    assert orchestrator.iam_service.role_created  # type: ignore[attr-defined]
    assert orchestrator.ec2_service.launched  # type: ignore[attr-defined]

    # Verify ALB resources were created
    assert orchestrator.alb_service.alb_created  # type: ignore[attr-defined]
    assert orchestrator.alb_service.target_group_created  # type: ignore[attr-defined]
    assert orchestrator.alb_service.listener_created  # type: ignore[attr-defined]
    assert orchestrator.alb_service.targets_registered  # type: ignore[attr-defined]
    assert orchestrator.alb_service.waited_for_healthy  # type: ignore[attr-defined]

    # Verify state has ALB information
    assert state.alb_arn is not None
    assert state.alb_dns is not None
    assert state.target_group_arn is not None
    assert "elb.amazonaws.com" in state.alb_dns


def test_tier2_orchestrator_skips_alb_when_disabled() -> None:
    """Test that Tier2Orchestrator skips ALB creation when enable_alb=False."""
    config = DeploymentConfig(
        stack_name="test-tier2-no-alb",
        tier="automation",
        instance_type="t3.medium",
        enable_alb=False,
    )

    state_manager = StubStateManager()
    orchestrator = Tier2Orchestrator(client_factory=None, region="us-east-1", state_manager=state_manager)  # type: ignore[arg-type]

    # Replace services with stubs
    orchestrator.vpc_service = StubVPCService()  # type: ignore[assignment]
    orchestrator.sg_service = StubSecurityGroupService()  # type: ignore[assignment]
    orchestrator.efs_service = StubEFSService()  # type: ignore[assignment]
    orchestrator.iam_service = StubIAMService()  # type: ignore[assignment]
    orchestrator.ec2_service = StubEC2Service()  # type: ignore[assignment]
    orchestrator.alb_service = StubALBService()  # type: ignore[assignment]
    orchestrator.userdata_generator = StubUserDataGenerator()  # type: ignore[assignment]

    # Execute deployment
    state = orchestrator.deploy(config, enable_rollback=False)

    # Verify Tier 1 resources were created
    assert orchestrator.ec2_service.launched  # type: ignore[attr-defined]

    # Verify ALB resources were NOT created
    assert not orchestrator.alb_service.alb_created  # type: ignore[attr-defined]
    assert not orchestrator.alb_service.target_group_created  # type: ignore[attr-defined]

    # Verify state does NOT have ALB information
    assert state.alb_arn is None
    assert state.alb_dns is None
    assert state.target_group_arn is None


def test_tier2_orchestrator_requires_minimum_two_subnets() -> None:
    """Test that Tier2Orchestrator raises error if less than 2 subnets available."""
    config = DeploymentConfig(
        stack_name="test-tier2-insufficient-subnets",
        tier="automation",
        instance_type="t3.medium",
        enable_alb=True,
    )

    state_manager = StubStateManager()
    orchestrator = Tier2Orchestrator(client_factory=None, region="us-east-1", state_manager=state_manager)  # type: ignore[arg-type]

    # Replace services with stubs
    orchestrator.vpc_service = SingleSubnetVPCService()  # type: ignore[assignment]
    orchestrator.sg_service = StubSecurityGroupService()  # type: ignore[assignment]
    orchestrator.efs_service = StubEFSService()  # type: ignore[assignment]
    orchestrator.iam_service = StubIAMService()  # type: ignore[assignment]
    orchestrator.ec2_service = StubEC2Service()  # type: ignore[assignment]
    orchestrator.alb_service = StubALBService()  # type: ignore[assignment]
    orchestrator.userdata_generator = StubUserDataGenerator()  # type: ignore[assignment]

    # Deployment should fail with meaningful error
    with pytest.raises(OrchestrationError, match="ALB requires at least 2 subnets"):
        orchestrator.deploy(config, enable_rollback=False)


def test_tier2_orchestrator_n8n_url_uses_alb_dns() -> None:
    """Test that n8n_url uses ALB DNS when ALB is enabled."""
    config = DeploymentConfig(
        stack_name="test-tier2-url",
        tier="automation",
        instance_type="t3.medium",
        enable_alb=True,
    )

    state_manager = StubStateManager()
    orchestrator = Tier2Orchestrator(client_factory=None, region="us-east-1", state_manager=state_manager)  # type: ignore[arg-type]

    # Replace services with stubs
    orchestrator.vpc_service = StubVPCService()  # type: ignore[assignment]
    orchestrator.sg_service = StubSecurityGroupService()  # type: ignore[assignment]
    orchestrator.efs_service = StubEFSService()  # type: ignore[assignment]
    orchestrator.iam_service = StubIAMService()  # type: ignore[assignment]
    orchestrator.ec2_service = StubEC2Service()  # type: ignore[assignment]
    orchestrator.alb_service = StubALBService()  # type: ignore[assignment]
    orchestrator.userdata_generator = StubUserDataGenerator()  # type: ignore[assignment]

    # Execute deployment
    state = orchestrator.deploy(config, enable_rollback=False)

    # Verify n8n URL uses ALB DNS
    assert "elb.amazonaws.com" in state.n8n_url
    assert state.n8n_url.startswith("http://")
    assert ":80" in state.n8n_url
