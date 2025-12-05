from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from geusemaker.infra.state import StateManager
from geusemaker.models import CostTracking, DeploymentConfig, DeploymentState
from geusemaker.services.destruction.service import DestructionService


class StubWaiter:
    def __init__(self, calls: list[tuple[str, object]]):
        self.calls = calls

    def wait(self, InstanceIds):  # type: ignore[no-untyped-def]
        self.calls.append(("wait", InstanceIds))


class StubEC2:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.internet_gateways = [
            {"InternetGatewayId": "igw-1", "Attachments": [{"VpcId": "vpc-1"}]},
        ]
        self.route_tables = [
            {"RouteTableId": "rtb-main", "Associations": [{"Main": True}]},
            {"RouteTableId": "rtb-1", "Associations": [{"Main": False}]},
        ]

    def terminate_instances(self, InstanceIds):  # type: ignore[no-untyped-def]
        self.calls.append(("terminate", InstanceIds))

    def get_waiter(self, name: str):  # noqa: ARG002
        return StubWaiter(self.calls)

    def delete_subnet(self, SubnetId):  # type: ignore[no-untyped-def]
        self.calls.append(("delete_subnet", SubnetId))

    def delete_vpc(self, VpcId):  # type: ignore[no-untyped-def]
        self.calls.append(("delete_vpc", VpcId))

    def delete_security_group(self, GroupId):  # type: ignore[no-untyped-def]
        self.calls.append(("delete_sg", GroupId))

    def describe_internet_gateways(self, Filters=None):  # type: ignore[no-untyped-def] # noqa: ANN001
        return {"InternetGateways": list(self.internet_gateways)}

    def detach_internet_gateway(self, InternetGatewayId, VpcId):  # type: ignore[no-untyped-def]
        self.calls.append(("detach_igw", InternetGatewayId, VpcId))

    def delete_internet_gateway(self, InternetGatewayId):  # type: ignore[no-untyped-def]
        self.calls.append(("delete_igw", InternetGatewayId))
        self.internet_gateways = [
            igw for igw in self.internet_gateways if igw["InternetGatewayId"] != InternetGatewayId
        ]

    def describe_route_tables(self, Filters=None):  # type: ignore[no-untyped-def] # noqa: ANN001
        return {"RouteTables": list(self.route_tables)}

    def describe_network_interfaces(self, Filters=None):  # type: ignore[no-untyped-def] # noqa: ANN001
        """Return empty list of network interfaces for testing."""
        return {"NetworkInterfaces": []}

    def delete_route_table(self, RouteTableId):  # type: ignore[no-untyped-def]
        self.calls.append(("delete_rtb", RouteTableId))
        self.route_tables = [rt for rt in self.route_tables if rt["RouteTableId"] != RouteTableId]


class StubEFS:
    def __init__(self, mount_targets: list[str] | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self.mount_targets = set(mount_targets or [])

    def delete_mount_target(self, MountTargetId):  # type: ignore[no-untyped-def]
        self.calls.append(("delete_mt", MountTargetId))
        self.mount_targets.discard(MountTargetId)

    def delete_file_system(self, FileSystemId):  # type: ignore[no-untyped-def]
        self.calls.append(("delete_fs", FileSystemId))

    def describe_mount_targets(self, FileSystemId=None, MountTargetId=None):  # type: ignore[no-untyped-def] # noqa: ANN001
        targets: list[dict[str, str]] = []
        if MountTargetId:
            if MountTargetId in self.mount_targets:
                targets = [{"MountTargetId": MountTargetId, "LifeCycleState": "available"}]
        elif FileSystemId:
            targets = [{"MountTargetId": mt, "LifeCycleState": "available"} for mt in sorted(self.mount_targets)]
        return {"MountTargets": targets}


def _state() -> DeploymentState:
    config = DeploymentConfig(stack_name="demo", tier="dev")
    cost = CostTracking(
        instance_type="t3.medium",
        is_spot=True,
        spot_price_per_hour=Decimal("0.0125"),
        on_demand_price_per_hour=Decimal("0.0416"),
        estimated_monthly_cost=Decimal("25.0"),
    )
    return DeploymentState(
        stack_name=config.stack_name,
        status="running",
        vpc_id="vpc-1",
        subnet_ids=["subnet-1"],
        security_group_id="sg-1",
        efs_id="fs-1",
        efs_mount_target_id="mt-1",
        instance_id="i-1",
        keypair_name="kp",
        private_ip="10.0.0.10",
        public_ip="1.2.3.4",
        n8n_url="http://example.com",
        cost=cost,
        config=config,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def test_destruction_deletes_created_resources_and_archives(tmp_path: Path) -> None:
    state = _state()
    manager = StateManager(base_path=tmp_path)
    ec2 = StubEC2()
    efs = StubEFS(mount_targets=["mt-1", "mt-2"])
    service = DestructionService(state_manager=manager, ec2_client=ec2, efs_client=efs)

    result = service.destroy(state)

    assert result.success is True
    assert any(call[0] == "terminate" for call in ec2.calls)
    assert any(call[0] == "delete_vpc" for call in ec2.calls)
    assert ("delete_mt", "mt-1") in efs.calls
    assert ("delete_mt", "mt-2") in efs.calls
    assert ("detach_igw", "igw-1", "vpc-1") in ec2.calls
    assert ("delete_igw", "igw-1") in ec2.calls
    assert ("delete_rtb", "rtb-1") in ec2.calls
    assert not any(call[0] == "delete_rtb" and call[1] == "rtb-main" for call in ec2.calls)
    assert result.archived_state_path is not None
    assert (tmp_path / "archive").exists()


def test_destruction_preserves_reused_vpc(tmp_path: Path) -> None:
    state = _state()
    state.config = state.config.model_copy(update={"vpc_id": state.vpc_id})
    state.resource_provenance = {
        "vpc": "reused",
        "subnets": "reused",
        "efs": "created",
        "instance": "created",
        "security_group": "created",
    }

    manager = StateManager(base_path=tmp_path)
    ec2 = StubEC2()
    efs = StubEFS()
    service = DestructionService(state_manager=manager, ec2_client=ec2, efs_client=efs)

    result = service.destroy(state)

    assert not any(call[0] == "delete_vpc" for call in ec2.calls)
    assert any(res.resource_type == "vpc" for res in result.preserved_resources)
