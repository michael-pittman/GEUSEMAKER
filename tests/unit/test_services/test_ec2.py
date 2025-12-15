"""Tests for EC2 service AMI selection."""

from __future__ import annotations

import pytest
from moto import mock_aws
from moto.core import DEFAULT_ACCOUNT_ID
from moto.ec2.models import ec2_backends

from geusemaker.infra import AWSClientFactory
from geusemaker.services.ec2 import EC2Service


def _add_image(
    name: str,
    architecture: str,
    creation_date: str = "2025-01-01T00:00:00.000Z",
) -> str:
    backend = ec2_backends[DEFAULT_ACCOUNT_ID]["us-east-1"]
    image = backend.register_image(name=name)
    image.architecture = architecture
    image.creation_date = creation_date
    image.owner_alias = "amazon"
    return image.id


@mock_aws
def test_get_latest_dlami_returns_newest_match() -> None:
    service = EC2Service(AWSClientFactory(), region="us-east-1")
    older = _add_image(
        "Deep Learning Base GPU AMI (Ubuntu 22.04) 2024.01",
        architecture="x86_64",
        creation_date="2024-01-01T00:00:00.000Z",
    )
    newer = _add_image(
        "Deep Learning Base GPU AMI (Ubuntu 22.04) 2025.01",
        architecture="x86_64",
        creation_date="2025-01-01T00:00:00.000Z",
    )

    ami_id = service.get_latest_dlami(
        os_type="ubuntu-22.04",
        architecture="x86_64",
        ami_type="base",
    )

    assert ami_id == newer
    assert ami_id != older


@mock_aws
def test_get_latest_dlami_honors_architecture_filter() -> None:
    service = EC2Service(AWSClientFactory(), region="us-east-1")
    _add_image(
        "Deep Learning Base GPU AMI (Ubuntu 24.04) x86",
        architecture="x86_64",
    )
    arm_image = _add_image(
        "Deep Learning Base GPU AMI (Ubuntu 24.04) arm",
        architecture="arm64",
    )

    ami_id = service.get_latest_dlami(
        os_type="ubuntu-24.04",
        architecture="arm64",
        ami_type="base",
    )

    assert ami_id == arm_image


@mock_aws
def test_get_latest_dlami_prefers_cpu_patterns_for_cpu_instance_types() -> None:
    service = EC2Service(AWSClientFactory(), region="us-east-1")
    gpu_image = _add_image(
        "Deep Learning Base GPU AMI (Ubuntu 22.04) 2025.01",
        architecture="x86_64",
        creation_date="2025-01-01T00:00:00.000Z",
    )
    cpu_image = _add_image(
        "Deep Learning Base AMI (Ubuntu 22.04) 2025.02",
        architecture="x86_64",
        creation_date="2025-02-01T00:00:00.000Z",
    )

    ami_id = service.get_latest_dlami(
        os_type="ubuntu-22.04",
        architecture="x86_64",
        ami_type="base",
        instance_type="t3.medium",
    )

    assert ami_id == cpu_image
    assert ami_id != gpu_image


@mock_aws
def test_get_latest_dlami_prefers_gpu_patterns_for_gpu_instance_types() -> None:
    service = EC2Service(AWSClientFactory(), region="us-east-1")
    cpu_image = _add_image(
        "Deep Learning AMI CPU TensorFlow (Ubuntu 22.04) 2025.02",
        architecture="x86_64",
        creation_date="2025-02-01T00:00:00.000Z",
    )
    gpu_image = _add_image(
        "Deep Learning AMI GPU TensorFlow (Ubuntu 22.04) 2025.01",
        architecture="x86_64",
        creation_date="2025-01-01T00:00:00.000Z",
    )

    ami_id = service.get_latest_dlami(
        os_type="ubuntu-22.04",
        architecture="x86_64",
        ami_type="tensorflow",
        instance_type="g5.xlarge",
    )

    assert ami_id == gpu_image
    assert ami_id != cpu_image


@mock_aws
def test_get_latest_dlami_uses_broader_base_pattern_when_needed() -> None:
    service = EC2Service(AWSClientFactory(), region="us-east-1")
    oss_image = _add_image(
        "Deep Learning Base OSS Nvidia Driver AMI (Ubuntu 22.04) 2025.03",
        architecture="x86_64",
        creation_date="2025-03-01T00:00:00.000Z",
    )

    ami_id = service.get_latest_dlami(
        os_type="ubuntu-22.04",
        architecture="x86_64",
        ami_type="base",
        instance_type="t3.medium",
    )

    assert ami_id == oss_image


