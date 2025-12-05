from __future__ import annotations

from geusemaker.models.discovery import (
    ALBInfo,
    CloudFrontInfo,
    EFSInfo,
    KeyPairInfo,
    ListenerInfo,
    MountTargetInfo,
    SecurityGroupInfo,
    SecurityGroupRule,
    SubnetInfo,
    TargetGroupInfo,
    VPCInfo,
)
from geusemaker.models.selection import ResourceProvenance
from geusemaker.services.selection import (
    DependencyValidator,
    ResourceSelectionFlow,
    ResourceSelector,
)


def test_selector_honors_provided_id_and_create_new() -> None:
    selector = ResourceSelector()
    vpc = VPCInfo(
        vpc_id="vpc-1",
        cidr_block="10.0.0.0/16",
        name="main",
        state="available",
        is_default=False,
        has_internet_gateway=True,
        region="us-east-1",
    )
    reused = selector.select_vpc([vpc], provided_id="vpc-1")
    assert reused.resource_id == "vpc-1"
    assert reused.provenance == ResourceProvenance.REUSED

    created = selector.select_vpc([], provided_id=None, chooser=lambda options: 0)
    assert created.resource_id is None
    assert created.provenance == ResourceProvenance.CREATED


def test_selection_flow_validates_dependencies() -> None:
    chooser = lambda options: 1 if len(options) > 1 else 0  # choose first existing item
    selector = ResourceSelector(chooser=chooser)
    validator = DependencyValidator()
    vpc = VPCInfo(
        vpc_id="vpc-1",
        cidr_block="10.0.0.0/16",
        name="main",
        state="available",
        is_default=False,
        has_internet_gateway=True,
        region="us-east-1",
    )
    subnet = SubnetInfo(
        subnet_id="subnet-1",
        vpc_id="vpc-1",
        cidr_block="10.0.1.0/24",
        availability_zone="us-east-1a",
        available_ip_count=200,
        is_public=True,
        map_public_ip_on_launch=True,
        route_table_id="rtb-1",
        has_internet_route=True,
        tags={},
    )
    sg = SecurityGroupInfo(
        security_group_id="sg-1",
        name="web",
        description="web sg",
        vpc_id="vpc-1",
        ingress_rules=[SecurityGroupRule(protocol="tcp", from_port=22, to_port=22)],
        egress_rules=[],
    )
    key_pair = KeyPairInfo(
        key_name="kp-1",
        key_fingerprint="fp",
        key_type="rsa",
    )
    efs = EFSInfo(
        file_system_id="fs-1",
        name=None,
        lifecycle_state="available",
        throughput_mode="bursting",
        encrypted=True,
        mount_targets=[
            MountTargetInfo(
                mount_target_id="mt-1",
                file_system_id="fs-1",
                subnet_id="subnet-1",
                availability_zone="us-east-1a",
                ip_address="10.0.1.5",
                lifecycle_state="available",
                security_groups=[],
            ),
        ],
        tags={},
    )
    alb = ALBInfo(
        arn="arn:alb",
        name="alb",
        dns_name="example.elb.amazonaws.com",
        scheme="internet-facing",
        state="active",
        vpc_id="vpc-1",
        availability_zones=["us-east-1a"],
        listeners=[ListenerInfo(arn="arn:listener", protocol="HTTP", port=80)],
        target_groups=[
            TargetGroupInfo(
                arn="arn:tg",
                name="tg",
                protocol="HTTP",
                port=80,
                target_type="instance",
                vpc_id="vpc-1",
            ),
        ],
    )
    cloudfront = CloudFrontInfo(
        distribution_id="dist-1",
        domain_name="example.cloudfront.net",
        status="Deployed",
        origins=["example.com"],
        default_cache_behavior={"target_origin": "origin-1"},
        enabled=True,
        ssl_certificate=None,
    )

    flow = ResourceSelectionFlow(selector=selector, validator=validator)
    result = flow.run(
        vpcs=[vpc],
        subnets=[subnet],
        security_groups=[sg],
        key_pairs=[key_pair],
        efs_list=[efs],
        alb_list=[alb],
        cloudfront_list=[cloudfront],
    )

    assert result.vpc and result.vpc.resource_id == "vpc-1"
    assert result.subnets[0].resource_id == "subnet-1"
    assert result.security_group and result.security_group.resource_id == "sg-1"
    assert result.key_pair and result.key_pair.resource_id == "kp-1"
    assert result.efs and result.efs.resource_id == "fs-1"
    assert result.alb and result.alb.resource_id == "arn:alb"
    assert result.cloudfront and result.cloudfront.resource_id == "dist-1"
    assert all(validation.is_valid for validation in result.validations)
