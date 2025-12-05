"""SSM service for running commands on instances."""

from __future__ import annotations

import time
from collections.abc import Generator, Iterable
from typing import Any

from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from geusemaker.infra import AWSClientFactory
from geusemaker.services.base import BaseService


class SSMService(BaseService):
    """Interact with AWS Systems Manager for commands and log streaming."""

    def __init__(self, client_factory: AWSClientFactory, region: str = "us-east-1"):
        super().__init__(client_factory, region)
        self._ssm = self._client("ssm")

    def send_shell_commands(
        self,
        instance_ids: str | Iterable[str],
        commands: list[str],
        comment: str | None = None,
        timeout_seconds: int = 900,
    ) -> str:
        """Send shell commands via AWS-RunShellScript and return the command ID."""
        if isinstance(instance_ids, str):
            instance_ids = [instance_ids]

        def _call() -> str:
            resp = self._ssm.send_command(
                InstanceIds=list(instance_ids),
                DocumentName="AWS-RunShellScript",
                Parameters={"commands": commands},
                Comment=comment,
                TimeoutSeconds=timeout_seconds,
            )
            return resp["Command"]["CommandId"]  # type: ignore[return-value]

        return self._safe_call(_call)

    def wait_for_command(
        self,
        command_id: str,
        instance_id: str,
        timeout_seconds: int = 900,
        poll_interval: float = 2.0,
    ) -> dict[str, Any]:
        """Poll command invocation until completion."""
        end_time = time.monotonic() + timeout_seconds
        last_response: dict[str, Any] = {}
        while time.monotonic() < end_time:

            def _call() -> dict[str, Any]:
                return self._ssm.get_command_invocation(
                    CommandId=command_id,
                    InstanceId=instance_id,
                )

            try:
                last_response = self._safe_call(_call)
            except RuntimeError as exc:
                if self._is_invocation_not_ready(exc):
                    time.sleep(poll_interval)
                    continue
                raise
            status = last_response.get("Status")
            if status not in {"Pending", "InProgress", "Delayed"}:
                return last_response
            time.sleep(poll_interval)
        return last_response

    def run_shell_script(
        self,
        instance_id: str,
        commands: list[str],
        comment: str | None = None,
        timeout_seconds: int = 900,
    ) -> dict[str, Any]:
        """Send and wait for shell script execution."""
        command_id = self.send_shell_commands(instance_id, commands, comment=comment, timeout_seconds=timeout_seconds)
        return self.wait_for_command(command_id, instance_id, timeout_seconds=timeout_seconds)

    def wait_for_ssm_agent(
        self,
        instance_id: str,
        timeout_seconds: int = 60,
        poll_interval: float = 5.0,
    ) -> bool:
        """Wait for SSM agent to be ready on the instance."""
        end_time = time.monotonic() + timeout_seconds
        while time.monotonic() < end_time:

            def _call() -> dict[str, Any]:
                resp = self._ssm.describe_instance_information(
                    Filters=[{"Key": "InstanceIds", "Values": [instance_id]}]
                )
                return resp

            resp = self._safe_call(_call)
            if resp.get("InstanceInformationList"):
                info = resp["InstanceInformationList"][0]
                if info.get("PingStatus") == "Online":
                    return True

            time.sleep(poll_interval)
        return False

    def wait_for_userdata_completion(
        self,
        instance_id: str,
        timeout_seconds: int = 600,
        poll_interval: float = 10.0,
    ) -> str:
        """Wait for UserData script to complete by checking guard files.

        Returns:
            "success" when the completion guard file exists
            "error" when an error guard file is present
            "timeout" when neither guard is found within the timeout window
        """
        end_time = time.monotonic() + timeout_seconds
        guard_file = "/var/lib/geusemaker/userdata-complete"
        error_guard = "/var/lib/geusemaker/userdata-error"

        while time.monotonic() < end_time:
            # Check if guard or error file exists
            command_id = self.send_shell_commands(
                instance_id,
                [
                    (
                        f"if [ -f {guard_file} ]; then echo 'exists'; "
                        f"elif [ -f {error_guard} ]; then echo 'error'; "
                        "else echo 'not_found'; fi"
                    )
                ],
                comment="Check UserData completion",
                timeout_seconds=30,
            )

            result = self.wait_for_command(command_id, instance_id, timeout_seconds=30)
            output = result.get("StandardOutputContent", "").strip()

            if output == "exists":
                return "success"
            if output == "error":
                return "error"

            time.sleep(poll_interval)
        return "timeout"

    def fetch_userdata_logs(
        self,
        instance_id: str,
        wait_for_completion: bool = True,
    ) -> str:
        """
        Fetch UserData initialization logs from an EC2 instance via SSM.

        Args:
            instance_id: EC2 instance ID
            wait_for_completion: Wait for SSM agent and UserData to complete

        Returns:
            Log content as string (may be partial if UserData is still running)

        Raises:
            RuntimeError: If SSM agent not ready or logs unavailable
        """
        # Wait for SSM agent to be ready
        if not self.wait_for_ssm_agent(instance_id, timeout_seconds=60):
            raise RuntimeError(f"SSM agent not ready on instance {instance_id} after 60 seconds")

        # Wait for UserData completion if requested
        status: str = "success"
        if wait_for_completion:
            status = self.wait_for_userdata_completion(instance_id, timeout_seconds=600)

        # Try primary log file first
        primary_log = "/var/log/geusemaker-userdata.log"
        fallback_log = "/var/log/cloud-init-output.log"
        status_prefix = {
            "timeout": "WARNING: UserData still running after 600s; showing latest logs.\n",
            "error": "WARNING: UserData reported an error; showing logs.\n",
        }

        for log_file in [primary_log, fallback_log]:
            command_id = self.send_shell_commands(
                instance_id,
                [f"cat {log_file}"],
                comment=f"Fetch {log_file}",
                timeout_seconds=30,
            )

            result = self.wait_for_command(command_id, instance_id, timeout_seconds=30)
            invocation_status = result.get("Status")

            if invocation_status == "Success":
                log_content = result.get("StandardOutputContent", "")
                if log_content.strip():
                    prefix = status_prefix.get(status, "")
                    return f"{prefix}{log_content}" if prefix else log_content

        if status == "timeout":
            raise RuntimeError(f"UserData did not complete on instance {instance_id} after 600 seconds")

        raise RuntimeError(f"UserData logs not available on instance {instance_id}")

    def stream_userdata_logs(
        self,
        instance_id: str,
        poll_interval: float = 2.0,
        timeout_seconds: int = 600,
    ) -> Generator[str, None, None]:
        """Stream UserData initialization logs in real time.

        Polls the log file every poll_interval seconds and yields new lines as they appear.
        Stops when:
        - "GeuseMaker initialization complete!" message is found
        - Error guard file is detected
        - Timeout is reached

        Args:
            instance_id: EC2 instance ID
            poll_interval: Seconds between log polls (default: 2.0)
            timeout_seconds: Maximum time to stream logs (default: 600)

        Yields:
            New log lines as they become available

        Raises:
            RuntimeError: If SSM agent not ready or logs unavailable
        """
        # Wait for SSM agent to be ready
        if not self.wait_for_ssm_agent(instance_id, timeout_seconds=60):
            raise RuntimeError(f"SSM agent not ready on instance {instance_id} after 60 seconds")

        log_file = "/var/log/geusemaker-userdata.log"
        error_guard = "/var/lib/geusemaker/userdata-error"
        completion_marker = "GeuseMaker initialization complete!"
        error_marker = "ERROR:"

        lines_seen = 0
        end_time = time.monotonic() + timeout_seconds

        while time.monotonic() < end_time:
            # Fetch current log content
            command_id = self.send_shell_commands(
                instance_id,
                [f"tail -n +1 {log_file} 2>/dev/null || echo ''"],
                comment="Stream UserData logs",
                timeout_seconds=30,
            )

            result = self.wait_for_command(command_id, instance_id, timeout_seconds=30)
            log_content = result.get("StandardOutputContent", "")

            # Split into lines and yield new ones
            lines = log_content.splitlines()
            new_lines = lines[lines_seen:]

            for line in new_lines:
                yield line
                lines_seen += 1

                # Check for completion or error markers
                if completion_marker in line:
                    return
                if error_marker in line:
                    # Check if error guard file exists
                    check_cmd = self.send_shell_commands(
                        instance_id,
                        [f"[ -f {error_guard} ] && echo 'error' || echo 'ok'"],
                        comment="Check error guard",
                        timeout_seconds=30,
                    )
                    check_result = self.wait_for_command(check_cmd, instance_id, timeout_seconds=30)
                    if check_result.get("StandardOutputContent", "").strip() == "error":
                        return

            # Check for completion guard file
            guard_cmd = self.send_shell_commands(
                instance_id,
                ["[ -f /var/lib/geusemaker/userdata-complete ] && echo 'done' || echo 'running'"],
                comment="Check completion guard",
                timeout_seconds=30,
            )
            guard_result = self.wait_for_command(guard_cmd, instance_id, timeout_seconds=30)
            if guard_result.get("StandardOutputContent", "").strip() == "done":
                return

            time.sleep(poll_interval)

    @staticmethod
    def _is_invocation_not_ready(exc: RuntimeError) -> bool:
        """Return True if the invocation has not been created yet."""
        cause = exc.__cause__
        if isinstance(cause, ClientError):
            error = cause.response.get("Error", {})
            return error.get("Code") == "InvocationDoesNotExist"
        return False


__all__ = ["SSMService"]