@mock_aws
def test_get_latest_dlami_respects_ami_type_patterns() -> None:
    service = EC2Service(AWSClientFactory(), region="us-east-1")
    _add_image(
        "Deep Learning Base GPU AMI (Amazon Linux 2023) base",
        architecture="x86_64",
    )
    pytorch_image = _add_image(
        "Deep Learning AMI GPU PyTorch (Amazon Linux 2023) 2025.01",
        architecture="x86_64",
    )

    ami_id = service.get_latest_dlami(
        os_type="amazon-linux-2023",
        architecture="x86_64",
        ami_type="pytorch",
    )

    assert ami_id == pytorch_image


@mock_aws
def test_get_latest_dlami_raises_when_missing() -> None:
    service = EC2Service(AWSClientFactory(), region="us-east-1")

    with pytest.raises(RuntimeError, match="No Deep Learning AMI found"):
        service.get_latest_dlami(
            os_type="amazon-linux-2",
            architecture="x86_64",
            ami_type="tensorflow",
        )


@mock_aws
def test_get_latest_ami_uses_default_dlami() -> None:
    service = EC2Service(AWSClientFactory(), region="us-east-1")
    expected = _add_image(
        "Deep Learning Base GPU AMI (Ubuntu 22.04) default",
        architecture="x86_64",
    )

    assert service.get_latest_ami() == expected


@mock_aws
def test_validate_ami_returns_true_for_available_ami() -> None:
    """Test that validate_ami returns True for available AMIs."""
    service = EC2Service(AWSClientFactory(), region="us-east-1")
    ami_id = _add_image(
        "Test AMI",
        architecture="x86_64",
    )

    assert service.validate_ami(ami_id) is True


@mock_aws
def test_validate_ami_returns_false_for_nonexistent_ami() -> None:
    """Test that validate_ami returns False for non-existent AMIs."""
    service = EC2Service(AWSClientFactory(), region="us-east-1")

    assert service.validate_ami("ami-nonexistent123") is False


@mock_aws
def test_validate_ami_returns_false_for_invalid_ami_id() -> None:
    """Test that validate_ami returns False for invalid AMI IDs."""
    service = EC2Service(AWSClientFactory(), region="us-east-1")

    assert service.validate_ami("invalid-ami-id") is False


@mock_aws
def test_get_latest_dlami_uses_direct_lookup_for_al2023_base() -> None:
    """Test that get_latest_dlami uses direct AMI lookup from DLAMI_BASE."""
    service = EC2Service(AWSClientFactory(), region="us-east-1")

    # Add the mapped AMI from DLAMI_BASE to moto backend
    mapped_ami = "ami-00a3a6192ba06e9ae"  # From DLAMI_BASE
    backend = ec2_backends[DEFAULT_ACCOUNT_ID]["us-east-1"]
    image = backend.register_image(name="Deep Learning Base AMI with Single CUDA (Amazon Linux 2023)")
    image.id = mapped_ami  # Set the specific AMI ID
    image.architecture = "x86_64"
    image.owner_alias = "amazon"

    # Should return the mapped AMI directly without pattern search
    ami_id = service.get_latest_dlami(
        os_type="amazon-linux-2023",
        architecture="x86_64",
        ami_type="base",
    )

    assert ami_id == mapped_ami


@mock_aws
def test_get_latest_dlami_uses_direct_lookup_for_arm64() -> None:
    """Test that get_latest_dlami uses correct ARM64 AMI from DLAMI_BASE."""
    service = EC2Service(AWSClientFactory(), region="us-east-1")

    # Add the mapped ARM64 AMI from DLAMI_BASE to moto backend
    mapped_ami = "ami-0f7f69448b947f02e"  # From DLAMI_BASE
    backend = ec2_backends[DEFAULT_ACCOUNT_ID]["us-east-1"]
    image = backend.register_image(name="Deep Learning ARM64 Base AMI with Single CUDA (Amazon Linux 2023)")
    image.id = mapped_ami  # Set the specific AMI ID
    image.architecture = "arm64"
    image.owner_alias = "amazon"

    # Should return the mapped ARM64 AMI directly
    ami_id = service.get_latest_dlami(
        os_type="amazon-linux-2023",
        architecture="arm64",
        ami_type="base",
    )

    assert ami_id == mapped_ami


