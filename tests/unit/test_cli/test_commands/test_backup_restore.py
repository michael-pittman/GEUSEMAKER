from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from click.testing import CliRunner

from geusemaker.cli.main import cli
from geusemaker.infra.state import StateManager
from geusemaker.models import CostTracking, DeploymentConfig, DeploymentState


def _make_state(name: str, base: Path) -> None:
    manager = StateManager(base_path=base)
    cost = CostTracking(
        instance_type="t3.medium",
        is_spot=True,
        on_demand_price_per_hour=Decimal("0.04"),
        estimated_monthly_cost=Decimal("25.0"),
    )
    state = DeploymentState(
        stack_name=name,
        status="running",
        created_at=datetime.now(UTC),
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
        config=DeploymentConfig(stack_name=name, tier="dev", region="us-east-1"),
    )
    asyncio.run(manager.save_deployment(state))


def test_backup_create_and_list(tmp_path: Path) -> None:
    _make_state("demo", tmp_path)
    backup_dir = tmp_path / "backups"
    runner = CliRunner()

    create_result = runner.invoke(
        cli,
        ["backup", "create", "demo", "--state-dir", str(tmp_path), "--backup-dir", str(backup_dir)],
    )
    assert create_result.exit_code == 0

    list_result = runner.invoke(
        cli,
        ["backup", "list", "demo", "--state-dir", str(tmp_path), "--backup-dir", str(backup_dir)],
    )
    assert list_result.exit_code == 0
    assert "demo" in list_result.output


def test_restore_latest_backup(tmp_path: Path) -> None:
    _make_state("demo", tmp_path)
    manager = StateManager(base_path=tmp_path)
    backup_dir = tmp_path / "backups"
    runner = CliRunner()

    runner.invoke(
        cli,
        ["backup", "create", "demo", "--state-dir", str(tmp_path), "--backup-dir", str(backup_dir)],
    )

    # Mutate state then restore from latest backup
    state = asyncio.run(manager.load_deployment("demo"))
    assert state is not None
    state.status = "failed"
    asyncio.run(manager.save_deployment(state))

    restore_result = runner.invoke(
        cli,
        ["restore", "demo", "--latest", "--state-dir", str(tmp_path), "--backup-dir", str(backup_dir)],
    )
    assert restore_result.exit_code == 0

    restored = asyncio.run(manager.load_deployment("demo"))
    assert restored is not None
    assert restored.status == "running"
