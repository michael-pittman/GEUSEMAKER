"""Tests for ALB service."""

from __future__ import annotations

import pytest
from moto import mock_aws

from geusemaker.infra import AWSClientFactory
from geusemaker.services.alb import ALBService


@mock_aws
def test_create_alb_success() -> None:
    """Test successful ALB creation."""
    svc = ALBService(AWSClientFactory(), region="us-east-1")

    # Mock VPC and subnets via EC2
    ec2 = AWSClientFactory()._session.client("ec2", region_name="us-east-1")
    vpc_resp = ec2.create_vpc(CidrBlock="10.0.0.0/16")
    vpc_id = vpc_resp["Vpc"]["VpcId"]

    subnet1 = ec2.create_subnet(VpcId=vpc_id, CidrBlock="10.0.1.0/24", AvailabilityZone="us-east-1a")
    subnet2 = ec2.create_subnet(VpcId=vpc_id, CidrBlock="10.0.2.0/24", AvailabilityZone="us-east-1b")

    sg_resp = ec2.create_security_group(GroupName="test-sg", Description="Test SG", VpcId=vpc_id)
    sg_id = sg_resp["GroupId"]

    resp = svc.create_alb(
        name="test-alb",
        subnets=[subnet1["Subnet"]["SubnetId"], subnet2["Subnet"]["SubnetId"]],
        security_groups=[sg_id],
        scheme="internet-facing",
        tags=[{"Key": "Name", "Value": "test-alb"}],
    )

    assert "LoadBalancers" in resp
    assert len(resp["LoadBalancers"]) == 1
    assert resp["LoadBalancers"][0]["LoadBalancerName"] == "test-alb"
    assert resp["LoadBalancers"][0]["Scheme"] == "internet-facing"


@mock_aws
def test_create_target_group_success() -> None:
    """Test successful target group creation."""
    svc = ALBService(AWSClientFactory(), region="us-east-1")

    # Create VPC
    ec2 = AWSClientFactory()._session.client("ec2", region_name="us-east-1")
    vpc_resp = ec2.create_vpc(CidrBlock="10.0.0.0/16")
    vpc_id = vpc_resp["Vpc"]["VpcId"]

    resp = svc.create_target_group(
        name="test-tg",
        vpc_id=vpc_id,
        port=80,
        protocol="HTTP",
        health_check_path="/health",
        health_check_interval=30,
        health_check_timeout=5,
        healthy_threshold=2,
        unhealthy_threshold=2,
        tags=[{"Key": "Name", "Value": "test-tg"}],
    )

    assert "TargetGroups" in resp
    assert len(resp["TargetGroups"]) == 1
    tg = resp["TargetGroups"][0]
    assert tg["TargetGroupName"] == "test-tg"
    assert tg["Protocol"] == "HTTP"
    assert tg["Port"] == 80
    assert tg["VpcId"] == vpc_id
    assert tg["HealthCheckPath"] == "/health"
    assert tg["HealthCheckIntervalSeconds"] == 30
    assert tg["HealthCheckTimeoutSeconds"] == 5
    assert tg["HealthyThresholdCount"] == 2
    assert tg["UnhealthyThresholdCount"] == 2