@mock_aws
def test_get_latest_dlami_falls_back_to_pattern_search_when_mapping_unavailable() -> None:
    """Test that get_latest_dlami falls back to pattern search when mapped AMI is not available."""
    service = EC2Service(AWSClientFactory(), region="us-east-1")

    # Don't add the mapped AMI, but add a matching pattern-based AMI
    fallback_ami = _add_image(
        "Deep Learning Base GPU AMI (Amazon Linux 2023) 2025.01",
        architecture="x86_64",
    )

    # Should fall back to pattern search since mapped AMI doesn't exist
    ami_id = service.get_latest_dlami(
        os_type="amazon-linux-2023",
        architecture="x86_64",
        ami_type="base",
    )

    assert ami_id == fallback_ami


@mock_aws
def test_get_latest_dlami_falls_back_for_unmapped_os() -> None:
    """Test that get_latest_dlami uses pattern search for OS types not in DLAMI_BASE."""
    service = EC2Service(AWSClientFactory(), region="us-east-1")

    # Add Ubuntu 24.04 AMI (not in DLAMI_BASE)
    ubuntu_ami = _add_image(
        "Deep Learning Base GPU AMI (Ubuntu 24.04) 2025.01",
        architecture="x86_64",
    )

    # Should use pattern search since ubuntu-24.04 is not in DLAMI_BASE
    ami_id = service.get_latest_dlami(
        os_type="ubuntu-24.04",
        architecture="x86_64",
        ami_type="base",
    )

    assert ami_id == ubuntu_ami


@mock_aws
def test_get_latest_dlami_falls_back_for_non_base_ami_type() -> None:
    """Test that get_latest_dlami uses pattern search for non-base AMI types."""
    service = EC2Service(AWSClientFactory(), region="us-east-1")

    # Add PyTorch AMI
    pytorch_ami = _add_image(
        "Deep Learning AMI GPU PyTorch (Amazon Linux 2023) 2025.01",
        architecture="x86_64",
    )

    # Should use pattern search since ami_type is not "base"
    ami_id = service.get_latest_dlami(
        os_type="amazon-linux-2023",
        architecture="x86_64",
        ami_type="pytorch",
    )

    assert ami_id == pytorch_ami


@mock_aws
def test_get_latest_dlami_uses_dlami_base_for_all_instances() -> None:
    """Test that all instances (CPU and GPU) use the same AMIs from DLAMI_BASE."""
    service = EC2Service(AWSClientFactory(), region="us-east-1")

    # Register the AMIs from DLAMI_BASE
    ami_al2023_x86 = "ami-00a3a6192ba06e9ae"
    ami_al2023_arm = "ami-0f7f69448b947f02e"
    ami_ubuntu_x86 = "ami-0193ca8306cf64925"
    ami_ubuntu_arm = "ami-08f9f6bb4d8be1db8"

    backend = ec2_backends[DEFAULT_ACCOUNT_ID]["us-east-1"]

    # Amazon Linux 2023 AMIs
    img_al2023_x86 = backend.register_image(name="Deep Learning Base AMI with Single CUDA (Amazon Linux 2023) x86_64")
    img_al2023_x86.id = ami_al2023_x86
    img_al2023_x86.architecture = "x86_64"
    img_al2023_x86.owner_alias = "amazon"

    img_al2023_arm = backend.register_image(name="Deep Learning ARM64 Base AMI with Single CUDA (Amazon Linux 2023)")
    img_al2023_arm.id = ami_al2023_arm
    img_al2023_arm.architecture = "arm64"
    img_al2023_arm.owner_alias = "amazon"

    # Ubuntu 22.04 AMIs
    img_ubuntu_x86 = backend.register_image(name="Deep Learning Base AMI with Single CUDA (Ubuntu 22.04) x86_64")
    img_ubuntu_x86.id = ami_ubuntu_x86
    img_ubuntu_x86.architecture = "x86_64"
    img_ubuntu_x86.owner_alias = "amazon"

    img_ubuntu_arm = backend.register_image(name="Deep Learning ARM64 Base AMI with Single CUDA (Ubuntu 22.04)")
    img_ubuntu_arm.id = ami_ubuntu_arm
    img_ubuntu_arm.architecture = "arm64"
    img_ubuntu_arm.owner_alias = "amazon"

    # Test Amazon Linux 2023 x86_64 with GPU instance
    ami = service.get_latest_dlami(
        os_type="amazon-linux-2023",
        architecture="x86_64",
        ami_type="base",
        instance_type="g5.xlarge",  # GPU instance
    )
    assert ami == ami_al2023_x86

    # Test Amazon Linux 2023 x86_64 with CPU instance (same AMI)
    ami = service.get_latest_dlami(
        os_type="amazon-linux-2023",
        architecture="x86_64",
        ami_type="base",
        instance_type="t3.medium",  # CPU instance
    )
    assert ami == ami_al2023_x86

    # Test Ubuntu 22.04 x86_64 with GPU instance
    ami = service.get_latest_dlami(
        os_type="ubuntu-22.04",
        architecture="x86_64",
        ami_type="base",
        instance_type="p3.2xlarge",  # GPU instance
    )
    assert ami == ami_ubuntu_x86

    # Test Ubuntu 22.04 x86_64 with CPU instance (same AMI)
    ami = service.get_latest_dlami(
        os_type="ubuntu-22.04",
        architecture="x86_64",
        ami_type="base",
        instance_type="c5.xlarge",  # CPU instance
    )
    assert ami == ami_ubuntu_x86


