from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from geusemaker.models import CostTracking, DeploymentConfig, DeploymentState
from geusemaker.services.cleanup.detector import OrphanDetector


class StubStateManager:
    async def list_deployments(self):
        config = DeploymentConfig(stack_name="active", tier="dev")
        cost = CostTracking(
            instance_type="t3.medium",
            is_spot=True,
            spot_price_per_hour=Decimal("0.0125"),
            on_demand_price_per_hour=Decimal("0.0416"),
            estimated_monthly_cost=Decimal("25.0"),
        )
        state = DeploymentState(
            stack_name="active",
            status="running",
            vpc_id="vpc-active",
            subnet_ids=["subnet-1"],
            security_group_id="sg-1",
            efs_id="fs-keep",
            efs_mount_target_id="mt-keep",
            instance_id="i-keep",
            keypair_name="kp",
            private_ip="10.0.0.10",
            public_ip="1.2.3.4",
            n8n_url="http://example.com",
            cost=cost,
            config=config,
        )
        return [state]


class StubEC2:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def describe_instances(self, Filters=None):  # type: ignore[no-untyped-def]
        return {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": "i-orphan",
                            "LaunchTime": datetime.now(UTC),
                            "Tags": [{"Key": "Stack", "Value": "orphaned"}],
                        },
                    ],
                },
            ],
        }

    def describe_file_systems(self):  # type: ignore[no-untyped-def]
        return {"FileSystems": []}

    def describe_vpcs(self, Filters=None):  # type: ignore[no-untyped-def]
        return {"Vpcs": []}

    def describe_security_groups(self, Filters=None):  # type: ignore[no-untyped-def]
        return {"SecurityGroups": []}

    def terminate_instances(self, InstanceIds):  # type: ignore[no-untyped-def]
        self.deleted.extend(InstanceIds)

    def delete_vpc(self, VpcId):  # noqa: N802
        self.deleted.append(VpcId)

    def delete_security_group(self, GroupId):  # noqa: N802
        self.deleted.append(GroupId)


class StubEFS:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def describe_file_systems(self):  # type: ignore[no-untyped-def]
        return {
            "FileSystems": [
                {
                    "FileSystemId": "fs-orphan",
                    "CreationTime": datetime.now(UTC),
                    "Tags": [{"Key": "Stack", "Value": "orphaned"}],
                },
            ],
        }

    def delete_file_system(self, FileSystemId):  # type: ignore[no-untyped-def]
        self.deleted.append(FileSystemId)


def test_detects_orphan_instances_and_efs() -> None:
    detector = OrphanDetector(state_manager=StubStateManager(), ec2_client=StubEC2(), efs_client=StubEFS())
    orphans = detector.detect_orphans(region="us-east-1")

    assert len(orphans) == 2
    assert {o.resource_type for o in orphans} == {"ec2", "efs"}
    assert all(o.deployment_tag == "orphaned" for o in orphans)


def test_cleanup_report_counts_deleted_resources() -> None:
    ec2 = StubEC2()
    efs = StubEFS()
    detector = OrphanDetector(state_manager=StubStateManager(), ec2_client=ec2, efs_client=efs)
    orphans = detector.detect_orphans(region="us-east-1")
    deleted, errors = detector.delete_orphans(orphans, dry_run=False)
    report = detector.build_report(orphans, deleted, ["us-east-1"], errors, dry_run=False)

    assert report.orphans_deleted == 2
    assert report.estimated_monthly_savings > Decimal("0")
    assert not report.errors