@mock_aws
def test_create_listener_success() -> None:
    """Test successful listener creation."""
    svc = ALBService(AWSClientFactory(), region="us-east-1")

    # Setup VPC, subnets, ALB, and target group
    ec2 = AWSClientFactory()._session.client("ec2", region_name="us-east-1")
    vpc_resp = ec2.create_vpc(CidrBlock="10.0.0.0/16")
    vpc_id = vpc_resp["Vpc"]["VpcId"]

    subnet1 = ec2.create_subnet(VpcId=vpc_id, CidrBlock="10.0.1.0/24", AvailabilityZone="us-east-1a")
    subnet2 = ec2.create_subnet(VpcId=vpc_id, CidrBlock="10.0.2.0/24", AvailabilityZone="us-east-1b")

    sg_resp = ec2.create_security_group(GroupName="test-sg", Description="Test SG", VpcId=vpc_id)
    sg_id = sg_resp["GroupId"]

    alb_resp = svc.create_alb(
        name="test-alb",
        subnets=[subnet1["Subnet"]["SubnetId"], subnet2["Subnet"]["SubnetId"]],
        security_groups=[sg_id],
    )
    alb_arn = alb_resp["LoadBalancers"][0]["LoadBalancerArn"]

    tg_resp = svc.create_target_group(name="test-tg", vpc_id=vpc_id)
    tg_arn = tg_resp["TargetGroups"][0]["TargetGroupArn"]

    listener_resp = svc.create_listener(
        load_balancer_arn=alb_arn,
        target_group_arn=tg_arn,
        port=80,
        protocol="HTTP",
    )

    assert "Listeners" in listener_resp
    assert len(listener_resp["Listeners"]) == 1
    listener = listener_resp["Listeners"][0]
    assert listener["LoadBalancerArn"] == alb_arn
    assert listener["Protocol"] == "HTTP"
    assert listener["Port"] == 80
    assert listener["DefaultActions"][0]["TargetGroupArn"] == tg_arn


@mock_aws
def test_register_targets_success() -> None:
    """Test successful target registration."""
    svc = ALBService(AWSClientFactory(), region="us-east-1")

    # Setup VPC and target group
    ec2 = AWSClientFactory()._session.client("ec2", region_name="us-east-1")
    vpc_resp = ec2.create_vpc(CidrBlock="10.0.0.0/16")
    vpc_id = vpc_resp["Vpc"]["VpcId"]

    subnet_resp = ec2.create_subnet(VpcId=vpc_id, CidrBlock="10.0.1.0/24")
    subnet_id = subnet_resp["Subnet"]["SubnetId"]

    # Launch test instances
    instances = ec2.run_instances(
        ImageId="ami-12345678",
        MinCount=2,
        MaxCount=2,
        InstanceType="t2.micro",
        SubnetId=subnet_id,
    )
    instance_ids = [inst["InstanceId"] for inst in instances["Instances"]]

    tg_resp = svc.create_target_group(name="test-tg", vpc_id=vpc_id)
    tg_arn = tg_resp["TargetGroups"][0]["TargetGroupArn"]

    # Register targets
    register_resp = svc.register_targets(
        target_group_arn=tg_arn,
        instance_ids=instance_ids,
    )

    # Response should be empty dict on success
    assert isinstance(register_resp, dict)


@mock_aws
def test_register_targets_with_port_override() -> None:
    """Test target registration with custom port."""
    svc = ALBService(AWSClientFactory(), region="us-east-1")

    # Setup VPC and target group
    ec2 = AWSClientFactory()._session.client("ec2", region_name="us-east-1")
    vpc_resp = ec2.create_vpc(CidrBlock="10.0.0.0/16")
    vpc_id = vpc_resp["Vpc"]["VpcId"]

    subnet_resp = ec2.create_subnet(VpcId=vpc_id, CidrBlock="10.0.1.0/24")
    subnet_id = subnet_resp["Subnet"]["SubnetId"]

    instances = ec2.run_instances(
        ImageId="ami-12345678",
        MinCount=1,
        MaxCount=1,
        InstanceType="t2.micro",
        SubnetId=subnet_id,
    )
    instance_id = instances["Instances"][0]["InstanceId"]

    tg_resp = svc.create_target_group(name="test-tg", vpc_id=vpc_id, port=80)
    tg_arn = tg_resp["TargetGroups"][0]["TargetGroupArn"]

    # Register with custom port
    svc.register_targets(
        target_group_arn=tg_arn,
        instance_ids=[instance_id],
        port=8080,
    )

    # Verify registration succeeded
    health_resp = svc.describe_target_health(tg_arn)
    assert len(health_resp["TargetHealthDescriptions"]) == 1


