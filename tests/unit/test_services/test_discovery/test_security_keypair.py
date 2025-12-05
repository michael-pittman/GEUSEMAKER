from __future__ import annotations

import boto3
from moto import mock_aws

from geusemaker.infra import AWSClientFactory
from geusemaker.services.discovery import (
    KeyPairDiscoveryService,
    SecurityGroupDiscoveryService,
)


@mock_aws
def test_security_group_validation_and_keypair_discovery() -> None:
    session = boto3.Session(region_name="us-east-1")
    ec2 = session.client("ec2")

    vpc_id = ec2.create_vpc(CidrBlock="10.0.0.0/16")["Vpc"]["VpcId"]
    sg_id = ec2.create_security_group(
        GroupName="web",
        Description="web sg",
        VpcId=vpc_id,
    )["GroupId"]
    ec2.authorize_security_group_ingress(
        GroupId=sg_id,
        IpPermissions=[
            {
                "IpProtocol": "tcp",
                "FromPort": 22,
                "ToPort": 22,
                "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
            },
            {
                "IpProtocol": "tcp",
                "FromPort": 80,
                "ToPort": 80,
                "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
            },
        ],
    )

    sg_service = SecurityGroupDiscoveryService(AWSClientFactory(), region="us-east-1")
    groups = sg_service.list_security_groups(vpc_id, use_cache=False)
    target_group = next(group for group in groups if group.security_group_id == sg_id)

    validation = sg_service.validate_security_group(target_group, [22, 80])
    assert validation.is_valid is True

    missing_port_validation = sg_service.validate_security_group(target_group, [443])
    assert missing_port_validation.is_valid is False

    ec2.create_key_pair(KeyName="demo-key")
    key_service = KeyPairDiscoveryService(AWSClientFactory(), region="us-east-1")
    keys = key_service.list_key_pairs(use_cache=False)
    assert any(key.key_name == "demo-key" for key in keys)
