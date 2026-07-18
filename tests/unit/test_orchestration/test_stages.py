"""Focused unit tests for the extracted Tier1 stage helper functions.

These exercise the pure/computational logic moved out of
``Tier1Orchestrator`` into ``geusemaker.orchestration.stages`` during the
Phase 4 decomposition. They assert behavior parity with the coordinator's
former inline implementations.
"""

from __future__ import annotations

import gzip
import secrets
from decimal import Decimal

import pytest

from geusemaker.models import DeploymentConfig
from geusemaker.models.compute import InstanceSelection, SavingsComparison
from geusemaker.orchestration.errors import OrchestrationError
from geusemaker.orchestration.stages import (
    build_block_device_mappings,
    build_userdata_config,
    compress_userdata,
    detect_root_device,
    launch_instance,
    resolve_ami,
)
from geusemaker.orchestration.stages.ami import MIN_ROOT_GB
from geusemaker.services.spot_automation import SpotAutomationResources


class _FakeEC2:
    """Minimal EC2 double for AMI-stage helpers."""

    def __init__(self, *, root_error: bool = False) -> None:
        self.dlami_args: dict[str, object] | None = None
        self._root_error = root_error

    def get_latest_dlami(self, **kwargs: object) -> str:
        self.dlami_args = kwargs
        return "ami-autoselected"

    def get_root_device_name(self, ami_id: str) -> str:  # noqa: ARG002
        if self._root_error:
            raise RuntimeError("boom")
        return "/dev/sda1"


def test_resolve_ami_prefers_custom_ami() -> None:
    ec2 = _FakeEC2()
    config = DeploymentConfig(stack_name="s", tier="dev", ami_id="ami-custom")

    assert resolve_ami(ec2, config) == "ami-custom"
    assert ec2.dlami_args is None  # auto-select not consulted


def test_resolve_ami_auto_selects_when_no_override() -> None:
    ec2 = _FakeEC2()
    config = DeploymentConfig(stack_name="s", tier="dev")

    assert resolve_ami(ec2, config) == "ami-autoselected"
    assert ec2.dlami_args is not None
    assert ec2.dlami_args["instance_type"] == config.instance_type


def test_detect_root_device_returns_ami_value() -> None:
    assert detect_root_device(_FakeEC2(), "ami-x") == "/dev/sda1"


def test_detect_root_device_defaults_on_error() -> None:
    assert detect_root_device(_FakeEC2(root_error=True), "ami-x") == "/dev/xvda"


def test_build_block_device_mappings_shape() -> None:
    mappings = build_block_device_mappings("/dev/xvda")

    assert mappings == [
        {
            "DeviceName": "/dev/xvda",
            "Ebs": {
                "VolumeSize": MIN_ROOT_GB,
                "VolumeType": "gp3",
                "DeleteOnTermination": True,
                "Encrypted": True,
            },
        },
    ]


def test_compress_userdata_roundtrips() -> None:
    payload = compress_userdata("#!/bin/bash\necho hi\n")

    assert gzip.decompress(payload).decode("utf-8") == "#!/bin/bash\necho hi\n"


def test_compress_userdata_rejects_oversized_script() -> None:
    # Incompressible random content large enough to exceed the 16KB gzip cap.
    huge = secrets.token_urlsafe(64_000)

    with pytest.raises(OrchestrationError, match="exceeds the AWS limit"):
        compress_userdata(huge)


def test_build_userdata_config_dev_self_signed_enables_https() -> None:
    config = DeploymentConfig(
        stack_name="s",
        tier="dev",
        enable_https=True,
        tier1_use_self_signed=True,
    )

    ud = build_userdata_config(config, "us-east-1", "fs-123", "10.0.0.5", "pw")

    assert ud.enable_https is True
    assert ud.efs_dns == "fs-123.efs.us-east-1.amazonaws.com"
    assert ud.workload == config.effective_workload
    assert ud.n8n_external_host is None  # Tier 1 host unknown until launch


def test_build_userdata_config_spot_protection_names() -> None:
    config = DeploymentConfig(stack_name="mystack", tier="gpu")

    ud = build_userdata_config(
        config,
        "us-east-1",
        "fs-1",
        "10.0.0.5",
        "pw",
        spot_protection_enabled=True,
    )

    assert ud.spot_protection_enabled is True
    assert ud.spot_auto_scaling_group_name == "mystack-spot-asg"
    assert ud.spot_lease_table_name == "mystack-spot-lease"


class _StubEC2ForLaunch:
    def wait_for_running(self, instance_id: str) -> None:  # noqa: ARG002
        return None

    def describe_instance(self, instance_id: str) -> dict:  # noqa: ARG002
        return {"PublicIpAddress": "1.2.3.4", "PrivateIpAddress": "10.0.2.10"}


class _CapturingSpotAutomation:
    def __init__(self) -> None:
        self.subnet_ids: list[str] | None = None

    def create(self, *, subnet_ids: list[str], **_: object) -> SpotAutomationResources:
        self.subnet_ids = subnet_ids
        return SpotAutomationResources(
            launch_template_id="lt-1",
            auto_scaling_group_name="test-spot-asg",
            instance_id="i-123",
            log_group_name="/geusemaker/test/spot-events",
            event_rule_names=(),
            lease_table_name="test-spot-lease",
            lifecycle_hook_names=(),
            coordinator_function_name="test-spot-coordinator",
            coordinator_role_name="test-spot-coordinator",
        )


def _spot_selection(az: str) -> InstanceSelection:
    return InstanceSelection(
        instance_type="g4dn.xlarge",
        availability_zone=az,
        is_spot=True,
        price_per_hour=Decimal("0.20"),
        selection_reason="test",
        savings_vs_on_demand=SavingsComparison(
            on_demand_hourly=Decimal("0.50"),
            selected_hourly=Decimal("0.20"),
            hourly_savings=Decimal("0.30"),
            monthly_savings=Decimal("219"),
            savings_percentage=60.0,
        ),
    )


def test_spot_asg_launch_constrains_subnets_to_selected_az() -> None:
    """The production Spot ASG must launch into the selected AZ's subnet only, not all public subnets."""
    spot_automation = _CapturingSpotAutomation()
    config = DeploymentConfig(stack_name="test", tier="gpu", instance_type="g4dn.xlarge")
    vpc_info = {
        "chosen_public_subnet_id": "subnet-selected-az",
        "chosen_public_subnet_az": "us-east-1b",
        # All public subnets across AZs; the ASG must NOT spread across these.
        "public_subnet_ids": ["subnet-selected-az", "subnet-other-a", "subnet-other-c"],
    }

    info = launch_instance(
        _StubEC2ForLaunch(),  # type: ignore[arg-type]
        spot_automation,  # type: ignore[arg-type]
        config,
        vpc_info,
        "sg-1",
        b"#!/bin/bash\n",
        {"profile_name": "test-profile"},
        _spot_selection("us-east-1b"),
        "ami-123",
        [],
    )

    assert spot_automation.subnet_ids == ["subnet-selected-az"]
    assert info["instance_id"] == "i-123"
    assert info["auto_scaling_group_name"] == "test-spot-asg"
