"""Shared stub classes for orchestration tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from geusemaker.models import SubnetResource, VPCResource


@dataclass
class StubStateManager:
    """Minimal async state manager used across orchestration tests."""

    saved_state = None

    async def save_deployment(self, state) -> None:  # type: ignore[no-untyped-def]
        self.saved_state = state

    async def load_deployment(self, stack_name: str):  # type: ignore[no-untyped-def]  # noqa: ARG002
        """Return saved state if it matches the stack name, else None."""
        if self.saved_state and self.saved_state.stack_name == stack_name:
            return self.saved_state
        return None

    async def archive_deployment(self, stack_name: str) -> None:  # noqa: ARG002
        """Archive deployment (stub no-op)."""
        return None


class StubVPCService:
    """Stub VPC service that can create or configure VPCs with subnets."""

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
        # Provide two public subnets by default so ALB tests have coverage.
        public = [
            SubnetResource(
                subnet_id="subnet-public-1",
                vpc_id=vpc_id,
                cidr_block="10.0.1.0/24",
                availability_zone="us-east-1a",
                is_public=True,
                route_table_id="rtb-public",
            ),
            SubnetResource(
                subnet_id="subnet-public-2",
                vpc_id=vpc_id,
                cidr_block="10.0.2.0/24",
                availability_zone="us-east-1b",
                is_public=True,
                route_table_id="rtb-public",
            ),
        ]
        private = [
            SubnetResource(
                subnet_id="subnet-private-1",
                vpc_id=vpc_id,
                cidr_block="10.0.101.0/24",
                availability_zone="us-east-1c",
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
    """Capture ingress rules for assertions."""

    def __init__(self) -> None:
        self.last_ingress = None
        self.https_port_added = False
        self.https_port_existed = False

    def create_security_group(self, name: str, description: str, vpc_id: str, ingress_rules):  # type: ignore[no-untyped-def]  # noqa: ARG002
        self.last_ingress = ingress_rules
        return {"group_id": "sg-1"}

    def ensure_https_port(self, group_id: str) -> bool:  # noqa: ARG002
        """
        Stub implementation of ensure_https_port.

        Returns True if port was added, False if it already existed.
        Tests can override https_port_existed to simulate existing port.
        """
        if self.https_port_existed:
            return False
        self.https_port_added = True
        return True


class StubEFSService:
    """Stub EFS service that records wait state and subnet placement."""

    def __init__(self) -> None:
        self.last_subnet_id = None
        self.waited_for_available = False
        self.waited_for_mount_target = False
        self.waited_for_mount_target_available = False

    def create_filesystem(self, tags):  # type: ignore[no-untyped-def]  # noqa: ARG002
        return {"FileSystemId": "fs-1"}

    def wait_for_available(self, fs_id: str, max_attempts: int = 60, delay: int = 5) -> None:  # noqa: ARG002
        self.waited_for_available = True

    def create_mount_target(self, fs_id: str, subnet_id: str, security_groups):  # type: ignore[no-untyped-def]  # noqa: ARG002
        self.last_subnet_id = subnet_id
        return "fsmt-1"

    def wait_for_mount_target_available(self, mt_id: str, max_attempts: int = 40, delay: int = 5) -> None:  # noqa: ARG002
        self.waited_for_mount_target = True
        self.waited_for_mount_target_available = True

    def get_mount_target_ip(self, mt_id: str) -> str:  # noqa: ARG002
        return "10.0.1.100"


class StubIAMService:
    """Stub IAM service capturing role/profile creation."""

    def __init__(self) -> None:
        self.role_created = False
        self.profile_created = False
        self.role_attached = False
        self.waited_for_profile = False
        # Backwards-compatible aliases used by older assertions
        self.created_role = False
        self.created_profile = False
        self.attached_role = False

    def create_efs_mount_role(self, role_name: str, tags) -> str:  # type: ignore[no-untyped-def]  # noqa: ARG002
        self.role_created = True
        self.created_role = True
        return f"arn:aws:iam::123456789012:role/{role_name}"

    def create_instance_profile(self, profile_name: str, tags) -> str:  # type: ignore[no-untyped-def]  # noqa: ARG002
        self.profile_created = True
        self.created_profile = True
        return f"arn:aws:iam::123456789012:instance-profile/{profile_name}"

    def attach_role_to_profile(self, profile_name: str, role_name: str) -> None:  # noqa: ARG002
        self.role_attached = True
        self.attached_role = True

    def wait_for_instance_profile(
        self,
        profile_name: str,
        role_name: str,
        max_attempts: int = 30,
        delay: int = 2,
    ) -> None:  # noqa: ARG002
        self.waited_for_profile = True


class StubEC2Service:
    """Stub EC2 service capturing launch parameters and readiness checks."""

    def __init__(self) -> None:
        self.last_subnet_id = None
        self.last_dlami_args: dict[str, Any] | None = None
        self.last_user_data = None
        self.launched = False
        self.waited_for_running = False

    def get_latest_dlami(self, **kwargs) -> str:  # type: ignore[no-untyped-def]
        self.last_dlami_args = kwargs
        return "ami-12345678"

    def get_root_device_name(self, ami_id: str) -> str:  # noqa: ARG002
        return "/dev/xvda"

    def launch_instance(self, **kwargs) -> dict:  # type: ignore[type-arg]  # noqa: ARG002
        self.launched = True
        self.last_subnet_id = kwargs.get("SubnetId")
        self.last_user_data = kwargs.get("UserData")
        return {
            "Instances": [
                {
                    "InstanceId": "i-1234567890abcdef0",
                    "State": {"Name": "pending"},
                },
            ],
        }

    def wait_for_running(self, instance_id: str, max_attempts: int = 60, delay: int = 5) -> None:  # noqa: ARG002
        self.waited_for_running = True

    def describe_instance(self, instance_id: str):  # type: ignore[no-untyped-def]  # noqa: ARG002
        return {
            "InstanceId": instance_id,
            "State": {"Name": "running"},
            "PublicIpAddress": "54.123.45.67",
            "PrivateIpAddress": "10.0.1.10",
        }


class StubALBService:
    """Stub ALB service capturing creation and health checks."""

    def __init__(self) -> None:
        self.alb_created = False
        self.target_group_created = False
        self.listener_created = False
        self.targets_registered = False
        self.waited_for_healthy = False

    def create_alb(
        self,
        name: str,
        subnets,  # type: ignore[no-untyped-def]
        security_groups,  # type: ignore[no-untyped-def]
        scheme: str = "internet-facing",
        tags=None,  # type: ignore[no-untyped-def]
    ):  # type: ignore[no-untyped-def]  # noqa: ARG002
        self.alb_created = True
        return {
            "LoadBalancers": [
                {
                    "LoadBalancerArn": "arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/test-alb/1234567890abcdef",
                    "DNSName": "test-alb-1234567890.us-east-1.elb.amazonaws.com",
                },
            ],
        }

    def create_target_group(
        self,
        name: str,
        vpc_id: str,
        port: int = 80,
        protocol: str = "HTTP",
        health_check_path: str = "/health",
        health_check_interval: int = 30,
        health_check_timeout: int = 5,
        healthy_threshold: int = 2,
        unhealthy_threshold: int = 2,
        tags=None,  # type: ignore[no-untyped-def]
    ):  # type: ignore[no-untyped-def]  # noqa: ARG002
        self.target_group_created = True
        return {
            "TargetGroups": [
                {
                    "TargetGroupArn": "arn:aws:elasticloadbalancing:us-east-1:123456789012:targetgroup/test-tg/1234567890abcdef",
                },
            ],
        }

    def create_listener(
        self,
        load_balancer_arn: str,
        target_group_arn: str,
        port: int = 80,
        protocol: str = "HTTP",
    ):  # type: ignore[no-untyped-def]  # noqa: ARG002
        self.listener_created = True
        return {
            "Listeners": [
                {
                    "ListenerArn": "arn:aws:elasticloadbalancing:us-east-1:123456789012:listener/app/test-alb/1234567890abcdef/1234567890abcdef",
                },
            ],
        }

    def register_targets(
        self,
        target_group_arn: str,
        instance_ids,  # type: ignore[no-untyped-def]
        port: int | None = None,
    ):  # type: ignore[no-untyped-def]  # noqa: ARG002
        self.targets_registered = True
        return {}

    def wait_for_healthy(
        self,
        target_group_arn: str,
        instance_ids,  # type: ignore[no-untyped-def]
        max_attempts: int = 60,
        delay: int = 5,
    ) -> None:  # noqa: ARG002
        self.waited_for_healthy = True


class StubCloudFrontService:
    """Stub CloudFront service capturing distribution creation."""

    def __init__(self) -> None:
        self.distribution_created = False
        self.waited_for_deployed = False

    def create_distribution_with_alb_origin(
        self,
        alb_dns_name: str,  # noqa: ARG002
        caller_reference: str,  # noqa: ARG002
        **kwargs,  # type: ignore[no-untyped-def]  # noqa: ARG002
    ):  # type: ignore[no-untyped-def]
        self.distribution_created = True
        return {
            "Distribution": {
                "Id": "E1234567890ABC",
                "DomainName": "d111111abcdef8.cloudfront.net",
                "Status": "InProgress",
            },
            "ETag": "E2QWRUHAPOMQZL",
        }

    def wait_for_deployed(
        self,
        distribution_id: str,  # noqa: ARG002
        max_attempts: int = 60,  # noqa: ARG002
        delay: int = 30,  # noqa: ARG002
    ) -> None:
        self.waited_for_deployed = True


class StubUserDataGenerator:
    """Stub user data generator."""

    def generate(self, config) -> str:  # type: ignore[no-untyped-def]  # noqa: ARG002
        return "#!/bin/bash\necho 'UserData script'"


__all__ = [
    "StubALBService",
    "StubCloudFrontService",
    "StubEC2Service",
    "StubEFSService",
    "StubIAMService",
    "StubSecurityGroupService",
    "StubStateManager",
    "StubUserDataGenerator",
    "StubVPCService",
]
