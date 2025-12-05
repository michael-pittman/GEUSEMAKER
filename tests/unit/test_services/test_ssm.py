"""Unit tests for SSMService."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from geusemaker.infra import AWSClientFactory
from geusemaker.services.ssm import SSMService


@mock_aws
def test_send_shell_commands_returns_command_id() -> None:
    """Test send_shell_commands returns a command ID."""
    svc = SSMService(AWSClientFactory(), region="us-east-1")
    command_id = svc.send_shell_commands(
        instance_ids="i-12345678",
        commands=["echo hello"],
        comment="test command",
    )
    assert isinstance(command_id, str)
    assert len(command_id) > 0


@mock_aws
def test_send_shell_commands_accepts_multiple_instances() -> None:
    """Test send_shell_commands accepts list of instance IDs."""
    svc = SSMService(AWSClientFactory(), region="us-east-1")
    command_id = svc.send_shell_commands(
        instance_ids=["i-12345678", "i-87654321"],
        commands=["echo hello"],
        comment="test multiple",
    )
    assert isinstance(command_id, str)


def test_wait_for_command_retries_when_invocation_not_ready() -> None:
    """Test wait_for_command retries on InvocationDoesNotExist."""
    svc = SSMService(AWSClientFactory(), region="us-east-1")
    not_ready_error = _client_error("InvocationDoesNotExist")

    with patch.object(svc._ssm, "get_command_invocation") as mock_get:
        mock_get.side_effect = [
            not_ready_error,
            {"Status": "Success", "StandardOutputContent": "ok"},
        ]

        result = svc.wait_for_command(
            command_id="cmd-123",
            instance_id="i-12345678",
            timeout_seconds=1,
            poll_interval=0.01,
        )

        assert result["Status"] == "Success"
        assert mock_get.call_count == 2


def test_wait_for_command_raises_on_unexpected_errors() -> None:
    """Test wait_for_command surfaces non-transient ClientError."""
    svc = SSMService(AWSClientFactory(), region="us-east-1")
    fatal_error = _client_error("AccessDeniedException")

    with patch.object(svc._ssm, "get_command_invocation", side_effect=fatal_error) as mock_get:
        with pytest.raises(RuntimeError, match="AWS call failed"):
            svc.wait_for_command(
                command_id="cmd-456",
                instance_id="i-12345678",
                timeout_seconds=1,
                poll_interval=0.01,
            )
        assert mock_get.call_count == 1


def test_wait_for_ssm_agent_returns_false_on_timeout() -> None:
    """Test wait_for_ssm_agent returns False when agent never becomes ready."""
    svc = SSMService(AWSClientFactory(), region="us-east-1")

    # Mock describe_instance_information to return empty list
    with patch.object(svc._ssm, "describe_instance_information") as mock_describe:
        mock_describe.return_value = {"InstanceInformationList": []}

        result = svc.wait_for_ssm_agent(
            instance_id="i-nonexistent",
            timeout_seconds=1,
            poll_interval=0.1,
        )
        assert result is False


def test_wait_for_ssm_agent_returns_true_when_online() -> None:
    """Test wait_for_ssm_agent returns True when agent is online."""
    svc = SSMService(AWSClientFactory(), region="us-east-1")

    # Mock describe_instance_information to return online agent
    with patch.object(svc._ssm, "describe_instance_information") as mock_describe:
        mock_describe.return_value = {"InstanceInformationList": [{"PingStatus": "Online", "InstanceId": "i-12345678"}]}

        result = svc.wait_for_ssm_agent(
            instance_id="i-12345678",
            timeout_seconds=1,
            poll_interval=0.1,
        )
        assert result is True


def test_wait_for_userdata_completion_returns_false_on_timeout() -> None:
    """Test wait_for_userdata_completion returns False when guard file never appears."""
    svc = SSMService(AWSClientFactory(), region="us-east-1")

    # Mock send_command and wait_for_command to simulate guard file not found
    with (
        patch.object(svc, "send_shell_commands") as mock_send,
        patch.object(svc, "wait_for_command") as mock_wait,
    ):
        mock_send.return_value = "cmd-12345"
        mock_wait.return_value = {"StandardOutputContent": "not_found", "Status": "Success"}

        result = svc.wait_for_userdata_completion(
            instance_id="i-nonexistent",
            timeout_seconds=1,
            poll_interval=0.2,
        )
        assert result == "timeout"


def test_wait_for_userdata_completion_returns_true_when_guard_file_exists() -> None:
    """Test wait_for_userdata_completion returns True when guard file is found."""
    svc = SSMService(AWSClientFactory(), region="us-east-1")

    # Mock send_command and wait_for_command to simulate guard file exists
    with (
        patch.object(svc, "send_shell_commands") as mock_send,
        patch.object(svc, "wait_for_command") as mock_wait,
    ):
        mock_send.return_value = "cmd-12345"
        mock_wait.return_value = {"StandardOutputContent": "exists", "Status": "Success"}

        result = svc.wait_for_userdata_completion(
            instance_id="i-12345678",
            timeout_seconds=30,
            poll_interval=0.1,
        )
        assert result == "success"


def test_wait_for_userdata_completion_returns_error_on_error_guard() -> None:
    """Test wait_for_userdata_completion returns 'error' when error guard is found."""
    svc = SSMService(AWSClientFactory(), region="us-east-1")

    with (
        patch.object(svc, "send_shell_commands") as mock_send,
        patch.object(svc, "wait_for_command") as mock_wait,
    ):
        mock_send.return_value = "cmd-12345"
        mock_wait.return_value = {"StandardOutputContent": "error", "Status": "Success"}

        result = svc.wait_for_userdata_completion(
            instance_id="i-12345678",
            timeout_seconds=5,
            poll_interval=0.1,
        )
        assert result == "error"


def test_fetch_userdata_logs_raises_when_ssm_not_ready() -> None:
    """Test fetch_userdata_logs raises RuntimeError when SSM agent not ready."""
    svc = SSMService(AWSClientFactory(), region="us-east-1")

    # Mock wait_for_ssm_agent to return False
    with patch.object(svc, "wait_for_ssm_agent") as mock_wait:
        mock_wait.return_value = False

        with pytest.raises(RuntimeError, match="SSM agent not ready"):
            svc.fetch_userdata_logs(
                instance_id="i-nonexistent",
                wait_for_completion=True,
            )


def test_fetch_userdata_logs_returns_partial_on_timeout() -> None:
    """Test fetch_userdata_logs returns logs with warning when UserData times out but logs exist."""
    svc = SSMService(AWSClientFactory(), region="us-east-1")

    with (
        patch.object(svc, "wait_for_ssm_agent") as mock_wait_agent,
        patch.object(svc, "wait_for_userdata_completion") as mock_wait_userdata,
        patch.object(svc, "send_shell_commands") as mock_send,
        patch.object(svc, "wait_for_command") as mock_wait,
    ):
        mock_wait_agent.return_value = True
        mock_wait_userdata.return_value = "timeout"
        mock_send.return_value = "cmd-12345"
        mock_wait.return_value = {"Status": "Success", "StandardOutputContent": "partial logs"}

        result = svc.fetch_userdata_logs(instance_id="i-12345678", wait_for_completion=True)

        assert result.startswith("WARNING: UserData still running")
        assert "partial logs" in result


def test_fetch_userdata_logs_allows_error_guard_and_returns_logs() -> None:
    """Test fetch_userdata_logs still returns logs when UserData reports error."""
    svc = SSMService(AWSClientFactory(), region="us-east-1")

    log_content = "UserData failed at line 42"

    with (
        patch.object(svc, "wait_for_ssm_agent") as mock_wait_agent,
        patch.object(svc, "wait_for_userdata_completion") as mock_wait_userdata,
        patch.object(svc, "send_shell_commands") as mock_send,
        patch.object(svc, "wait_for_command") as mock_wait,
    ):
        mock_wait_agent.return_value = True
        mock_wait_userdata.return_value = "error"
        mock_send.return_value = "cmd-12345"
        mock_wait.return_value = {"Status": "Success", "StandardOutputContent": log_content}

        result = svc.fetch_userdata_logs(instance_id="i-12345678", wait_for_completion=True)

        assert result.startswith("WARNING: UserData reported an error")
        assert log_content in result


def test_fetch_userdata_logs_returns_primary_log() -> None:
    """Test fetch_userdata_logs returns content from primary log file."""
    svc = SSMService(AWSClientFactory(), region="us-east-1")

    log_content = "=== GeuseMaker UserData ===\nInstalling Docker...\nDone!"

    with (
        patch.object(svc, "wait_for_ssm_agent") as mock_wait_agent,
        patch.object(svc, "wait_for_userdata_completion") as mock_wait_userdata,
        patch.object(svc, "send_shell_commands") as mock_send,
        patch.object(svc, "wait_for_command") as mock_wait,
    ):
        mock_wait_agent.return_value = True
        mock_wait_userdata.return_value = "success"
        mock_send.return_value = "cmd-12345"
        mock_wait.return_value = {"Status": "Success", "StandardOutputContent": log_content}

        result = svc.fetch_userdata_logs(instance_id="i-12345678")

        assert result == log_content


def test_fetch_userdata_logs_falls_back_to_cloud_init() -> None:
    """Test fetch_userdata_logs falls back to cloud-init log when primary is empty."""
    svc = SSMService(AWSClientFactory(), region="us-east-1")

    fallback_content = "Cloud-init log content here"

    with (
        patch.object(svc, "wait_for_ssm_agent") as mock_wait_agent,
        patch.object(svc, "wait_for_userdata_completion") as mock_wait_userdata,
        patch.object(svc, "send_shell_commands") as mock_send,
        patch.object(svc, "wait_for_command") as mock_wait,
    ):
        mock_wait_agent.return_value = True
        mock_wait_userdata.return_value = "success"
        mock_send.side_effect = ["cmd-primary", "cmd-fallback"]

        # First call returns empty, second returns fallback
        mock_wait.side_effect = [
            {"Status": "Success", "StandardOutputContent": ""},
            {"Status": "Success", "StandardOutputContent": fallback_content},
        ]

        result = svc.fetch_userdata_logs(instance_id="i-12345678")

        assert result == fallback_content


@mock_aws
def test_run_shell_script_combines_send_and_wait() -> None:
    """Test run_shell_script sends command and waits for result."""
    svc = SSMService(AWSClientFactory(), region="us-east-1")
    result = svc.run_shell_script(
        instance_id="i-12345678",
        commands=["echo test"],
        comment="test",
        timeout_seconds=30,
    )
    # Should return the command invocation result
    assert isinstance(result, dict)


def _client_error(code: str) -> ClientError:
    """Construct a ClientError with the provided code."""
    return ClientError(
        error_response={"Error": {"Code": code, "Message": code}},
        operation_name="GetCommandInvocation",
    )
