"""Tests for IAM service."""

from __future__ import annotations

import pytest
from moto import mock_aws

from geusemaker.infra import AWSClientFactory
from geusemaker.services.iam import IAMService


@mock_aws
def test_create_efs_mount_role_returns_arn() -> None:
    """Test that create_efs_mount_role creates a role and returns ARN."""
    svc = IAMService(AWSClientFactory(), region="us-east-1")
    tags = [
        {"Key": "Name", "Value": "test-role"},
        {"Key": "Stack", "Value": "test-stack"},
    ]

    role_arn = svc.create_efs_mount_role("test-efs-role", tags)

    assert role_arn.startswith("arn:aws:iam::")
    assert "role/test-efs-role" in role_arn


@mock_aws
def test_create_efs_mount_role_has_required_permissions() -> None:
    """Test that created role has EFS mount permissions."""
    svc = IAMService(AWSClientFactory(), region="us-east-1")
    tags = [{"Key": "Name", "Value": "test-role"}]

    svc.create_efs_mount_role("test-efs-role", tags)

    # Verify role exists and has correct policy
    role = svc.get_role("test-efs-role")
    assert role["RoleName"] == "test-efs-role"
    assert "GeuseMaker EFS mount role" in role["Description"]


@mock_aws
def test_create_instance_profile_returns_arn() -> None:
    """Test that create_instance_profile creates a profile and returns ARN."""
    svc = IAMService(AWSClientFactory(), region="us-east-1")
    tags = [
        {"Key": "Name", "Value": "test-profile"},
        {"Key": "Stack", "Value": "test-stack"},
    ]

    profile_arn = svc.create_instance_profile("test-instance-profile", tags)

    assert profile_arn.startswith("arn:aws:iam::")
    assert "instance-profile/test-instance-profile" in profile_arn


@mock_aws
def test_attach_role_to_profile_succeeds() -> None:
    """Test that attach_role_to_profile successfully attaches role to profile."""
    svc = IAMService(AWSClientFactory(), region="us-east-1")

    # Create role and profile
    svc.create_efs_mount_role("test-role", [])
    svc.create_instance_profile("test-profile", [])

    # Attach role to profile (should not raise)
    svc.attach_role_to_profile("test-profile", "test-role")

    # Verify attachment
    profile = svc.get_instance_profile("test-profile")
    assert len(profile["Roles"]) == 1
    assert profile["Roles"][0]["RoleName"] == "test-role"


@mock_aws
def test_wait_for_instance_profile_succeeds_when_profile_exists() -> None:
    """Test wait_for_instance_profile completes when profile is available with role attached."""
    svc = IAMService(AWSClientFactory(), region="us-east-1")

    # Create role, profile, and attach
    svc.create_efs_mount_role("test-role", [])
    svc.create_instance_profile("test-profile", [])
    svc.attach_role_to_profile("test-profile", "test-role")

    # Should complete without error when role is attached
    svc.wait_for_instance_profile("test-profile", "test-role", max_attempts=5, delay=0)


@mock_aws
def test_wait_for_instance_profile_raises_on_nonexistent_profile() -> None:
    """Test wait_for_instance_profile raises error for non-existent profile."""
    svc = IAMService(AWSClientFactory(), region="us-east-1")

    with pytest.raises(RuntimeError, match="AWS call failed.*NoSuchEntity"):
        svc.wait_for_instance_profile("nonexistent-profile", "test-role", max_attempts=1, delay=0)


@mock_aws
def test_wait_for_instance_profile_verifies_role_attachment() -> None:
    """Test wait_for_instance_profile verifies that the expected role is attached."""
    svc = IAMService(AWSClientFactory(), region="us-east-1")

    # Create role and profile but don't attach - should timeout waiting for attachment
    svc.create_efs_mount_role("test-role", [])
    svc.create_instance_profile("test-profile", [])

    # Should raise because role is not attached
    with pytest.raises(RuntimeError, match="role test-role not attached"):
        svc.wait_for_instance_profile("test-profile", "test-role", max_attempts=2, delay=0)


@mock_aws
def test_delete_instance_profile_removes_profile() -> None:
    """Test delete_instance_profile removes the profile."""
    svc = IAMService(AWSClientFactory(), region="us-east-1")

    # Create role, profile, and attach
    svc.create_efs_mount_role("test-role", [])
    svc.create_instance_profile("test-profile", [])
    svc.attach_role_to_profile("test-profile", "test-role")

    # Delete profile (should detach role and delete)
    svc.delete_instance_profile("test-profile", "test-role")

    # Verify profile is gone
    with pytest.raises(RuntimeError, match="AWS call failed"):
        svc.get_instance_profile("test-profile")


@mock_aws
def test_delete_role_removes_role_and_policies() -> None:
    """Test delete_role removes role and inline policies."""
    svc = IAMService(AWSClientFactory(), region="us-east-1")

    # Create role (which includes inline policy)
    svc.create_efs_mount_role("test-role", [])

    # Delete role (should remove inline policies first)
    svc.delete_role("test-role")

    # Verify role is gone
    with pytest.raises(RuntimeError, match="AWS call failed"):
        svc.get_role("test-role")


@mock_aws
def test_delete_nonexistent_profile_does_not_raise() -> None:
    """Test delete_instance_profile handles non-existent profile gracefully."""
    svc = IAMService(AWSClientFactory(), region="us-east-1")

    # Should not raise even though profile doesn't exist
    svc.delete_instance_profile("nonexistent-profile")


@mock_aws
def test_delete_nonexistent_role_does_not_raise() -> None:
    """Test delete_role handles non-existent role gracefully."""
    svc = IAMService(AWSClientFactory(), region="us-east-1")

    # Should not raise even though role doesn't exist
    svc.delete_role("nonexistent-role")


@mock_aws
def test_full_iam_lifecycle_for_efs_mount() -> None:
    """Test complete IAM lifecycle: create role and profile, attach, then cleanup."""
    svc = IAMService(AWSClientFactory(), region="us-east-1")

    # Create IAM resources
    role_name = "test-stack-efs-role"
    profile_name = "test-stack-profile"
    tags = [
        {"Key": "Stack", "Value": "test-stack"},
        {"Key": "Tier", "Value": "dev"},
    ]

    role_arn = svc.create_efs_mount_role(role_name, tags)
    profile_arn = svc.create_instance_profile(profile_name, tags)
    svc.attach_role_to_profile(profile_name, role_name)
    svc.wait_for_instance_profile(profile_name, role_name, max_attempts=5, delay=0)

    # Verify creation
    assert role_arn.startswith("arn:aws:iam::")
    assert profile_arn.startswith("arn:aws:iam::")

    role = svc.get_role(role_name)
    profile = svc.get_instance_profile(profile_name)

    assert role["RoleName"] == role_name
    assert profile["InstanceProfileName"] == profile_name
    assert len(profile["Roles"]) == 1
    assert profile["Roles"][0]["RoleName"] == role_name

    # Cleanup
    svc.delete_instance_profile(profile_name, role_name)
    svc.delete_role(role_name)

    # Verify deletion
    with pytest.raises(RuntimeError, match="AWS call failed"):
        svc.get_instance_profile(profile_name)

    with pytest.raises(RuntimeError, match="AWS call failed"):
        svc.get_role(role_name)
