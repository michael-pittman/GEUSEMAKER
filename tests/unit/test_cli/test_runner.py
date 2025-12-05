"""Unit tests for DeploymentRunner."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from geusemaker.cli.interactive.runner import DeploymentRunner
from geusemaker.infra import AWSClientFactory, StateManager
from geusemaker.models import CostTracking, DeploymentConfig, DeploymentState


@pytest.fixture
def mock_state() -> DeploymentState:
    """Create a mock deployment state for testing."""
    config = DeploymentConfig(
        stack_name="test-stack",
        tier="dev",
        region="us-east-1",
        instance_type="t3.medium",
    )
    cost = CostTracking(
        instance_type="t3.medium",
        is_spot=True,
        on_demand_price_per_hour=Decimal("0.0416"),
        estimated_monthly_cost=Decimal("30.00"),
    )
    return DeploymentState(
        stack_name="test-stack",
        status="running",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        vpc_id="vpc-12345",
        subnet_ids=["subnet-1", "subnet-2"],
        security_group_id="sg-12345",
        efs_id="fs-12345",
        efs_mount_target_id="mt-12345",
        instance_id="i-12345678",
        keypair_name="test-key",
        public_ip="1.2.3.4",
        private_ip="10.0.1.10",
        n8n_url="http://1.2.3.4:5678",
        cost=cost,
        config=config,
    )


def test_stream_userdata_logs_streams_and_displays(mock_state: DeploymentState) -> None:
    """Test _stream_userdata_logs streams logs and displays them line by line."""
    runner = DeploymentRunner(AWSClientFactory(), StateManager())

    mock_log_lines = [
        "=== GeuseMaker UserData ===",
        "Installing Docker...",
        "Done!",
        "GeuseMaker initialization complete!",
    ]

    with (
        patch("geusemaker.cli.interactive.runner.SSMService") as mock_ssm_class,
        patch("geusemaker.cli.interactive.runner.console") as mock_console,
    ):
        mock_ssm = MagicMock()
        mock_ssm.stream_userdata_logs.return_value = iter(mock_log_lines)
        mock_ssm_class.return_value = mock_ssm

        runner._stream_userdata_logs(mock_state)

        # Verify SSMService was instantiated with correct params
        mock_ssm_class.assert_called_once()
        call_kwargs = mock_ssm_class.call_args[1]
        assert call_kwargs["region"] == "us-east-1"

        # Verify stream_userdata_logs was called
        mock_ssm.stream_userdata_logs.assert_called_once_with(
            instance_id="i-12345678",
            poll_interval=2.0,
            timeout_seconds=600,
        )

        # Verify console.print was called for each log line plus headers/footer
        assert mock_console.print.call_count >= len(mock_log_lines)


def test_stream_userdata_logs_handles_runtime_error(mock_state: DeploymentState) -> None:
    """Test _stream_userdata_logs handles RuntimeError gracefully."""
    runner = DeploymentRunner(AWSClientFactory(), StateManager())

    with (
        patch("geusemaker.cli.interactive.runner.SSMService") as mock_ssm_class,
        patch("geusemaker.cli.interactive.runner.console") as mock_console,
    ):
        mock_ssm = MagicMock()
        mock_ssm.stream_userdata_logs.side_effect = RuntimeError("SSM agent not ready")
        mock_ssm_class.return_value = mock_ssm

        # Should not raise, just print warning
        runner._stream_userdata_logs(mock_state)

        # Verify warning was printed
        warning_calls = [
            call for call in mock_console.print.call_args_list if "Could not stream UserData logs" in str(call)
        ]
        assert len(warning_calls) > 0


def test_stream_userdata_logs_skips_when_no_instance_id(mock_state: DeploymentState) -> None:
    """Test _stream_userdata_logs returns early when no instance_id."""
    mock_state.instance_id = ""  # type: ignore[misc]
    runner = DeploymentRunner(AWSClientFactory(), StateManager())

    with patch("geusemaker.cli.interactive.runner.SSMService") as mock_ssm_class:
        runner._stream_userdata_logs(mock_state)

        # SSMService should not be instantiated
        mock_ssm_class.assert_not_called()
