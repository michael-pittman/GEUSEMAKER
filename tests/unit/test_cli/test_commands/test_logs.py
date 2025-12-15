"""Tests for logs command."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from click.testing import CliRunner
from moto import mock_aws

from geusemaker.cli.main import cli
from geusemaker.infra.state import StateManager
from geusemaker.models import CostTracking, DeploymentConfig, DeploymentState


def _make_state(name: str, base: Path) -> DeploymentState:
    """Create test deployment state."""
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
        instance_id="i-123456",
        keypair_name="kp-1",
        public_ip="1.2.3.4",
        private_ip="10.0.0.1",
        n8n_url="http://1.2.3.4:5678",
        cost=cost,
        config=DeploymentConfig(stack_name=name, tier="dev", region="us-east-1"),
    )
    import asyncio

    asyncio.run(manager.save_deployment(state))
    return state


@mock_aws
def test_logs_deployment_not_found(tmp_path: Path) -> None:
    """Test logs command with non-existent deployment."""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["logs", "nonexistent", "--state-dir", str(tmp_path)],
    )
    assert result.exit_code == 1
    assert "not found" in result.output.lower()


@mock_aws
def test_logs_follow_only_for_userdata(tmp_path: Path) -> None:
    """Test that --follow flag only works with userdata service."""
    _make_state("demo", tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["logs", "demo", "--service", "n8n", "--follow", "--state-dir", str(tmp_path)],
    )
    assert result.exit_code == 1
    assert "only supported for userdata" in result.output.lower()


@mock_aws
def test_logs_userdata_text_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test logs command for userdata logs."""
    _make_state("demo", tmp_path)

    # Mock SSMService to return userdata logs
    def fake_fetch_userdata_logs(self, instance_id: str, wait_for_completion: bool = True) -> str:  # noqa: ARG001
        return "UserData initialization started\nDocker containers starting\nGeuseMaker initialization complete!"

    from geusemaker.services import ssm

    monkeypatch.setattr(ssm.SSMService, "fetch_userdata_logs", fake_fetch_userdata_logs)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["logs", "demo", "--state-dir", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert "UserData logs" in result.output
    assert "initialization complete" in result.output


@mock_aws
def test_logs_userdata_json_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test logs command JSON output for userdata."""
    _make_state("demo", tmp_path)

    # Mock SSMService to return userdata logs
    def fake_fetch_userdata_logs(self, instance_id: str, wait_for_completion: bool = True) -> str:  # noqa: ARG001
        return "UserData initialization complete!"

    from geusemaker.services import ssm

    monkeypatch.setattr(ssm.SSMService, "fetch_userdata_logs", fake_fetch_userdata_logs)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["logs", "demo", "--state-dir", str(tmp_path), "--output", "json"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "ok"
    assert payload["data"]["stack_name"] == "demo"
    assert payload["data"]["service"] == "userdata"
    assert "initialization complete" in payload["data"]["logs"]


@mock_aws
def test_logs_container_logs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test logs command for container logs."""
    _make_state("demo", tmp_path)

    # Mock SSMService to return container logs
    def fake_run_shell_script(
        self,  # noqa: ARG001
        instance_id: str,  # noqa: ARG001
        commands: list[str],  # noqa: ARG001
        comment: str | None = None,  # noqa: ARG001
        timeout_seconds: int = 900,  # noqa: ARG001
    ) -> dict:
        return {
            "Status": "Success",
            "StandardOutputContent": "n8n container log line 1\nn8n container log line 2\nn8n ready",
            "StandardErrorContent": "",
        }

    from geusemaker.services import ssm

    monkeypatch.setattr(ssm.SSMService, "run_shell_script", fake_run_shell_script)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["logs", "demo", "--service", "n8n", "--tail", "50", "--state-dir", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert "n8n" in result.output
    assert "n8n ready" in result.output


@mock_aws
def test_logs_container_logs_json_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test logs command JSON output for container logs."""
    _make_state("demo", tmp_path)

    # Mock SSMService to return container logs
    def fake_run_shell_script(
        self,  # noqa: ARG001
        instance_id: str,  # noqa: ARG001
        commands: list[str],  # noqa: ARG001
        comment: str | None = None,  # noqa: ARG001
        timeout_seconds: int = 900,  # noqa: ARG001
    ) -> dict:
        return {
            "Status": "Success",
            "StandardOutputContent": "ollama container logs",
            "StandardErrorContent": "",
        }

    from geusemaker.services import ssm

    monkeypatch.setattr(ssm.SSMService, "run_shell_script", fake_run_shell_script)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["logs", "demo", "--service", "ollama", "--tail", "100", "--state-dir", str(tmp_path), "--output", "json"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "ok"
    assert payload["data"]["service"] == "ollama"
    assert payload["data"]["tail"] == 100
    assert "ollama container logs" in payload["data"]["logs"]


@mock_aws
def test_logs_ssm_error_handling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test logs command error handling when SSM fails."""
    _make_state("demo", tmp_path)

    # Mock SSMService to raise error
    def fake_fetch_userdata_logs(self, instance_id: str, wait_for_completion: bool = True) -> str:  # noqa: ARG001
        raise RuntimeError("SSM agent not ready on instance i-123456 after 60 seconds")

    from geusemaker.services import ssm

    monkeypatch.setattr(ssm.SSMService, "fetch_userdata_logs", fake_fetch_userdata_logs)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["logs", "demo", "--state-dir", str(tmp_path)],
    )
    assert result.exit_code == 1
    assert "failed to fetch logs" in result.output.lower()


@mock_aws
def test_logs_container_command_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test logs command when container command fails."""
    _make_state("demo", tmp_path)

    # Mock SSMService to return failed command
    def fake_run_shell_script(
        self,  # noqa: ARG001
        instance_id: str,  # noqa: ARG001
        commands: list[str],  # noqa: ARG001
        comment: str | None = None,  # noqa: ARG001
        timeout_seconds: int = 900,  # noqa: ARG001
    ) -> dict:
        return {
            "Status": "Failed",
            "StandardOutputContent": "",
            "StandardErrorContent": "Error: No such container: postgres",
        }

    from geusemaker.services import ssm

    monkeypatch.setattr(ssm.SSMService, "run_shell_script", fake_run_shell_script)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["logs", "demo", "--service", "postgres", "--state-dir", str(tmp_path)],
    )
    assert result.exit_code == 1
    assert "failed" in result.output.lower()
