"""Tests for EFS service."""

from __future__ import annotations

import pytest
from moto import mock_aws

from geusemaker.infra import AWSClientFactory
from geusemaker.services.efs import EFSService


@mock_aws
def test_create_filesystem_returns_fs_id() -> None:
    """Test that create_filesystem returns a filesystem ID."""
    svc = EFSService(AWSClientFactory(), region="us-east-1")
    result = svc.create_filesystem(tags=[{"Key": "Name", "Value": "test-fs"}])

    assert "FileSystemId" in result
    assert result["FileSystemId"].startswith("fs-")


@mock_aws
def test_wait_for_available_succeeds_when_fs_becomes_available() -> None:
    """Test wait_for_available completes when filesystem reaches available state."""
    svc = EFSService(AWSClientFactory(), region="us-east-1")

    # Create filesystem (moto will immediately set it to available)
    result = svc.create_filesystem(tags=[{"Key": "Name", "Value": "test-fs"}])
    fs_id = result["FileSystemId"]

    # Should complete without error since moto sets state to available immediately
    svc.wait_for_available(fs_id, max_attempts=5, delay=0)


@mock_aws
def test_wait_for_available_raises_on_nonexistent_fs() -> None:
    """Test wait_for_available raises error for non-existent filesystem."""
    svc = EFSService(AWSClientFactory(), region="us-east-1")

    with pytest.raises(RuntimeError, match="AWS call failed.*FileSystemNotFound"):
        svc.wait_for_available("fs-nonexistent", max_attempts=1, delay=0)


@mock_aws
def test_create_mount_target_returns_mt_id() -> None:
    """Test create_mount_target returns a mount target ID."""
    from moto import mock_aws as aws_mock

    with aws_mock():
        # Setup: Create VPC, subnet, and filesystem
        client_factory = AWSClientFactory()
        ec2 = client_factory.get_client("ec2", region="us-east-1")

        # Create VPC and subnet
        vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")
        vpc_id = vpc["Vpc"]["VpcId"]

        subnet = ec2.create_subnet(VpcId=vpc_id, CidrBlock="10.0.1.0/24")
        subnet_id = subnet["Subnet"]["SubnetId"]

        # Create security group
        sg = ec2.create_security_group(
            GroupName="test-sg",
            Description="Test SG",
            VpcId=vpc_id,
        )
        sg_id = sg["GroupId"]

        # Create EFS filesystem
        svc = EFSService(client_factory, region="us-east-1")
        fs = svc.create_filesystem(tags=[{"Key": "Name", "Value": "test-fs"}])
        fs_id = fs["FileSystemId"]

        # Wait for filesystem to be available
        svc.wait_for_available(fs_id, max_attempts=5, delay=0)

        # Create mount target
        mt_id = svc.create_mount_target(fs_id, subnet_id, [sg_id])

        assert mt_id.startswith("fsmt-")


@mock_aws
def test_delete_mount_target_succeeds() -> None:
    """Test delete_mount_target completes without error."""
    from moto import mock_aws as aws_mock

    with aws_mock():
        # Setup: Create VPC, subnet, filesystem, and mount target
        client_factory = AWSClientFactory()
        ec2 = client_factory.get_client("ec2", region="us-east-1")

        vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")
        vpc_id = vpc["Vpc"]["VpcId"]

        subnet = ec2.create_subnet(VpcId=vpc_id, CidrBlock="10.0.1.0/24")
        subnet_id = subnet["Subnet"]["SubnetId"]

        sg = ec2.create_security_group(
            GroupName="test-sg",
            Description="Test SG",
            VpcId=vpc_id,
        )
        sg_id = sg["GroupId"]

        svc = EFSService(client_factory, region="us-east-1")
        fs = svc.create_filesystem(tags=[{"Key": "Name", "Value": "test-fs"}])
        fs_id = fs["FileSystemId"]

        svc.wait_for_available(fs_id, max_attempts=5, delay=0)
        mt_id = svc.create_mount_target(fs_id, subnet_id, [sg_id])

        # Should complete without error
        svc.delete_mount_target(mt_id)


@mock_aws
def test_delete_filesystem_succeeds() -> None:
    """Test delete_filesystem completes without error."""
    svc = EFSService(AWSClientFactory(), region="us-east-1")

    fs = svc.create_filesystem(tags=[{"Key": "Name", "Value": "test-fs"}])
    fs_id = fs["FileSystemId"]

    # Should complete without error
    svc.delete_filesystem(fs_id)
