from __future__ import annotations

from pathlib import Path

import boto3
from botocore.exceptions import ClientError  # type: ignore[import-untyped]
from moto import mock_aws

from geusemaker.infra.state import StateManager
from geusemaker.models import DeploymentConfig
from geusemaker.services.validation import PreDeploymentValidator


class FakeFactory:
    def get_client(self, service_name: str, region: str = "us-east-1") -> object:  # noqa: ARG002
        raise AssertionError(f"Unexpected client request for {service_name}")


class FakeSTS:
    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail

    def get_caller_identity(self) -> dict[str, str]:
        if self.should_fail:
            raise ClientError(
                {"Error": {"Code": "ExpiredToken", "Message": "Token expired"}},
                "GetCallerIdentity",
            )
        return {
            "Account": "123456789012",
            "Arn": "arn:aws:iam::123456789012:user/test",
            "UserId": "AIDTEST",
        }


class FakeIAM:
    def __init__(self, denied: list[str] | None = None, raise_error: bool = False) -> None:
        self.denied = denied or []
        self.raise_error = raise_error

    def simulate_principal_policy(self, PolicySourceArn: str, ActionNames: list[str]) -> dict:  # noqa: N802, ARG002
        if self.raise_error:
            raise ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "not allowed"}},
                "SimulatePrincipalPolicy",
            )
        results: list[dict[str, str]] = []
        for action in ActionNames:
            decision = "explicitDeny" if action in self.denied else "allowed"
            results.append({"EvalActionName": action, "EvalDecision": decision})
        return {"EvaluationResults": results}


class FakeServiceQuotas:
    def __init__(self, raise_error: bool = False) -> None:
        self.raise_error = raise_error

    def get_service_quota(self, ServiceCode: str, QuotaCode: str) -> dict:  # noqa: N802, ARG002
        if self.raise_error:
            raise ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "quota denied"}},
                "GetServiceQuota",
            )
        return {"Quota": {"Value": 10}}


class FakeEC2:
    def __init__(
        self,
        region: str = "us-east-1",
        allowed_instance_types: set[str] | None = None,
        vpc_exists: bool = False,
    ) -> None:
        self.region = region
        self.allowed_instance_types = allowed_instance_types or {"t3.medium"}
        self.vpc_exists = vpc_exists

    def describe_regions(self, AllRegions: bool = False) -> dict:  # noqa: N802, ARG002
        return {"Regions": [{"RegionName": self.region}]}

    def describe_instance_types(self, InstanceTypes: list[str]) -> dict:  # noqa: N802
        instance_type = InstanceTypes[0]
        if instance_type not in self.allowed_instance_types:
            raise ClientError(
                {"Error": {"Code": "InvalidInstanceType", "Message": "invalid"}},
                "DescribeInstanceTypes",
            )
        return {"InstanceTypes": [{"InstanceType": instance_type}]}

    def describe_availability_zones(self) -> dict:
        return {"AvailabilityZones": [{"ZoneName": f"{self.region}a"}]}

    def describe_vpcs(self, Filters: list[dict] | None = None) -> dict:  # noqa: N802, ARG002
        if self.vpc_exists:
            return {"Vpcs": [{"VpcId": "vpc-1234"}]}
        return {"Vpcs": []}


class FakeEFS:
    def describe_file_systems(self, MaxItems: int = 10) -> dict:  # noqa: N802, ARG002
        return {"FileSystems": []}


class FakeELBv2:
    def describe_load_balancers(self, PageSize: int = 1) -> dict:  # noqa: N802, ARG002
        return {"LoadBalancers": []}


def _validator(
    tmp_path: Path,
    sts: FakeSTS | None = None,
    iam: FakeIAM | None = None,
    quotas: FakeServiceQuotas | None = None,
    ec2: FakeEC2 | None = None,
) -> PreDeploymentValidator:
    return PreDeploymentValidator(
        client_factory=FakeFactory(),
        region="us-east-1",
        state_manager=StateManager(base_path=tmp_path),
        sts_client=sts or FakeSTS(),
        iam_client=iam or FakeIAM(),
        service_quotas_client=quotas or FakeServiceQuotas(),
        ec2_client=ec2 or FakeEC2(),
        efs_client=FakeEFS(),
        elbv2_client=FakeELBv2(),
    )