@mock_aws
def test_describe_target_health_all_targets() -> None:
    """Test describing health of all targets in a group."""
    svc = ALBService(AWSClientFactory(), region="us-east-1")

    # Setup VPC and target group
    ec2 = AWSClientFactory()._session.client("ec2", region_name="us-east-1")
    vpc_resp = ec2.create_vpc(CidrBlock="10.0.0.0/16")
    vpc_id = vpc_resp["Vpc"]["VpcId"]

    tg_resp = svc.create_target_group(name="test-tg", vpc_id=vpc_id)
    tg_arn = tg_resp["TargetGroups"][0]["TargetGroupArn"]

    resp = svc.describe_target_health(tg_arn)

    assert "TargetHealthDescriptions" in resp
    assert isinstance(resp["TargetHealthDescriptions"], list)


@mock_aws
def test_describe_target_health_specific_instances() -> None:
    """Test describing health of specific instances."""
    svc = ALBService(AWSClientFactory(), region="us-east-1")

    # Setup VPC, instances, and target group
    ec2 = AWSClientFactory()._session.client("ec2", region_name="us-east-1")
    vpc_resp = ec2.create_vpc(CidrBlock="10.0.0.0/16")
    vpc_id = vpc_resp["Vpc"]["VpcId"]

    subnet_resp = ec2.create_subnet(VpcId=vpc_id, CidrBlock="10.0.1.0/24")
    subnet_id = subnet_resp["Subnet"]["SubnetId"]

    instances = ec2.run_instances(
        ImageId="ami-12345678",
        MinCount=2,
        MaxCount=2,
        InstanceType="t2.micro",
        SubnetId=subnet_id,
    )
    instance_ids = [inst["InstanceId"] for inst in instances["Instances"]]

    tg_resp = svc.create_target_group(name="test-tg", vpc_id=vpc_id)
    tg_arn = tg_resp["TargetGroups"][0]["TargetGroupArn"]

    svc.register_targets(tg_arn, instance_ids)

    # Check specific instance
    resp = svc.describe_target_health(tg_arn, [instance_ids[0]])

    assert "TargetHealthDescriptions" in resp
    assert len(resp["TargetHealthDescriptions"]) >= 1


@mock_aws
def test_wait_for_healthy_success() -> None:
    """Test waiting for targets to become healthy."""
    svc = ALBService(AWSClientFactory(), region="us-east-1")

    # Setup VPC, instances, and target group
    ec2 = AWSClientFactory()._session.client("ec2", region_name="us-east-1")
    vpc_resp = ec2.create_vpc(CidrBlock="10.0.0.0/16")
    vpc_id = vpc_resp["Vpc"]["VpcId"]

    subnet_resp = ec2.create_subnet(VpcId=vpc_id, CidrBlock="10.0.1.0/24")
    subnet_id = subnet_resp["Subnet"]["SubnetId"]

    instances = ec2.run_instances(
        ImageId="ami-12345678",
        MinCount=1,
        MaxCount=1,
        InstanceType="t2.micro",
        SubnetId=subnet_id,
    )
    instance_id = instances["Instances"][0]["InstanceId"]

    tg_resp = svc.create_target_group(name="test-tg", vpc_id=vpc_id)
    tg_arn = tg_resp["TargetGroups"][0]["TargetGroupArn"]

    svc.register_targets(tg_arn, [instance_id])

    # Moto marks targets as healthy immediately
    # Use minimal delay for testing
    svc.wait_for_healthy(tg_arn, [instance_id], max_attempts=5, delay=0)


@mock_aws
def test_wait_for_healthy_timeout() -> None:
    """Test timeout when targets don't become healthy."""
    svc = ALBService(AWSClientFactory(), region="us-east-1")

    # Setup VPC and target group
    ec2 = AWSClientFactory()._session.client("ec2", region_name="us-east-1")
    vpc_resp = ec2.create_vpc(CidrBlock="10.0.0.0/16")
    vpc_id = vpc_resp["Vpc"]["VpcId"]

    tg_resp = svc.create_target_group(name="test-tg", vpc_id=vpc_id)
    tg_arn = tg_resp["TargetGroups"][0]["TargetGroupArn"]

    # Try to wait for non-existent instance
    with pytest.raises(RuntimeError, match="did not become healthy"):
        svc.wait_for_healthy(tg_arn, ["i-nonexistent"], max_attempts=2, delay=0)
