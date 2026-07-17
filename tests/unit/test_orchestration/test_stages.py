"""Focused unit tests for the extracted Tier1 stage helper functions.

These exercise the pure/computational logic moved out of
``Tier1Orchestrator`` into ``geusemaker.orchestration.stages`` during the
Phase 4 decomposition. They assert behavior parity with the coordinator's
former inline implementations.
"""

from __future__ import annotations

import gzip
import secrets

import pytest

from geusemaker.models import DeploymentConfig
from geusemaker.orchestration.errors import OrchestrationError
from geusemaker.orchestration.stages import (
    build_block_device_mappings,
    build_userdata_config,
    compress_userdata,
    detect_root_device,
    resolve_ami,
)
from geusemaker.orchestration.stages.ami import MIN_ROOT_GB


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