def test_predeployment_validation_passes(tmp_path: Path) -> None:
    config = DeploymentConfig(stack_name="test-stack", tier="dev", region="us-east-1")
    report = _validator(tmp_path).validate(config)

    assert report.passed is True
    assert report.errors == 0
    assert any(check.check_name == "credentials" and check.passed for check in report.checks)


def test_credentials_failure_is_reported(tmp_path: Path) -> None:
    config = DeploymentConfig(stack_name="test-stack", tier="dev", region="us-east-1")
    report = _validator(tmp_path, sts=FakeSTS(should_fail=True)).validate(config)

    assert report.passed is False
    assert report.errors >= 1
    credential_check = next(check for check in report.checks if check.check_name == "credentials")
    assert credential_check.passed is False


def test_permission_denials_are_detected(tmp_path: Path) -> None:
    config = DeploymentConfig(stack_name="test-stack", tier="dev", region="us-east-1")
    iam = FakeIAM(denied=["ec2:RunInstances"])
    report = _validator(tmp_path, iam=iam).validate(config)

    permission_check = next(check for check in report.checks if check.check_name == "permissions")
    assert permission_check.passed is False
    assert "ec2:RunInstances" in (permission_check.details or "")


def test_invalid_configuration_fails(tmp_path: Path) -> None:
    config = DeploymentConfig(
        stack_name="bad-name",
        tier="dev",
        region="us-east-1",
        instance_type="m9.nano",
    )
    ec2 = FakeEC2(allowed_instance_types={"t3.medium"})
    report = _validator(tmp_path, ec2=ec2).validate(config)

    assert report.passed is False
    config_check = next(check for check in report.checks if check.check_name == "config")
    assert config_check.passed is False


def test_naming_conflict_detected_from_state(tmp_path: Path) -> None:
    state_manager = StateManager(base_path=tmp_path)
    conflict_file = state_manager.deployments_path / "conflict-stack.json"
    conflict_file.write_text("{}")

    validator = PreDeploymentValidator(
        client_factory=FakeFactory(),
        region="us-east-1",
        state_manager=state_manager,
        sts_client=FakeSTS(),
        iam_client=FakeIAM(),
        service_quotas_client=FakeServiceQuotas(),
        ec2_client=FakeEC2(vpc_exists=True),
        efs_client=FakeEFS(),
        elbv2_client=FakeELBv2(),
    )

    config = DeploymentConfig(stack_name="conflict-stack", tier="dev", region="us-east-1")
    report = validator.validate(config)

    conflict_check = next(check for check in report.checks if check.check_name == "naming_conflicts")
    assert conflict_check.passed is False
    assert "deployment state" in (conflict_check.details or "")


@mock_aws
def test_naming_conflict_allows_existing_vpc_when_id_provided(tmp_path: Path) -> None:
    session = boto3.Session(region_name="us-east-1")
    ec2 = session.client("ec2")
    stack_name = "demo"
    vpc_id = ec2.create_vpc(CidrBlock="10.9.0.0/16")["Vpc"]["VpcId"]
    ec2.create_tags(Resources=[vpc_id], Tags=[{"Key": "Name", "Value": stack_name}])

    validator = _validator(tmp_path, ec2=ec2)
    config = DeploymentConfig(stack_name=stack_name, tier="dev", region="us-east-1", vpc_id=vpc_id)
    report = validator.validate(config)

    conflict_check = next(check for check in report.checks if check.check_name == "naming_conflicts")
    assert conflict_check.passed is True


@mock_aws
def test_existing_vpc_validation_flags_missing_internet_gateway(tmp_path: Path) -> None:
    session = boto3.Session(region_name="us-east-1")
    ec2 = session.client("ec2")
    vpc_id = ec2.create_vpc(CidrBlock="10.3.0.0/16")["Vpc"]["VpcId"]
    ec2.create_subnet(
        VpcId=vpc_id,
        CidrBlock="10.3.1.0/24",
        AvailabilityZone="us-east-1a",
    )

    validator = _validator(tmp_path, ec2=ec2)
    config = DeploymentConfig(stack_name="demo", tier="dev", region="us-east-1", vpc_id=vpc_id)
    report = validator.validate(config)

    igw_check = next(check for check in report.checks if check.check_name == "vpc_internet_gateway")
    assert igw_check.passed is False
    assert report.errors >= 1


