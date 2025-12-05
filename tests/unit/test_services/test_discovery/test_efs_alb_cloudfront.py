from __future__ import annotations

import boto3
from moto import mock_aws

from geusemaker.infra import AWSClientFactory
from geusemaker.services.discovery import (
    ALBDiscoveryService,
    CloudFrontDiscoveryService,
    EFSDiscoveryService,
)


@mock_aws
def test_storage_and_edge_discovery_round_trip() -> None:
    session = boto3.Session(region_name="us-east-1")
    ec2 = session.client("ec2")
    efs_client = session.client("efs")
    elbv2 = session.client("elbv2")
    cloudfront = session.client("cloudfront")

    vpc_id = ec2.create_vpc(CidrBlock="10.0.0.0/16")["Vpc"]["VpcId"]
    subnet_a = ec2.create_subnet(
        VpcId=vpc_id,
        CidrBlock="10.0.1.0/24",
        AvailabilityZone="us-east-1a",
    )["Subnet"]["SubnetId"]
    subnet_b = ec2.create_subnet(
        VpcId=vpc_id,
        CidrBlock="10.0.2.0/24",
        AvailabilityZone="us-east-1b",
    )["Subnet"]["SubnetId"]
    sg_id = ec2.create_security_group(
        GroupName="efs-sg",
        Description="efs sg",
        VpcId=vpc_id,
    )["GroupId"]

    fs_id = efs_client.create_file_system(
        CreationToken="token",
        PerformanceMode="generalPurpose",
        Encrypted=True,
    )["FileSystemId"]
    efs_client.create_mount_target(
        FileSystemId=fs_id,
        SubnetId=subnet_a,
        SecurityGroups=[sg_id],
    )

    alb = elbv2.create_load_balancer(
        Name="gm-alb",
        Subnets=[subnet_a, subnet_b],
        SecurityGroups=[sg_id],
        Scheme="internet-facing",
        Type="application",
        IpAddressType="ipv4",
    )["LoadBalancers"][0]
    target_group = elbv2.create_target_group(
        Name="gm-tg",
        Protocol="HTTP",
        Port=80,
        VpcId=vpc_id,
        TargetType="instance",
    )["TargetGroups"][0]
    elbv2.create_listener(
        LoadBalancerArn=alb["LoadBalancerArn"],
        Protocol="HTTP",
        Port=80,
        DefaultActions=[
            {"Type": "forward", "TargetGroupArn": target_group["TargetGroupArn"]},
        ],
    )

    dist_config = {
        "CallerReference": "gm-test",
        "Comment": "gm",
        "Enabled": True,
        "Origins": {
            "Quantity": 1,
            "Items": [
                {
                    "Id": "origin-1",
                    "DomainName": "example.com",
                    "CustomOriginConfig": {
                        "HTTPPort": 80,
                        "HTTPSPort": 443,
                        "OriginProtocolPolicy": "http-only",
                        "OriginSslProtocols": {"Quantity": 1, "Items": ["TLSv1.2"]},
                        "OriginReadTimeout": 30,
                        "OriginKeepaliveTimeout": 5,
                    },
                },
            ],
        },
        "DefaultCacheBehavior": {
            "TargetOriginId": "origin-1",
            "ViewerProtocolPolicy": "allow-all",
            "TrustedSigners": {"Enabled": False, "Quantity": 0},
            "TrustedKeyGroups": {"Enabled": False, "Quantity": 0},
            "ForwardedValues": {
                "QueryString": False,
                "Cookies": {"Forward": "none"},
                "Headers": {"Quantity": 0},
                "QueryStringCacheKeys": {"Quantity": 0},
            },
            "MinTTL": 0,
        },
        "Restrictions": {"GeoRestriction": {"RestrictionType": "none", "Quantity": 0}},
        "ViewerCertificate": {"CloudFrontDefaultCertificate": True},
        "PriceClass": "PriceClass_All",
        "HttpVersion": "http2",
        "IsIPV6Enabled": True,
    }
    cloudfront.create_distribution(DistributionConfig=dist_config)

    factory = AWSClientFactory()
    efs_service = EFSDiscoveryService(factory, region="us-east-1")
    alb_service = ALBDiscoveryService(factory, region="us-east-1")
    cf_service = CloudFrontDiscoveryService(factory, region="us-east-1")

    filesystems = efs_service.list_file_systems(use_cache=False)
    assert any(fs.file_system_id == fs_id for fs in filesystems)
    efs_validation = efs_service.validate_efs_for_subnets(fs_id, [subnet_a])
    assert efs_validation.is_valid is True

    albs = alb_service.list_load_balancers(vpc_id, use_cache=False)
    assert any(alb.arn for alb in albs)
    alb_validation = alb_service.validate_alb_for_deployment(albs[0])
    assert alb_validation.is_valid is True or alb_validation.issues

    distributions = cf_service.list_distributions(use_cache=False)
    assert len(distributions) == 1
    cf_validation = cf_service.validate_distribution_origin(
        distributions[0].distribution_id,
        "example.com",
    )
    assert cf_validation.is_valid is True
