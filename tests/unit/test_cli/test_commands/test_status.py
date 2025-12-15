"""Tests for status command."""

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
from geusemaker.models.health import HealthCheckResult


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
def test_status_deployment_not_found(tmp_path: Path) -> None:
    """Test status command with non-existent deployment."""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["status", "nonexistent", "--state-dir", str(tmp_path)],
    )
    assert result.exit_code == 1
    assert "not found" in result.output.lower()


@mock_aws
def test_status_text_output_instance_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test status command when EC2 instance not found."""
    state = _make_state("demo", tmp_path)

    # Mock EC2Service to raise error for instance not found
    def fake_describe_instance(self, instance_id: str) -> dict:  # noqa: ARG001
        raise RuntimeError("Instance not found")

    from geusemaker.services import ec2

    monkeypatch.setattr(ec2.EC2Service, "describe_instance", fake_describe_instance)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["status", "demo", "--state-dir", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert "demo" in result.output
    assert "not_found" in result.output.lower() or "warning" in result.output.lower()


@mock_aws
def test_status_text_output_running_instance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test status command with running instance."""
    state = _make_state("demo", tmp_path)

    # Mock EC2Service to return running instance
    def fake_describe_instance(self, instance_id: str) -> dict:  # noqa: ARG001
        return {
            "State": {"Name": "running"},
            "InstanceType": "t3.medium",
            "PublicIpAddress": "1.2.3.4",
            "PrivateIpAddress": "10.0.0.1",
        }

    # Mock health checks to return healthy
    async def fake_check_http(
        self,  # noqa: ARG001
        url: str,  # noqa: ARG001
        expected_status: int = 200,  # noqa: ARG001
        timeout_seconds: float = 10.0,  # noqa: ARG001
        max_retries: int = 3,  # noqa: ARG001
        base_delay: float = 0.5,  # noqa: ARG001
        max_delay: float = 5.0,  # noqa: ARG001
        service_name: str = "http",  # noqa: ARG001
    ) -> HealthCheckResult:
        return HealthCheckResult(
            service_name=service_name,
            healthy=True,
            status_code=200,
            response_time_ms=10.0,
            endpoint=url,
        )

    async def fake_check_tcp(
        self,  # noqa: ARG001
        host: str,  # noqa: ARG001
        port: int,  # noqa: ARG001
        timeout_seconds: float = 5.0,  # noqa: ARG001
        service_name: str = "tcp",  # noqa: ARG001
    ) -> HealthCheckResult:
        return HealthCheckResult(
            service_name=service_name,
            healthy=True,
            status_code=None,
            response_time_ms=5.0,
            endpoint=f"{host}:{port}",
        )

    from geusemaker.services import ec2, health

    monkeypatch.setattr(ec2.EC2Service, "describe_instance", fake_describe_instance)
    monkeypatch.setattr(health.HealthCheckClient, "check_http", fake_check_http)
    monkeypatch.setattr(health.HealthCheckClient, "check_tcp", fake_check_tcp)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["status", "demo", "--state-dir", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert "demo" in result.output
    assert "running" in result.output.lower()


@mock_aws
def test_status_json_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test status command JSON output."""
    state = _make_state("demo", tmp_path)

    # Mock EC2Service to return running instance
    def fake_describe_instance(self, instance_id: str) -> dict:  # noqa: ARG001
        return {
            "State": {"Name": "running"},
            "InstanceType": "t3.medium",
            "PublicIpAddress": "1.2.3.4",
            "PrivateIpAddress": "10.0.0.1",
        }

    # Mock health checks to return healthy
    async def fake_check_http(
        self,  # noqa: ARG001
        url: str,  # noqa: ARG001
        expected_status: int = 200,  # noqa: ARG001
        timeout_seconds: float = 10.0,  # noqa: ARG001
        max_retries: int = 3,  # noqa: ARG001
        base_delay: float = 0.5,  # noqa: ARG001
        max_delay: float = 5.0,  # noqa: ARG001
        service_name: str = "http",  # noqa: ARG001
    ) -> HealthCheckResult:
        return HealthCheckResult(
            service_name=service_name,
            healthy=True,
            status_code=200,
            response_time_ms=10.0,
            endpoint=url,
        )

    async def fake_check_tcp(
        self,  # noqa: ARG001
        host: str,  # noqa: ARG001
        port: int,  # noqa: ARG001
        timeout_seconds: float = 5.0,  # noqa: ARG001
        service_name: str = "tcp",  # noqa: ARG001
    ) -> HealthCheckResult:
        return HealthCheckResult(
            service_name=service_name,
            healthy=True,
            status_code=None,
            response_time_ms=5.0,
            endpoint=f"{host}:{port}",
        )

    from geusemaker.services import ec2, health

    monkeypatch.setattr(ec2.EC2Service, "describe_instance", fake_describe_instance)
    monkeypatch.setattr(health.HealthCheckClient, "check_http", fake_check_http)
    monkeypatch.setattr(health.HealthCheckClient, "check_tcp", fake_check_tcp)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["status", "demo", "--state-dir", str(tmp_path), "--output", "json"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "ok"
    assert payload["data"]["stack_name"] == "demo"
    assert payload["data"]["instance"]["state"] == "running"
    assert payload["data"]["instance"]["instance_id"] == "i-123456"
    assert "health" in payload["data"]


@mock_aws
def test_status_stopped_instance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test status command with stopped instance."""
    state = _make_state("demo", tmp_path)

    # Mock EC2Service to return stopped instance
    def fake_describe_instance(self, instance_id: str) -> dict:  # noqa: ARG001
        return {
            "State": {"Name": "stopped"},
            "InstanceType": "t3.medium",
            "PrivateIpAddress": "10.0.0.1",
        }

    from geusemaker.services import ec2

    monkeypatch.setattr(ec2.EC2Service, "describe_instance", fake_describe_instance)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["status", "demo", "--state-dir", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert "stopped" in result.output.lower()
    # Services should be marked as unavailable when instance is stopped
    assert "unavailable" in result.output.lower()
