from __future__ import annotations

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from geusemaker.infra import AWSClientFactory
from geusemaker.services.vpc import VPCService


@mock_aws
def test_create_vpc_with_subnets_applies_tags_and_routes() -> None:
    service = VPCService(AWSClientFactory(), region="us-east-1")
    vpc = service.create_vpc_with_subnets(
        "10.0.0.0/16",
        "demo",
        deployment="demo",
        tier="dev",
    )

    ec2 = boto3.client("ec2", region_name="us-east-1")
    vpc_desc = ec2.describe_vpcs(VpcIds=[vpc.vpc_id])["Vpcs"][0]
    tags = {tag["Key"]: tag["Value"] for tag in vpc_desc.get("Tags", [])}
    assert tags.get("geusemaker:deployment") == "demo"
    assert tags.get("Name") == "demo"

    igw_desc = ec2.describe_internet_gateways(
        Filters=[{"Name": "attachment.vpc-id", "Values": [vpc.vpc_id]}],
    )["InternetGateways"]
    assert len(igw_desc) == 1
    assert vpc.internet_gateway_id == igw_desc[0]["InternetGatewayId"]

    assert len(vpc.public_subnets) == 2
    assert len(vpc.private_subnets) == 2
    for subnet in vpc.public_subnets:
        subnet_resp = ec2.describe_subnets(SubnetIds=[subnet.subnet_id])["Subnets"][0]
        assert subnet_resp.get("MapPublicIpOnLaunch") is True

    route_table_id = vpc.route_table_ids[0]
    routes = ec2.describe_route_tables(RouteTableIds=[route_table_id])["RouteTables"][0]["Routes"]
    assert any(
        route.get("GatewayId") == vpc.internet_gateway_id and route.get("DestinationCidrBlock") == "0.0.0.0/0"
        for route in routes
    )

    nacls = ec2.describe_network_acls(Filters=[{"Name": "vpc-id", "Values": [vpc.vpc_id]}])["NetworkAcls"]
    default_nacl = next(nacl for nacl in nacls if nacl.get("IsDefault"))
    nacl_tags = {tag["Key"]: tag["Value"] for tag in default_nacl.get("Tags", [])}
    assert nacl_tags.get("geusemaker:deployment") == "demo"


@mock_aws
def test_configure_existing_vpc_validates_and_attaches_internet() -> None:
    ec2 = boto3.client("ec2", region_name="us-east-1")
    vpc_id = ec2.create_vpc(CidrBlock="10.1.0.0/16")["Vpc"]["VpcId"]
    public_subnet = ec2.create_subnet(
        VpcId=vpc_id,
        CidrBlock="10.1.1.0/24",
        AvailabilityZone="us-east-1a",
    )["Subnet"]["SubnetId"]
    private_subnet = ec2.create_subnet(
        VpcId=vpc_id,
        CidrBlock="10.1.101.0/24",
        AvailabilityZone="us-east-1b",
    )["Subnet"]["SubnetId"]
    ec2.modify_subnet_attribute(SubnetId=public_subnet, MapPublicIpOnLaunch={"Value": True})

    service = VPCService(AWSClientFactory(), region="us-east-1")
    result = service.configure_existing_vpc(
        vpc_id,
        name="existing",
        deployment="demo",
        tier="dev",
        attach_internet_gateway=True,
    )

    igws = ec2.describe_internet_gateways(
        Filters=[{"Name": "attachment.vpc-id", "Values": [vpc_id]}],
    )["InternetGateways"]
    assert len(igws) == 1
    igw_id = igws[0]["InternetGatewayId"]
    assert result.internet_gateway_id == igw_id
    assert result.created_by_geusemaker is False

    public_route_tables = ec2.describe_route_tables(
        Filters=[{"Name": "association.subnet-id", "Values": [public_subnet]}],
    )["RouteTables"]
    assert len(public_route_tables) == 1
    assert any(route.get("GatewayId") == igw_id for route in public_route_tables[0]["Routes"])

    vpc_tags = {tag["Key"]: tag["Value"] for tag in ec2.describe_vpcs(VpcIds=[vpc_id])["Vpcs"][0].get("Tags", [])}
    assert vpc_tags.get("geusemaker:deployment") == "demo"
    assert any(subnet.subnet_id == public_subnet for subnet in result.public_subnets)
    assert any(subnet.subnet_id == private_subnet for subnet in result.private_subnets)


@mock_aws
def test_configure_existing_vpc_respects_requested_subnet_lists() -> None:
    ec2 = boto3.client("ec2", region_name="us-east-1")
    vpc_id = ec2.create_vpc(CidrBlock="10.5.0.0/16")["Vpc"]["VpcId"]
    subnet_a = ec2.create_subnet(
        VpcId=vpc_id,
        CidrBlock="10.5.1.0/24",
        AvailabilityZone="us-east-1a",
    )["Subnet"]["SubnetId"]
    subnet_b = ec2.create_subnet(
        VpcId=vpc_id,
        CidrBlock="10.5.2.0/24",
        AvailabilityZone="us-east-1b",
    )["Subnet"]["SubnetId"]
    igw_id = ec2.create_internet_gateway()["InternetGateway"]["InternetGatewayId"]
    ec2.attach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)
    route_table_id = ec2.create_route_table(VpcId=vpc_id)["RouteTable"]["RouteTableId"]
    ec2.create_route(RouteTableId=route_table_id, DestinationCidrBlock="0.0.0.0/0", GatewayId=igw_id)
    ec2.associate_route_table(RouteTableId=route_table_id, SubnetId=subnet_b)

    service = VPCService(AWSClientFactory(), region="us-east-1")
    result = service.configure_existing_vpc(
        vpc_id,
        public_subnet_ids=[subnet_b],
        private_subnet_ids=[subnet_a],
    )

    assert [s.subnet_id for s in result.public_subnets] == [subnet_b]
    assert [s.subnet_id for s in result.private_subnets] == [subnet_a]


@mock_aws
def test_configure_existing_vpc_errors_without_attach_flag() -> None:
    ec2 = boto3.client("ec2", region_name="us-east-1")
    vpc_id = ec2.create_vpc(CidrBlock="10.9.0.0/16")["Vpc"]["VpcId"]
    ec2.create_subnet(
        VpcId=vpc_id,
        CidrBlock="10.9.1.0/24",
        AvailabilityZone="us-east-1a",
    )

    service = VPCService(AWSClientFactory(), region="us-east-1")
    with pytest.raises(RuntimeError):
        service.configure_existing_vpc(vpc_id)


@mock_aws
def test_create_vpc_rolls_back_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    service = VPCService(AWSClientFactory(), region="us-east-1")
    ec2 = boto3.client("ec2", region_name="us-east-1")
    vpc_count_before = len(ec2.describe_vpcs()["Vpcs"])
    igw_count_before = len(ec2.describe_internet_gateways()["InternetGateways"])

    def _fail_route(*args: object, **kwargs: object) -> None:
        raise ClientError(
            error_response={"Error": {"Code": "RouteCreationFailed", "Message": "boom"}},
            operation_name="CreateRoute",
        )

    monkeypatch.setattr(service._ec2, "create_route", _fail_route)
    with pytest.raises(RuntimeError):
        service.create_vpc_with_subnets("10.2.0.0/16", "rollback-demo")

    assert len(ec2.describe_vpcs()["Vpcs"]) == vpc_count_before
    assert len(ec2.describe_internet_gateways()["InternetGateways"]) == igw_count_before
