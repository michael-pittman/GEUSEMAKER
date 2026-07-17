from __future__ import annotations

import json
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
    import asyncio

    asyncio.run(manager.save_deployment(state))


def test_silent_mode_shows_json_only(tmp_path: Path) -> None:
    _make_state("demo", tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["--silent", "list", "--state-dir", str(tmp_path), "--output", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "ok"
    assert payload["data"][0]["stack_name"] == "demo"


def test_silent_text_mode_suppresses_results(tmp_path: Path) -> None:
    """--silent means errors only: even result-level text output is suppressed."""
    _make_state("demo", tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["--silent", "list", "--state-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert result.output.strip() == ""


def test_cleanup_json_requires_all_or_dry_run() -> None:
    """Machine-readable cleanup must never fall through to interactive confirmation."""
    runner = CliRunner()
    result = runner.invoke(cli, ["cleanup", "--output", "json"])
    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert payload["error_code"] == "confirmation_required"


def test_json_output_goes_to_stdout_diagnostics_to_stderr(tmp_path: Path) -> None:
    """In machine mode, stdout parses as one document even when diagnostics are emitted."""
    _make_state("demo", tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["list", "--state-dir", str(tmp_path), "--output", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
