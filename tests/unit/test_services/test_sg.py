"""Tests for SecurityGroupService."""

from moto import mock_aws

from geusemaker.infra import AWSClientFactory
from geusemaker.services import SecurityGroupService


@mock_aws
def test_ensure_https_port_adds_port_when_missing() -> None:
    """Test that ensure_https_port adds port 443 when it doesn't exist."""
    service = SecurityGroupService(AWSClientFactory(), region="us-east-1")

    # Create VPC and security group without port 443
    ec2 = service._client("ec2")
    vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")
    vpc_id = vpc["Vpc"]["VpcId"]

    sg_resp = ec2.create_security_group(
        GroupName="test-sg",
        Description="Test SG",
        VpcId=vpc_id,
    )
    sg_id = sg_resp["GroupId"]

    # Add some other ports (not 443)
    ec2.authorize_security_group_ingress(
        GroupId=sg_id,
        IpPermissions=[
            {"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
            {"IpProtocol": "tcp", "FromPort": 80, "ToPort": 80, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
        ],
    )

    # Call ensure_https_port - should add port 443
    port_added = service.ensure_https_port(sg_id)

    assert port_added is True

    # Verify port 443 was added
    sg_details = ec2.describe_security_groups(GroupIds=[sg_id])
    rules = sg_details["SecurityGroups"][0]["IpPermissions"]
    https_rule = next((r for r in rules if r.get("FromPort") == 443), None)
    assert https_rule is not None
    assert https_rule["IpProtocol"] == "tcp"
    assert https_rule["ToPort"] == 443


@mock_aws
def test_ensure_https_port_skips_when_port_exists() -> None:
    """Test that ensure_https_port returns False when port 443 already exists."""
    service = SecurityGroupService(AWSClientFactory(), region="us-east-1")

    # Create VPC and security group WITH port 443
    ec2 = service._client("ec2")
    vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")
    vpc_id = vpc["Vpc"]["VpcId"]

    sg_resp = ec2.create_security_group(
        GroupName="test-sg",
        Description="Test SG",
        VpcId=vpc_id,
    )
    sg_id = sg_resp["GroupId"]

    # Add port 443 and other ports
    ec2.authorize_security_group_ingress(
        GroupId=sg_id,
        IpPermissions=[
            {"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
            {"IpProtocol": "tcp", "FromPort": 443, "ToPort": 443, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
        ],
    )

    # Call ensure_https_port - should detect existing port
    port_added = service.ensure_https_port(sg_id)

    assert port_added is False

    # Verify only one port 443 rule exists (not duplicated)
    sg_details = ec2.describe_security_groups(GroupIds=[sg_id])
    rules = sg_details["SecurityGroups"][0]["IpPermissions"]
    https_rules = [r for r in rules if r.get("FromPort") == 443]
    assert len(https_rules) == 1


@mock_aws
def test_ensure_https_port_handles_nonexistent_sg() -> None:
    """Test that ensure_https_port raises error for nonexistent security group."""
    service = SecurityGroupService(AWSClientFactory(), region="us-east-1")

    # Try to ensure port on nonexistent security group
    try:
        service.ensure_https_port("sg-nonexistent")
        raise AssertionError("Should have raised RuntimeError")
    except RuntimeError as e:
        assert "sg-nonexistent" in str(e).lower() or "not found" in str(e).lower()
