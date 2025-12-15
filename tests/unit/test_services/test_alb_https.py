"""Tests for ALB HTTPS listener functionality."""

from moto import mock_aws

from geusemaker.infra import AWSClientFactory
from geusemaker.services import ALBService


@mock_aws
def test_create_https_listener() -> None:
    """Test creating HTTPS listener with ACM certificate."""
    alb_service = ALBService(AWSClientFactory(), region="us-east-1")

    # Create VPC and subnets for ALB
    ec2 = AWSClientFactory()._session.client("ec2", region_name="us-east-1")
    vpc_resp = ec2.create_vpc(CidrBlock="10.0.0.0/16")
    vpc_id = vpc_resp["Vpc"]["VpcId"]

    subnet1_resp = ec2.create_subnet(VpcId=vpc_id, CidrBlock="10.0.1.0/24", AvailabilityZone="us-east-1a")
    subnet2_resp = ec2.create_subnet(VpcId=vpc_id, CidrBlock="10.0.2.0/24", AvailabilityZone="us-east-1b")
    subnet1_id = subnet1_resp["Subnet"]["SubnetId"]
    subnet2_id = subnet2_resp["Subnet"]["SubnetId"]

    # Create security group
    sg_resp = ec2.create_security_group(
        GroupName="test-sg",
        Description="test",
        VpcId=vpc_id,
    )
    sg_id = sg_resp["GroupId"]

    # Create ACM certificate
    acm = AWSClientFactory()._session.client("acm", region_name="us-east-1")
    cert_resp = acm.request_certificate(
        DomainName="example.com",
        ValidationMethod="DNS",
    )
    cert_arn = cert_resp["CertificateArn"]

    # Create ALB
    alb_resp = alb_service.create_alb(
        name="test-alb",
        subnets=[subnet1_id, subnet2_id],
        security_groups=[sg_id],
    )
    alb_arn = alb_resp["LoadBalancers"][0]["LoadBalancerArn"]

    # Create target group
    tg_resp = alb_service.create_target_group(
        name="test-tg",
        vpc_id=vpc_id,
        port=80,
        protocol="HTTP",
    )
    tg_arn = tg_resp["TargetGroups"][0]["TargetGroupArn"]

    # Create HTTPS listener
    listener_resp = alb_service.create_https_listener(
        load_balancer_arn=alb_arn,
        target_group_arn=tg_arn,
        certificate_arn=cert_arn,
        port=443,
    )

    # Verify listener was created
    assert "Listeners" in listener_resp
    listener = listener_resp["Listeners"][0]
    assert listener["Protocol"] == "HTTPS"
    assert listener["Port"] == 443
    assert len(listener["Certificates"]) == 1
    assert listener["Certificates"][0]["CertificateArn"] == cert_arn
    assert listener["DefaultActions"][0]["Type"] == "forward"
    assert listener["DefaultActions"][0]["TargetGroupArn"] == tg_arn


@mock_aws
def test_create_redirect_listener() -> None:
    """Test creating HTTP→HTTPS redirect listener."""
    alb_service = ALBService(AWSClientFactory(), region="us-east-1")

    # Create VPC and subnets for ALB
    ec2 = AWSClientFactory()._session.client("ec2", region_name="us-east-1")
    vpc_resp = ec2.create_vpc(CidrBlock="10.0.0.0/16")
    vpc_id = vpc_resp["Vpc"]["VpcId"]

    subnet1_resp = ec2.create_subnet(VpcId=vpc_id, CidrBlock="10.0.1.0/24", AvailabilityZone="us-east-1a")
    subnet2_resp = ec2.create_subnet(VpcId=vpc_id, CidrBlock="10.0.2.0/24", AvailabilityZone="us-east-1b")
    subnet1_id = subnet1_resp["Subnet"]["SubnetId"]
    subnet2_id = subnet2_resp["Subnet"]["SubnetId"]

    # Create security group
    sg_resp = ec2.create_security_group(
        GroupName="test-sg",
        Description="test",
        VpcId=vpc_id,
    )
    sg_id = sg_resp["GroupId"]

    # Create ALB
    alb_resp = alb_service.create_alb(
        name="test-alb",
        subnets=[subnet1_id, subnet2_id],
        security_groups=[sg_id],
    )
    alb_arn = alb_resp["LoadBalancers"][0]["LoadBalancerArn"]

    # Create redirect listener
    listener_resp = alb_service.create_redirect_listener(
        load_balancer_arn=alb_arn,
        port=80,
    )

    # Verify redirect listener was created
    assert "Listeners" in listener_resp
    listener = listener_resp["Listeners"][0]
    assert listener["Protocol"] == "HTTP"
    assert listener["Port"] == 80
    assert listener["DefaultActions"][0]["Type"] == "redirect"

    redirect_config = listener["DefaultActions"][0]["RedirectConfig"]
    assert redirect_config["Protocol"] == "HTTPS"
    assert redirect_config["Port"] == "443"
    assert redirect_config["StatusCode"] == "HTTP_301"


@mock_aws
def test_https_listener_custom_port() -> None:
    """Test HTTPS listener with custom port."""
    alb_service = ALBService(AWSClientFactory(), region="us-east-1")

    # Create VPC and subnets for ALB
    ec2 = AWSClientFactory()._session.client("ec2", region_name="us-east-1")
    vpc_resp = ec2.create_vpc(CidrBlock="10.0.0.0/16")
    vpc_id = vpc_resp["Vpc"]["VpcId"]

    subnet1_resp = ec2.create_subnet(VpcId=vpc_id, CidrBlock="10.0.1.0/24", AvailabilityZone="us-east-1a")
    subnet2_resp = ec2.create_subnet(VpcId=vpc_id, CidrBlock="10.0.2.0/24", AvailabilityZone="us-east-1b")
    subnet1_id = subnet1_resp["Subnet"]["SubnetId"]
    subnet2_id = subnet2_resp["Subnet"]["SubnetId"]

    # Create security group
    sg_resp = ec2.create_security_group(
        GroupName="test-sg",
        Description="test",
        VpcId=vpc_id,
    )
    sg_id = sg_resp["GroupId"]

    # Create ACM certificate
    acm = AWSClientFactory()._session.client("acm", region_name="us-east-1")
    cert_resp = acm.request_certificate(
        DomainName="example.com",
        ValidationMethod="DNS",
    )
    cert_arn = cert_resp["CertificateArn"]

    # Create ALB
    alb_resp = alb_service.create_alb(
        name="test-alb",
        subnets=[subnet1_id, subnet2_id],
        security_groups=[sg_id],
    )
    alb_arn = alb_resp["LoadBalancers"][0]["LoadBalancerArn"]

    # Create target group
    tg_resp = alb_service.create_target_group(
        name="test-tg",
        vpc_id=vpc_id,
        port=8443,
        protocol="HTTPS",
    )
    tg_arn = tg_resp["TargetGroups"][0]["TargetGroupArn"]

    # Create HTTPS listener on custom port
    listener_resp = alb_service.create_https_listener(
        load_balancer_arn=alb_arn,
        target_group_arn=tg_arn,
        certificate_arn=cert_arn,
        port=8443,
    )

    # Verify custom port
    listener = listener_resp["Listeners"][0]
    assert listener["Port"] == 8443
    assert listener["Protocol"] == "HTTPS"
