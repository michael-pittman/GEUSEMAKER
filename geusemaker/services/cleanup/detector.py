"""Detect and clean up orphaned GeuseMaker resources."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from geusemaker.infra import AWSClientFactory, StateManager
from geusemaker.models.cleanup import CleanupReport, OrphanedResource
from geusemaker.models.destruction import DeletedResource


class OrphanDetector:
    """Detect resources tagged for GeuseMaker that no longer have state files."""

    def __init__(
        self,
        client_factory: AWSClientFactory | None = None,
        state_manager: StateManager | None = None,
        region: str = "us-east-1",
        ec2_client: Any | None = None,
        efs_client: Any | None = None,
    ):
        self.client_factory = client_factory or AWSClientFactory()
        self.state_manager = state_manager or StateManager()
        self.region = region
        self._ec2 = ec2_client or self.client_factory.get_client("ec2", region)
        self._efs = efs_client or self.client_factory.get_client("efs", region)

    def detect_orphans(self, region: str | None = None) -> list[OrphanedResource]:
        """Return orphaned resources for a region."""
        reg = region or self.region
        active = asyncio.run(self.state_manager.list_deployments())
        active_names = {state.stack_name for state in active}
        now = datetime.now(UTC)

        orphans: list[OrphanedResource] = []
        orphans.extend(self._detect_instances(active_names, reg, now))
        orphans.extend(self._detect_efs(active_names, reg, now))
        orphans.extend(self._detect_vpcs(active_names, reg, now))
        orphans.extend(self._detect_security_groups(active_names, reg, now))
        return orphans

    def delete_orphans(
        self,
        orphans: list[OrphanedResource],
        dry_run: bool = False,
    ) -> tuple[list[DeletedResource], list[str]]:
        """Delete selected orphaned resources."""
        errors: list[str] = []
        deleted: list[DeletedResource] = []
        for orphan in orphans:
            try:
                if dry_run:
                    continue
                if orphan.resource_type == "ec2":
                    self._ec2.terminate_instances(InstanceIds=[orphan.resource_id])
                elif orphan.resource_type == "efs":
                    self._efs.delete_file_system(FileSystemId=orphan.resource_id)
                elif orphan.resource_type == "vpc":
                    self._ec2.delete_vpc(VpcId=orphan.resource_id)
                elif orphan.resource_type == "security_group":
                    self._ec2.delete_security_group(GroupId=orphan.resource_id)
                deleted.append(
                    DeletedResource(
                        resource_type=orphan.resource_type,
                        resource_id=orphan.resource_id,
                        deleted_at=datetime.now(UTC),
                        deletion_time_seconds=0.0,
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Failed to delete {orphan.resource_type} {orphan.resource_id}: {exc}")
        return deleted, errors

    def build_report(
        self,
        orphans: list[OrphanedResource],
        deleted: list[DeletedResource],
        regions: list[str],
        errors: list[str],
        dry_run: bool,
    ) -> CleanupReport:
        """Create a CleanupReport from detection results."""
        orphans_deleted = 0 if dry_run else len(deleted)
        savings = Decimal("0")
        if not dry_run:
            for orphan in orphans:
                if any(d.resource_id == orphan.resource_id for d in deleted):
                    savings += orphan.estimated_monthly_cost
        return CleanupReport(
            scanned_regions=regions,
            orphans_found=len(orphans),
            orphans_deleted=orphans_deleted,
            orphans_preserved=len(orphans) - orphans_deleted,
            estimated_monthly_savings=savings,
            deleted_resources=deleted,
            errors=errors,
        )

    def _detect_instances(
        self,
        active_names: set[str],
        region: str,
        now: datetime,
    ) -> list[OrphanedResource]:
        orphans: list[OrphanedResource] = []
        resp = self._ec2.describe_instances(
            Filters=[{"Name": "tag-key", "Values": ["geusemaker:deployment", "Stack"]}],
        )
        for reservation in resp.get("Reservations", []):
            for instance in reservation.get("Instances", []):
                tags = self._tags(instance.get("Tags", []))
                deployment = tags.get("geusemaker:deployment") or tags.get("Stack")
                if not deployment or deployment in active_names:
                    continue
                created = instance.get("LaunchTime", now)
                age_days = max(0, (now - created).days)
                name = tags.get("Name")
                orphans.append(
                    OrphanedResource(
                        resource_type="ec2",
                        resource_id=instance.get("InstanceId", ""),
                        name=name,
                        region=region,
                        deployment_tag=deployment,
                        created_at=created,
                        age_days=age_days,
                        estimated_monthly_cost=Decimal("25.00"),
                        tags=tags,
                    ),
                )
        return orphans

    def _detect_efs(
        self,
        active_names: set[str],
        region: str,
        now: datetime,
    ) -> list[OrphanedResource]:
        orphans: list[OrphanedResource] = []
        resp = self._efs.describe_file_systems()
        for fs in resp.get("FileSystems", []):
            tags = self._tags(fs.get("Tags", []))
            deployment = tags.get("geusemaker:deployment") or tags.get("Stack")
            if not deployment or deployment in active_names:
                continue
            created = fs.get("CreationTime", now)
            age_days = max(0, (now - created).days)
            orphans.append(
                OrphanedResource(
                    resource_type="efs",
                    resource_id=fs.get("FileSystemId", ""),
                    name=tags.get("Name"),
                    region=region,
                    deployment_tag=deployment,
                    created_at=created,
                    age_days=age_days,
                    estimated_monthly_cost=Decimal("5.00"),
                    tags=tags,
                ),
            )
        return orphans

    def _detect_vpcs(
        self,
        active_names: set[str],
        region: str,
        now: datetime,
    ) -> list[OrphanedResource]:
        orphans: list[OrphanedResource] = []
        resp = self._ec2.describe_vpcs(Filters=[{"Name": "tag-key", "Values": ["geusemaker:deployment", "Stack"]}])
        for vpc in resp.get("Vpcs", []):
            tags = self._tags(vpc.get("Tags", []))
            deployment = tags.get("geusemaker:deployment") or tags.get("Stack")
            if not deployment or deployment in active_names:
                continue
            orphans.append(
                OrphanedResource(
                    resource_type="vpc",
                    resource_id=vpc.get("VpcId", ""),
                    name=tags.get("Name"),
                    region=region,
                    deployment_tag=deployment,
                    created_at=now,
                    age_days=0,
                    estimated_monthly_cost=Decimal("0.00"),
                    tags=tags,
                ),
            )
        return orphans

    def _detect_security_groups(
        self,
        active_names: set[str],
        region: str,
        now: datetime,
    ) -> list[OrphanedResource]:
        orphans: list[OrphanedResource] = []
        resp = self._ec2.describe_security_groups(
            Filters=[{"Name": "tag-key", "Values": ["geusemaker:deployment", "Stack"]}],
        )
        for sg in resp.get("SecurityGroups", []):
            tags = self._tags(sg.get("Tags", []))
            deployment = tags.get("geusemaker:deployment") or tags.get("Stack")
            if not deployment or deployment in active_names:
                continue
            orphans.append(
                OrphanedResource(
                    resource_type="security_group",
                    resource_id=sg.get("GroupId", ""),
                    name=sg.get("GroupName"),
                    region=region,
                    deployment_tag=deployment,
                    created_at=now,
                    age_days=0,
                    estimated_monthly_cost=Decimal("0.00"),
                    tags=tags,
                ),
            )
        return orphans

    def _tags(self, tags: list[dict[str, str]]) -> dict[str, str]:
        return {tag.get("Key", ""): tag.get("Value", "") for tag in tags if tag.get("Key")}


__all__ = ["OrphanDetector"]
