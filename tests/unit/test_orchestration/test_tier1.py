from __future__ import annotations

import gzip
from dataclasses import dataclass

import pytest

from geusemaker.models import DeploymentConfig, SubnetResource, VPCResource
from geusemaker.orchestration.errors import OrchestrationError
from geusemaker.orchestration.tier1 import Tier1Orchestrator


@dataclass
class StubStateManager:
    saved_state = None

    async def save_deployment(self, state) -> None:  # type: ignore[no-untyped-def]
        self.saved_state = state


class StubVPCService:
    def __init__(self) -> None:
        self.created = False
        self.configured = False

    def create_vpc_with_subnets(
        self,
        cidr_block: str,
        name: str,
        deployment: str | None = None,
        tier: str | None = None,
    ) -> VPCResource:  # noqa: ARG002
        self.created = True
        return self._build_vpc("vpc-new")

    def configure_existing_vpc(
        self,
        vpc_id: str,
        name: str | None = None,
        deployment: str | None = None,
        tier: str | None = None,
        attach_internet_gateway: bool = False,
    ) -> VPCResource:  # noqa: ARG002
        self.configured = True
        return self._build_vpc(vpc_id, created=False)

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
        private = [
            SubnetResource(
                subnet_id="subnet-private-1",
                vpc_id=vpc_id,
                cidr_block="10.0.101.0/24",
                availability_zone="us-east-1b",
                is_public=False,
                route_table_id="rtb-private",
            ),
        ]
        return VPCResource(
            vpc_id=vpc_id,
            cidr_block="10.0.0.0/16",
            name="test",
            public_subnets=public,
            private_subnets=private,
            internet_gateway_id="igw-1",
            route_table_ids=["rtb-public"],
            created_by_geusemaker=created,
        )


class StubSecurityGroupService:
    def __init__(self) -> None:
        self.last_ingress = None

    def create_security_group(self, name: str, description: str, vpc_id: str, ingress_rules):  # type: ignore[no-untyped-def]  # noqa: ARG002
        self.last_ingress = ingress_rules
        return {"group_id": "sg-1"}


class StubEFSService:
    def __init__(self) -> None:
        self.last_subnet_id = None
        self.waited_for_available = False
        self.waited_for_mount_target_available = False

    def create_filesystem(self, tags):  # type: ignore[no-untyped-def]
        return {"FileSystemId": "fs-1"}

    def wait_for_available(self, fs_id: str, max_attempts: int = 60, delay: int = 5) -> None:  # noqa: ARG002
        """Stub wait - EFS is immediately available in tests."""
        self.waited_for_available = True

    def create_mount_target(self, fs_id: str, subnet_id: str, security_groups):  # type: ignore[no-untyped-def]  # noqa: ARG002
        self.last_subnet_id = subnet_id
        return "mt-1"

    def wait_for_mount_target_available(self, mount_target_id: str, max_attempts: int = 60, delay: int = 5) -> None:  # noqa: ARG002
        """Stub wait - mount target is immediately available in tests."""
        self.waited_for_mount_target_available = True


class StubEC2Service:
    def __init__(self) -> None:
        self.last_subnet_id = None
        self.last_dlami_args = None
        self.last_user_data = None

    def get_latest_dlami(self, **kwargs):  # type: ignore[no-untyped-def]
        self.last_dlami_args = kwargs
        return "ami-123"

    def launch_instance(self, **kwargs):  # type: ignore[no-untyped-def]
        self.last_subnet_id = kwargs.get("SubnetId")
        self.last_user_data = kwargs.get("UserData")
        return {"Instances": [{"InstanceId": "i-1"}]}

    def wait_for_running(self, instance_id: str) -> None:  # noqa: ARG002
        return None

    def describe_instance(self, instance_id: str):  # type: ignore[no-untyped-def]  # noqa: ARG002
        return {"PublicIpAddress": "1.2.3.4", "PrivateIpAddress": "10.0.1.10"}


def _orchestrator() -> tuple[Tier1Orchestrator, StubStateManager, StubVPCService]:
    orch = Tier1Orchestrator()
    orch.vpc_service = StubVPCService()
    orch.efs_service = StubEFSService()
    orch.sg_service = StubSecurityGroupService()
    orch.ec2_service = StubEC2Service()
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