@mock_aws
def test_existing_vpc_validation_warns_when_attach_requested(tmp_path: Path) -> None:
    session = boto3.Session(region_name="us-east-1")
    ec2 = session.client("ec2")
    vpc_id = ec2.create_vpc(CidrBlock="10.8.0.0/16")["Vpc"]["VpcId"]
    ec2.create_subnet(
        VpcId=vpc_id,
        CidrBlock="10.8.1.0/24",
        AvailabilityZone="us-east-1a",
    )

    validator = _validator(tmp_path, ec2=ec2)
    config = DeploymentConfig(
        stack_name="demo",
        tier="dev",
        region="us-east-1",
        vpc_id=vpc_id,
        attach_internet_gateway=True,
    )
    report = validator.validate(config)

    igw_check = next(check for check in report.checks if check.check_name == "vpc_internet_gateway")
    route_check = next(check for check in report.checks if check.check_name == "vpc_routes")
    assert igw_check.severity == "warning"
    assert route_check.severity == "warning"
    assert report.passed is True


@mock_aws
def test_existing_vpc_validation_passes_with_routes_and_tags(tmp_path: Path) -> None:
    session = boto3.Session(region_name="us-east-1")
    ec2 = session.client("ec2")
    vpc_id = ec2.create_vpc(CidrBlock="10.4.0.0/16")["Vpc"]["VpcId"]

    igw_id = ec2.create_internet_gateway()["InternetGateway"]["InternetGatewayId"]
    ec2.attach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)

    subnet_id = ec2.create_subnet(
        VpcId=vpc_id,
        CidrBlock="10.4.1.0/24",
        AvailabilityZone="us-east-1a",
    )["Subnet"]["SubnetId"]
    private_subnet_id = ec2.create_subnet(
        VpcId=vpc_id,
        CidrBlock="10.4.101.0/24",
        AvailabilityZone="us-east-1b",
    )["Subnet"]["SubnetId"]
    route_table_id = ec2.create_route_table(VpcId=vpc_id)["RouteTable"]["RouteTableId"]
    ec2.create_route(
        RouteTableId=route_table_id,
        DestinationCidrBlock="0.0.0.0/0",
        GatewayId=igw_id,
    )
    ec2.associate_route_table(RouteTableId=route_table_id, SubnetId=subnet_id)

    default_nacl = ec2.describe_network_acls(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])["NetworkAcls"][0][
        "NetworkAclId"
    ]
    ec2.create_tags(
        Resources=[vpc_id, default_nacl],
        Tags=[
            {"Key": "geusemaker:deployment", "Value": "demo"},
            {"Key": "geusemaker:tier", "Value": "dev"},
        ],
    )

    validator = _validator(tmp_path, ec2=ec2)
    config = DeploymentConfig(
        stack_name="demo",
        tier="dev",
        region="us-east-1",
        vpc_id=vpc_id,
        public_subnet_ids=[subnet_id],
        private_subnet_ids=[private_subnet_id],
    )
    report = validator.validate(config)

    route_check = next(check for check in report.checks if check.check_name == "vpc_routes")
    nacl_check = next(check for check in report.checks if check.check_name == "vpc_network_acl_tags")
    assert route_check.passed is True
    assert nacl_check.severity == "info"
    assert report.errors == 0


@mock_aws
def test_existing_vpc_validation_flags_missing_requested_subnet(tmp_path: Path) -> None:
    session = boto3.Session(region_name="us-east-1")
    ec2 = session.client("ec2")
    vpc_id = ec2.create_vpc(CidrBlock="10.6.0.0/16")["Vpc"]["VpcId"]
    ec2.create_subnet(
        VpcId=vpc_id,
        CidrBlock="10.6.1.0/24",
        AvailabilityZone="us-east-1a",
    )

    validator = _validator(tmp_path, ec2=ec2)
    config = DeploymentConfig(
        stack_name="demo",
        tier="dev",
        region="us-east-1",
        vpc_id=vpc_id,
        public_subnet_ids=["subnet-missing"],
        storage_subnet_id="subnet-missing",
    )
    report = validator.validate(config)

    public_check = next(check for check in report.checks if check.check_name == "vpc_public_subnets")
    storage_check = next(check for check in report.checks if check.check_name == "vpc_storage_subnet")
    assert public_check.passed is False
    assert storage_check.passed is False
