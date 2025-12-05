from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from geusemaker.infra.state import StateManager
from geusemaker.models import (
    STATE_SCHEMA_VERSION,
    CostTracking,
    DeploymentConfig,
    DeploymentState,
)


def _state(
    name: str,
    status: str = "running",
    region: str = "us-east-1",
    created_at: datetime | None = None,
) -> DeploymentState:
    config = DeploymentConfig(stack_name=name, tier="dev", region=region)
    cost = CostTracking(
        instance_type="t3.medium",
        is_spot=True,
        on_demand_price_per_hour=Decimal("0.04"),
        estimated_monthly_cost=Decimal("25.0"),
    )
    return DeploymentState(
        stack_name=name,
        status=status,
        created_at=created_at or datetime.now(UTC),
        updated_at=datetime.now(UTC),
        vpc_id="vpc-1",
        subnet_ids=["subnet-1"],
        security_group_id="sg-1",
        efs_id="efs-1",
        efs_mount_target_id="mt-1",
        instance_id="i-1",
        keypair_name="kp-1",
        public_ip="1.2.3.4",
        private_ip="10.0.0.1",
        n8n_url="http://1.2.3.4:5678",
        cost=cost,
        config=config,
    )


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    manager = StateManager(base_path=tmp_path)
    state = _state("demo")

    asyncio.run(manager.save_deployment(state))
    loaded = asyncio.run(manager.load_deployment("demo"))

    assert loaded is not None
    assert loaded.stack_name == "demo"
    assert loaded.schema_version == STATE_SCHEMA_VERSION


def test_load_allows_pending_instance_when_creating(tmp_path: Path) -> None:
    manager = StateManager(base_path=tmp_path)
    config = DeploymentConfig(stack_name="pending", tier="dev", region="us-east-1")
    cost = CostTracking(
        instance_type="t3.medium",
        is_spot=True,
        on_demand_price_per_hour=Decimal("0.04"),
        estimated_monthly_cost=Decimal("25.0"),
    )
    pending_state = DeploymentState(
        stack_name="pending",
        status="creating",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        vpc_id="vpc-1",
        subnet_ids=["subnet-1"],
        security_group_id="sg-1",
        efs_id="efs-1",
        efs_mount_target_id="mt-1",
        instance_id="",
        keypair_name="kp-1",
        public_ip=None,
        private_ip="10.0.0.2",
        n8n_url="",
        cost=cost,
        config=config,
        resource_provenance={"instance": "pending"},
    )

    asyncio.run(manager.save_deployment(pending_state))
    loaded = asyncio.run(manager.load_deployment("pending"))

    assert loaded is not None
    assert loaded.instance_id == ""


def test_query_filters_by_status_region_and_date(tmp_path: Path) -> None:
    manager = StateManager(base_path=tmp_path)
    earlier = datetime.now(UTC) - timedelta(days=2)
    newer = datetime.now(UTC)
    asyncio.run(manager.save_deployment(_state("one", status="running", created_at=earlier)))
    asyncio.run(manager.save_deployment(_state("two", status="failed", region="us-west-2", created_at=newer)))

    filtered = asyncio.run(
        manager.query(
            filters={"status": "failed", "region": "us-west-2"},
            date_range=(earlier + timedelta(days=1), None),
        ),
    )

    assert len(filtered) == 1
    assert filtered[0].stack_name == "two"


def test_backup_and_restore_round_trip(tmp_path: Path) -> None:
    manager = StateManager(base_path=tmp_path)
    state = _state("demo")
    asyncio.run(manager.save_deployment(state))

    # Save an updated version to trigger a backup
    state.status = "failed"
    asyncio.run(manager.save_deployment(state))

    backups = manager.list_backups("demo")
    assert backups, "Backup should be created before overwrite"

    restored = manager.restore_from_backup("demo", backups[0])
    assert restored.status == "running"


def test_export_formats(tmp_path: Path) -> None:
    manager = StateManager(base_path=tmp_path)
    state = _state("demo")
    asyncio.run(manager.save_deployment(state))

    json_payload = manager.export_json(state)
    yaml_payload = manager.export_yaml(state)

    assert '"stack_name": "demo"' in json_payload
    assert "stack_name: demo" in yaml_payload


def test_migration_upgrades_old_schema_version(tmp_path: Path) -> None:
    manager = StateManager(base_path=tmp_path)
    state = _state("legacy")
    raw = state.model_dump(mode="json")
    raw["schema_version"] = 1
    (tmp_path / "deployments").mkdir(parents=True, exist_ok=True)
    file_path = tmp_path / "deployments" / "legacy.json"
    file_path.write_text(json.dumps(raw))

    loaded = asyncio.run(manager.load_deployment("legacy"))

    assert loaded is not None
    assert loaded.schema_version == STATE_SCHEMA_VERSION
    assert any("v1_to_v2" in entry for entry in loaded.migration_history)
