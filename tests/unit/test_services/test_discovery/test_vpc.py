from __future__ import annotations

import boto3
from moto import mock_aws

from geusemaker.infra import AWSClientFactory
from geusemaker.services.discovery import VPCDiscoveryService


@mock_aws
def test_vpc_and_subnet_discovery_flags_internet_routing() -> None:
    session = boto3.Session(region_name="us-east-1")
    ec2 = session.client("ec2")

    vpc_id = ec2.create_vpc(CidrBlock="10.0.0.0/16")["Vpc"]["VpcId"]
    igw_id = ec2.create_internet_gateway()["InternetGateway"]["InternetGatewayId"]
    ec2.attach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)

    subnet_id = ec2.create_subnet(
        VpcId=vpc_id,
        CidrBlock="10.0.1.0/24",
        AvailabilityZone="us-east-1a",
    )["Subnet"]["SubnetId"]
    route_table_id = ec2.create_route_table(VpcId=vpc_id)["RouteTable"]["RouteTableId"]
    ec2.associate_route_table(RouteTableId=route_table_id, SubnetId=subnet_id)
    ec2.create_route(
        RouteTableId=route_table_id,
        DestinationCidrBlock="0.0.0.0/0",
        GatewayId=igw_id,
    )

    service = VPCDiscoveryService(AWSClientFactory(), region="us-east-1")

    vpcs = service.list_vpcs(use_cache=False)
    target_vpc = next(vpc for vpc in vpcs if vpc.vpc_id == vpc_id)
    assert target_vpc.has_internet_gateway is True

    subnets = [subnet for subnet in service.list_subnets(vpc_id, use_cache=False) if subnet.subnet_id == subnet_id]
    assert len(subnets) == 1
    assert subnets[0].has_internet_route is True
    assert subnets[0].route_table_id == route_table_id

    vpc_validation = service.validate_vpc(vpc_id)
    assert vpc_validation.is_valid is True

    subnet_validation = service.validate_subnets(subnets)
    assert subnet_validation.is_valid is True
    assert any(issue.level == "warning" for issue in subnet_validation.issues)