# ===================================
# GPU Instance Support Tests
# ===================================


def test_gpu_instance_specs_returns_correct_info() -> None:
    """Test that get_gpu_instance_specs returns correct GPU specifications."""
    # Test G4dn instance (NVIDIA T4)
    specs = EC2Service.get_gpu_instance_specs("g4dn.xlarge")
    assert specs is not None
    assert specs["gpu"] == "T4"
    assert specs["gpu_count"] == 1
    assert specs["gpu_memory_gb"] == 16
    assert specs["vcpu"] == 4
    assert specs["memory_gb"] == 16

    # Test G5 instance (NVIDIA A10G)
    specs = EC2Service.get_gpu_instance_specs("g5.xlarge")
    assert specs is not None
    assert specs["gpu"] == "A10G"
    assert specs["gpu_count"] == 1
    assert specs["gpu_memory_gb"] == 24
    assert specs["vcpu"] == 4
    assert specs["memory_gb"] == 16

    # Test P3 instance (NVIDIA V100)
    specs = EC2Service.get_gpu_instance_specs("p3.2xlarge")
    assert specs is not None
    assert specs["gpu"] == "V100"
    assert specs["gpu_count"] == 1
    assert specs["gpu_memory_gb"] == 16
    assert specs["vcpu"] == 8
    assert specs["memory_gb"] == 61


def test_gpu_instance_specs_returns_none_for_unknown_type() -> None:
    """Test that get_gpu_instance_specs returns None for unknown instance types."""
    assert EC2Service.get_gpu_instance_specs("t3.medium") is None
    assert EC2Service.get_gpu_instance_specs("g9.xlarge") is None
    assert EC2Service.get_gpu_instance_specs("unknown.type") is None


def test_validate_gpu_instance_type_accepts_supported_types() -> None:
    """Test that validate_gpu_instance_type accepts all supported GPU types."""
    # Test G4dn series
    is_valid, error = EC2Service.validate_gpu_instance_type("g4dn.xlarge")
    assert is_valid is True
    assert error is None

    is_valid, error = EC2Service.validate_gpu_instance_type("g4dn.12xlarge")
    assert is_valid is True
    assert error is None

    # Test G5 series
    is_valid, error = EC2Service.validate_gpu_instance_type("g5.xlarge")
    assert is_valid is True
    assert error is None

    is_valid, error = EC2Service.validate_gpu_instance_type("g5.48xlarge")
    assert is_valid is True
    assert error is None

    # Test P3 series
    is_valid, error = EC2Service.validate_gpu_instance_type("p3.2xlarge")
    assert is_valid is True
    assert error is None

    # Test P4 series
    is_valid, error = EC2Service.validate_gpu_instance_type("p4d.24xlarge")
    assert is_valid is True
    assert error is None

    # Test P5 series
    is_valid, error = EC2Service.validate_gpu_instance_type("p5.48xlarge")
    assert is_valid is True
    assert error is None


