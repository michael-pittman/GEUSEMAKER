from __future__ import annotations

from decimal import Decimal

from geusemaker.cli.components.dialogs import Dialogs, scripted_inputs
from geusemaker.cli.interactive.flow import InteractiveFlow, InteractiveSessionStore
from geusemaker.models.cost import (
    ComponentCost,
    CostBreakdown,
    CostComparison,
    CostEstimate,
)
from geusemaker.models.discovery import (
    KeyPairInfo,
    SecurityGroupInfo,
    SecurityGroupRule,
    SubnetInfo,
    VPCInfo,
)


class FakeDiscovery:
    def __init__(self):
        self.region = "us-east-1"
        self.vpc = VPCInfo(
            vpc_id="vpc-1",
            cidr_block="10.0.0.0/16",
            name="main",
            state="available",
            is_default=True,
            has_internet_gateway=True,
            region="us-east-1",
        )
        self.public_subnet = SubnetInfo(
            subnet_id="subnet-public",
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
        self.private_subnet = SubnetInfo(
            subnet_id="subnet-private",
            vpc_id="vpc-1",
            cidr_block="10.0.2.0/24",
            availability_zone="us-east-1b",
            available_ip_count=200,
            is_public=False,
            map_public_ip_on_launch=False,
            route_table_id="rtb-2",
            has_internet_route=False,
            tags={},
        )
        self.sg = SecurityGroupInfo(
            security_group_id="sg-1",
            name="default",
            description="default sg",
            vpc_id="vpc-1",
            ingress_rules=[SecurityGroupRule(protocol="tcp", from_port=22, to_port=22)],
            egress_rules=[],
        )
        self.key = KeyPairInfo(
            key_name="kp-1",
            key_fingerprint="fp",
            key_type="rsa",
        )

    def set_region(self, region: str) -> None:
        self.region = region

    def list_vpcs(self):
        return [self.vpc]

    def list_subnets(self, vpc_id: str):
        assert vpc_id == self.vpc.vpc_id
        return [self.public_subnet, self.private_subnet]

    def list_security_groups(self, vpc_id: str):
        assert vpc_id == self.vpc.vpc_id
        return [self.sg]

    def list_key_pairs(self):
        return [self.key]


class FakeEstimator:
    def estimate_deployment_cost(self, config):
        comparison = CostComparison(
            spot_hourly=Decimal("0.01"),
            on_demand_hourly=Decimal("0.02"),
            spot_monthly=Decimal("7.30"),
            on_demand_monthly=Decimal("14.60"),
            hourly_savings=Decimal("0.01"),
            monthly_savings=Decimal("7.30"),
            savings_percentage=50.0,
        )
        compute = self._component("compute", Decimal("0.01"), Decimal("7.30"))
        zero = self._component("data_transfer", Decimal("0.00"), Decimal("0.00"))
        breakdown = CostBreakdown(
            compute=compute,
            storage=zero,
            data_transfer=zero,
            networking=zero,
            total=compute,
        )
        return CostEstimate(
            deployment_name=config.stack_name,
            tier=config.tier,
            hourly_cost=compute.hourly_cost,
            monthly_cost=compute.monthly_cost,
            breakdown=breakdown,
            comparison=comparison,
            pricing_source="estimated",
        )

    def _component(self, name: str, hourly: Decimal, monthly: Decimal) -> ComponentCost:
        return ComponentCost(
            resource_type=name,
            description=name,
            hourly_cost=hourly,
            monthly_cost=monthly,
            unit_price=hourly,
            unit="hour",
            quantity=1,
        )


def test_interactive_flow_collects_config(monkeypatch, tmp_path):
    dialog_sequence = [
        "demo",  # stack name
        "1",  # region
        "",  # tier default
        "",  # use spot default yes
        "",  # instance type default
        "2",  # choose existing vpc (option 2 after "Create new")
        "1",  # compute subnet
        "1",  # storage subnet
        "2",  # security group existing
        "2",  # key pair existing
        "",  # accept costs
        "",  # confirm deploy
    ]
    dialogs = Dialogs(input_provider=scripted_inputs(dialog_sequence))
    session_store = InteractiveSessionStore(base_path=tmp_path)
    flow = InteractiveFlow(
        prompts=None,
        dialogs=dialogs,
        session_store=session_store,
        initial_state={"region": "us-east-1"},
    )
    flow._discovery = FakeDiscovery()
    flow._cost_estimator = FakeEstimator()

    config = flow.run()

    assert config.stack_name == "demo"
    assert config.vpc_id == "vpc-1"
    assert config.subnet_id == "subnet-public"
    assert config.storage_subnet_id == "subnet-private"
    assert config.security_group_id == "sg-1"
    assert config.keypair_name == "kp-1"
    assert config.use_spot is True


def test_session_store_round_trip(tmp_path):
    store = InteractiveSessionStore(base_path=tmp_path)
    store.save({"stack_name": "demo"})
    loaded = store.load()
    assert loaded == {"stack_name": "demo"}
    store.clear()
    assert store.load() is None
