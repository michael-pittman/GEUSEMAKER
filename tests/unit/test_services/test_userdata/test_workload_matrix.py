"""Tests for the tier/workload compatibility matrix in UserData generation.

Topology (`tier`) controls networking/CDN shape; workload (`cpu`/`gpu`) controls the
NVIDIA runtime, GPU Docker images, and GPU model preload. Legacy configs without an
explicit workload infer `gpu` only when `tier == "gpu"`.
"""

from __future__ import annotations

import pytest

from geusemaker.models.userdata import UserDataConfig
from geusemaker.services.userdata import UserDataGenerator

# ruff: noqa: S106 - Test fixtures use hardcoded passwords for testing only


def _render(tier: str, workload: str | None) -> str:
    """Render a UserData script for the given tier/workload combination."""
    config = UserDataConfig(
        efs_id="fs-12345678",
        efs_dns="fs-12345678.efs.us-east-1.amazonaws.com",
        tier=tier,  # type: ignore[arg-type]
        workload=workload,  # type: ignore[arg-type]
        stack_name="test-stack",
        region="us-east-1",
        postgres_password="test-password-123",
    )
    return UserDataGenerator().generate(config)


def _assert_gpu_present(script: str) -> None:
    assert "DOCKER_RUNTIME=nvidia" in script
    assert "nvidia-container-toolkit" in script
    assert "driver: nvidia" in script


def _assert_gpu_absent(script: str) -> None:
    assert "DOCKER_RUNTIME=nvidia" not in script
    assert "DOCKER_RUNTIME=runc" in script
    assert "nvidia-container-toolkit" not in script
    assert "driver: nvidia" not in script


@pytest.mark.parametrize(
    ("tier", "workload"),
    [
        ("dev", "gpu"),
        ("automation", "gpu"),
        ("gpu", "gpu"),
    ],
)
def test_gpu_workload_includes_nvidia(tier: str, workload: str) -> None:
    """Any topology with a GPU workload must ship the NVIDIA runtime + GPU sections."""
    _assert_gpu_present(_render(tier, workload))


@pytest.mark.parametrize(
    ("tier", "workload"),
    [
        ("dev", "cpu"),
        ("automation", "cpu"),
        ("gpu", "cpu"),
    ],
)
def test_cpu_workload_excludes_nvidia(tier: str, workload: str) -> None:
    """Any topology with a CPU workload must not ship NVIDIA/GPU sections."""
    _assert_gpu_absent(_render(tier, workload))


def test_legacy_gpu_tier_infers_gpu_workload() -> None:
    """Legacy config: tier=gpu with no workload infers gpu -> NVIDIA present."""
    _assert_gpu_present(_render("gpu", None))


def test_legacy_dev_tier_infers_cpu_workload() -> None:
    """Legacy config: tier=dev with no workload infers cpu -> no NVIDIA."""
    _assert_gpu_absent(_render("dev", None))


def test_config_resolves_workload_in_model_dump() -> None:
    """The resolved workload string must be present in model_dump for template gating."""
    gpu_inferred = UserDataConfig(
        efs_id="fs-12345678",
        efs_dns="fs-12345678.efs.us-east-1.amazonaws.com",
        tier="gpu",
        stack_name="test-stack",
        region="us-east-1",
        postgres_password="test-password-123",
    )
    assert gpu_inferred.model_dump()["workload"] == "gpu"

    cpu_inferred = UserDataConfig(
        efs_id="fs-12345678",
        efs_dns="fs-12345678.efs.us-east-1.amazonaws.com",
        tier="dev",
        stack_name="test-stack",
        region="us-east-1",
        postgres_password="test-password-123",
    )
    assert cpu_inferred.model_dump()["workload"] == "cpu"

    explicit = UserDataConfig(
        efs_id="fs-12345678",
        efs_dns="fs-12345678.efs.us-east-1.amazonaws.com",
        tier="gpu",
        workload="cpu",
        stack_name="test-stack",
        region="us-east-1",
        postgres_password="test-password-123",
    )
    assert explicit.model_dump()["workload"] == "cpu"