def test_validate_gpu_instance_type_rejects_cpu_instances() -> None:
    """Test that validate_gpu_instance_type rejects CPU-only instance types."""
    is_valid, error = EC2Service.validate_gpu_instance_type("t3.medium")
    assert is_valid is False
    assert "does not have GPU support" in error

    is_valid, error = EC2Service.validate_gpu_instance_type("c5.xlarge")
    assert is_valid is False
    assert "does not have GPU support" in error

    is_valid, error = EC2Service.validate_gpu_instance_type("m5.large")
    assert is_valid is False
    assert "does not have GPU support" in error


def test_validate_gpu_instance_type_rejects_unknown_gpu_types() -> None:
    """Test that validate_gpu_instance_type rejects GPU instances not in the mapping."""
    # Hypothetical GPU instance types that might exist but aren't in our mapping
    is_valid, error = EC2Service.validate_gpu_instance_type("g6.xlarge")
    assert is_valid is False
    assert "not in the supported list" in error
    assert "g4dn.xlarge" in error  # Should suggest supported types

    is_valid, error = EC2Service.validate_gpu_instance_type("p6.48xlarge")
    assert is_valid is False
    assert "not in the supported list" in error


def test_is_gpu_instance_type_detects_gpu_families() -> None:
    """Test that _is_gpu_instance_type correctly detects GPU instance families."""
    # GPU families
    assert EC2Service._is_gpu_instance_type("g4dn.xlarge") is True
    assert EC2Service._is_gpu_instance_type("g5.xlarge") is True
    assert EC2Service._is_gpu_instance_type("g6.xlarge") is True
    assert EC2Service._is_gpu_instance_type("p3.2xlarge") is True
    assert EC2Service._is_gpu_instance_type("p4d.24xlarge") is True
    assert EC2Service._is_gpu_instance_type("p5.48xlarge") is True
    assert EC2Service._is_gpu_instance_type("p6.48xlarge") is True
    assert EC2Service._is_gpu_instance_type("g5g.xlarge") is True

    # CPU families
    assert EC2Service._is_gpu_instance_type("t3.medium") is False
    assert EC2Service._is_gpu_instance_type("c5.xlarge") is False
    assert EC2Service._is_gpu_instance_type("m5.large") is False
    assert EC2Service._is_gpu_instance_type("r5.xlarge") is False

    # Edge cases
    assert EC2Service._is_gpu_instance_type(None) is False
    assert EC2Service._is_gpu_instance_type("") is False


@mock_aws
def test_get_latest_dlami_with_gpu_instance_type() -> None:
    """Test that get_latest_dlami successfully selects AMIs for both GPU and CPU instances."""
    service = EC2Service(AWSClientFactory(), region="us-east-1")

    # Add both GPU and CPU AMIs (both work on GPU and CPU instances)
    gpu_ami = _add_image(
        "Deep Learning Base GPU AMI (Ubuntu 22.04) 2025.01",
        architecture="x86_64",
        creation_date="2025-01-01T00:00:00.000Z",
    )
    cpu_ami = _add_image(
        "Deep Learning Base OSS Nvidia Driver AMI (Ubuntu 22.04) 2025.01",
        architecture="x86_64",
        creation_date="2025-01-01T00:00:00.000Z",
    )

    # Test with GPU instance type - should find valid AMI
    ami_id = service.get_latest_dlami(
        os_type="ubuntu-22.04",
        architecture="x86_64",
        ami_type="base",
        instance_type="g5.xlarge",  # GPU instance
    )
    # Both AMIs have NVIDIA drivers and work on GPU instances
    assert ami_id in (gpu_ami, cpu_ami)

    # Test with CPU instance type - should find valid AMI
    ami_id = service.get_latest_dlami(
        os_type="ubuntu-22.04",
        architecture="x86_64",
        ami_type="base",
        instance_type="c5.xlarge",  # CPU instance
    )
    # Both AMIs work on CPU instances (GPU drivers are dormant)
    assert ami_id in (gpu_ami, cpu_ami)
