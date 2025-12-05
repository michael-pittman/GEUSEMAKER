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
    """Test that get_latest_dlami uses direct AMI lookup for Amazon Linux 2023 base images."""
    service = EC2Service(AWSClientFactory(), region="us-east-1")

    # Add the mapped AMI to moto backend
    mapped_ami = "ami-0941ba2cd9ee2998a"
    backend = ec2_backends[DEFAULT_ACCOUNT_ID]["us-east-1"]
    image = backend.register_image(name="Amazon Linux 2023 AMI")
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
    """Test that get_latest_dlami uses correct ARM64 AMI from mapping."""
    service = EC2Service(AWSClientFactory(), region="us-east-1")

    # Add the mapped ARM64 AMI to moto backend
    mapped_ami = "ami-08742254cf19c5488"
    backend = ec2_backends[DEFAULT_ACCOUNT_ID]["us-east-1"]
    image = backend.register_image(name="Amazon Linux 2023 AMI ARM64")
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
def test_get_latest_dlami_falls_back_for_non_al2023_os() -> None:
    """Test that get_latest_dlami uses pattern search for non-AL2023 operating systems."""
    service = EC2Service(AWSClientFactory(), region="us-east-1")

    # Add Ubuntu AMI
    ubuntu_ami = _add_image(
        "Deep Learning Base GPU AMI (Ubuntu 22.04) 2025.01",
        architecture="x86_64",
    )

    # Should use pattern search, not direct lookup
    ami_id = service.get_latest_dlami(
        os_type="ubuntu-22.04",
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
def test_get_latest_dlami_works_in_different_regions() -> None:
    """Test that get_latest_dlami uses region-specific AMI mappings."""
    # Test us-west-2
    service_west = EC2Service(AWSClientFactory(), region="us-west-2")
    mapped_ami_west = "ami-019056869a13971ff"

    backend_west = ec2_backends[DEFAULT_ACCOUNT_ID]["us-west-2"]
    image_west = backend_west.register_image(name="Amazon Linux 2023 AMI")
    image_west.id = mapped_ami_west  # Set the specific AMI ID
    image_west.architecture = "x86_64"
    image_west.owner_alias = "amazon"

    ami_id_west = service_west.get_latest_dlami(
        os_type="amazon-linux-2023",
        architecture="x86_64",
        ami_type="base",
    )

    assert ami_id_west == mapped_ami_west
