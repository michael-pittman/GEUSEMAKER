from __future__ import annotations

import gzip

import pytest

from geusemaker.models import DeploymentConfig
from geusemaker.orchestration.errors import OrchestrationError
from geusemaker.orchestration.tier1 import Tier1Orchestrator
from tests.unit.test_orchestration.conftest import (
    StubEC2Service,
    StubEFSService,
    StubIAMService,
    StubSecurityGroupService,
    StubStateManager,
    StubVPCService,
)


def _orchestrator() -> tuple[Tier1Orchestrator, StubStateManager, StubVPCService]:
    orch = Tier1Orchestrator()
    orch.vpc_service = StubVPCService()
    orch.efs_service = StubEFSService()
    orch.sg_service = StubSecurityGroupService()
    orch.ec2_service = StubEC2Service()
    orch.iam_service = StubIAMService()
    state_manager = StubStateManager()
    orch.state_manager = state_manager
    return orch, state_manager, orch.vpc_service


def test_deploy_creates_new_vpc_when_missing() -> None:
    orch, state_manager, vpc_service = _orchestrator()
    config = DeploymentConfig(stack_name="stack", tier="dev")

    state = orch.deploy(config)

    assert vpc_service.created is True
    assert vpc_service.configured is False
    assert state.vpc_id == "vpc-new"
    assert state_manager.saved_state is not None
    assert any(rule.get("ToPort") == 2049 for rule in orch.sg_service.last_ingress)


def test_deploy_configures_existing_vpc_when_provided() -> None:
    orch, _, vpc_service = _orchestrator()
    config = DeploymentConfig(stack_name="stack", tier="dev", vpc_id="vpc-existing")

    state = orch.deploy(config)

    assert vpc_service.configured is True
    assert vpc_service.created is False
    assert state.vpc_id == "vpc-existing"


def test_deploy_prefers_configured_subnet_for_existing_vpc() -> None:
    orch, _, vpc_service = _orchestrator()
    config = DeploymentConfig(
        stack_name="stack",
        tier="dev",
        vpc_id="vpc-existing",
        subnet_id="subnet-public-1",
        public_subnet_ids=["subnet-public-1"],
        private_subnet_ids=["subnet-private-1"],
        storage_subnet_id="subnet-private-1",
    )

    state = orch.deploy(config)

    assert state.vpc_id == "vpc-existing"
    assert orch.efs_service.last_subnet_id == "subnet-private-1"
    assert orch.ec2_service.last_subnet_id == "subnet-public-1"
    assert state.storage_subnet_id == "subnet-private-1"


def test_deploy_errors_when_configured_subnet_not_public() -> None:
    orch, _, _ = _orchestrator()
    config = DeploymentConfig(stack_name="stack", tier="dev", vpc_id="vpc-existing", subnet_id="subnet-missing")

    with pytest.raises(OrchestrationError):
        orch.deploy(config)


def test_deploy_passes_ami_preferences() -> None:
    orch, _, _ = _orchestrator()
    config = DeploymentConfig(
        stack_name="stack",
        tier="dev",
        os_type="amazon-linux-2",
        architecture="arm64",
        ami_type="tensorflow",
    )

    orch.deploy(config)

    assert orch.ec2_service.last_dlami_args == {
        "os_type": "amazon-linux-2",
        "architecture": "arm64",
        "ami_type": "tensorflow",
        "instance_type": "t3.medium",  # Default instance type from DeploymentConfig
    }


def test_deploy_compresses_userdata_before_launch() -> None:
    orch, _, _ = _orchestrator()
    config = DeploymentConfig(stack_name="stack", tier="dev")

    orch.deploy(config)

    payload = orch.ec2_service.last_user_data
    assert isinstance(payload, (bytes, bytearray))

    decompressed = gzip.decompress(payload).decode()
    assert "#!/bin/bash" in decompressed
    assert len(payload) < len(decompressed.encode("utf-8"))


def test_deploy_adds_https_port_to_reused_sg_when_https_enabled() -> None:
    """Test that HTTPS port is added to reused security group when HTTPS is enabled."""
    orch, _, _ = _orchestrator()
    config = DeploymentConfig(
        stack_name="stack",
        tier="dev",
        enable_https=True,
        security_group_id="sg-existing",
    )

    orch.deploy(config)

    assert orch.sg_service.https_port_added is True


def test_deploy_skips_https_port_when_already_exists() -> None:
    """Test that HTTPS port is not re-added if it already exists."""
    orch, _, _ = _orchestrator()
    # Simulate port 443 already existing
    orch.sg_service.https_port_existed = True
    config = DeploymentConfig(
        stack_name="stack",
        tier="dev",
        enable_https=True,
        security_group_id="sg-existing",
    )

    orch.deploy(config)

    assert orch.sg_service.https_port_added is False


def test_deploy_includes_https_port_in_new_sg() -> None:
    """Test that HTTPS port is included when creating a new security group."""
    orch, _, _ = _orchestrator()
    config = DeploymentConfig(stack_name="stack", tier="dev", enable_https=True)

    orch.deploy(config)

    # Verify port 443 is in the ingress rules
    assert any(rule.get("ToPort") == 443 for rule in orch.sg_service.last_ingress)


def test_deploy_skips_https_port_when_disabled() -> None:
    """Test that HTTPS port is not added when HTTPS is disabled."""
    orch, _, _ = _orchestrator()
    config = DeploymentConfig(stack_name="stack", tier="dev", enable_https=False)

    orch.deploy(config)

    # Verify port 443 is NOT in the ingress rules
    assert not any(rule.get("ToPort") == 443 for rule in orch.sg_service.last_ingress)
