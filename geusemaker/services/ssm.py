"""SSM service for running commands on instances."""

from __future__ import annotations

import shlex
import time
from collections.abc import Generator, Iterable
from typing import Any

from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from geusemaker.infra import AWSClientFactory
from geusemaker.services.base import BaseService

# Single source of truth for CLI/TUI service -> Docker container name mapping.
CONTAINER_LOG_SERVICES: dict[str, str] = {
    "n8n": "n8n",
    "ollama": "ollama",
    "qdrant": "qdrant",
    "crawl4ai": "crawl4ai",
    "postgres": "postgres",
}

# Consecutive SSM command failures tolerated before a streaming generator aborts.
_MAX_CONSECUTIVE_STREAM_FAILURES = 3


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

    def get_userdata_status(self, instance_id: str) -> str:
        """One-shot check of the UserData guard files (no waiting).

        Returns:
            "success" when the completion guard exists,
            "error" when the error guard exists,
            "running" when neither is present yet.
        """
        guard_file = "/var/lib/geusemaker/userdata-complete"
        error_guard = "/var/lib/geusemaker/userdata-error"
        command_id = self.send_shell_commands(
            instance_id,
            [
                (
                    f"if [ -f {guard_file} ]; then echo 'exists'; "
                    f"elif [ -f {error_guard} ]; then echo 'error'; "
                    "else echo 'not_found'; fi"
                )
            ],
            comment="Check UserData status",
            timeout_seconds=30,
        )
        result = self.wait_for_command(command_id, instance_id, timeout_seconds=30)
        output = result.get("StandardOutputContent", "").strip()
        if output == "exists":
            return "success"
        if output == "error":
            return "error"
        return "running"

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
    def resolve_container_name(service: str) -> str:
        """Map a logical service name to its Docker container name.

        Raises:
            ValueError: If the service is not a known container-backed service.
        """
        container = CONTAINER_LOG_SERVICES.get(service.lower())
        if container is None:
            known = ", ".join(sorted(CONTAINER_LOG_SERVICES))
            raise ValueError(f"Unknown service '{service}'. Known services: {known}")
        return container

    def tail_file(
        self,
        instance_id: str,
        path: str,
        *,
        poll_interval: float = 2.0,
        timeout_seconds: int = 600,
    ) -> Generator[str, None, None]:
        """Tail a remote file via SSM with byte-offset resume.

        Each poll sends ``tail -c +<offset+1> <path>`` (path shell-quoted) and
        yields the newly appended content split into lines (``str.splitlines``;
        a line written across a poll boundary may arrive as two yielded
        fragments). The byte offset advances by the full UTF-8 byte length of
        each received chunk.

        Stops when:
        - ``timeout_seconds`` elapses: yields a final ``[TAIL TIMEOUT]`` line, then returns
        - the caller closes the generator (clean ``GeneratorExit``)
        - ``_MAX_CONSECUTIVE_STREAM_FAILURES`` consecutive command failures occur (RuntimeError)

        A missing file is surfaced once as a ``[TAIL]`` notice line and polling
        continues (the file may appear later, e.g. model-preload).

        Raises:
            RuntimeError: If the SSM agent is not ready within 60 seconds, or
                after repeated consecutive command failures.
        """
        if not self.wait_for_ssm_agent(instance_id, timeout_seconds=60):
            raise RuntimeError(f"SSM agent not ready on instance {instance_id} after 60 seconds")

        quoted_path = shlex.quote(path)
        offset = 0
        consecutive_failures = 0
        missing_file_notified = False
        end_time = time.monotonic() + timeout_seconds

        while time.monotonic() < end_time:
            try:
                command_id = self.send_shell_commands(
                    instance_id,
                    [f"tail -c +{offset + 1} {quoted_path}"],
                    comment=f"Tail {path}",
                    timeout_seconds=30,
                )
                result = self.wait_for_command(command_id, instance_id, timeout_seconds=30)
            except RuntimeError as exc:
                consecutive_failures += 1
                if consecutive_failures >= _MAX_CONSECUTIVE_STREAM_FAILURES:
                    raise RuntimeError(
                        f"Tailing {path} failed {consecutive_failures} consecutive times: {exc}"
                    ) from exc
                time.sleep(poll_interval)
                continue

            if result.get("Status") != "Success":
                reason = (result.get("StandardErrorContent") or result.get("StandardOutputContent") or "").strip()
                if "no such file" in reason.lower():
                    consecutive_failures = 0
                    if not missing_file_notified:
                        missing_file_notified = True
                        yield f"[TAIL] {path} not available yet: {reason}"
                else:
                    consecutive_failures += 1
                    if consecutive_failures >= _MAX_CONSECUTIVE_STREAM_FAILURES:
                        raise RuntimeError(
                            f"Tailing {path} failed {consecutive_failures} consecutive times: "
                            f"{reason or result.get('Status', 'unknown status')}"
                        )
                time.sleep(poll_interval)
                continue

            consecutive_failures = 0
            missing_file_notified = False
            chunk = result.get("StandardOutputContent", "")
            if chunk:
                offset += len(chunk.encode("utf-8"))
                yield from chunk.splitlines()
            time.sleep(poll_interval)

        yield f"[TAIL TIMEOUT] Stopped tailing {path} after {timeout_seconds}s"

    def follow_container_logs(
        self,
        instance_id: str,
        service: str,
        *,
        poll_interval: float = 3.0,
        timeout_seconds: int = 600,
    ) -> Generator[str, None, None]:
        """Follow a Docker container's logs via SSM polling.

        The first poll runs ``docker logs --timestamps --tail 50 <container>``
        to seed recent context; subsequent polls run
        ``docker logs --timestamps --since <last-timestamp> <container>`` and
        de-duplicate on the timestamp boundary (lines with a timestamp <= the
        last one seen are dropped). Yielded lines have the leading Docker
        timestamp stripped; lines without a parseable timestamp are yielded
        as-is and bypass de-duplication.

        Stop and failure semantics match :meth:`tail_file` (explicit
        ``[FOLLOW TIMEOUT]`` line, clean close(), RuntimeError after repeated
        consecutive failures, missing container surfaced once and re-polled).

        Raises:
            ValueError: If the service is not a known container-backed service
                (raised eagerly, before the generator starts).
            RuntimeError: If the SSM agent is not ready within 60 seconds, or
                after repeated consecutive command failures.
        """
        container = self.resolve_container_name(service)
        return self._follow_container_logs(
            instance_id,
            container,
            poll_interval=poll_interval,
            timeout_seconds=timeout_seconds,
        )

    def _follow_container_logs(
        self,
        instance_id: str,
        container: str,
        *,
        poll_interval: float,
        timeout_seconds: int,
    ) -> Generator[str, None, None]:
        """Inner polling generator for :meth:`follow_container_logs`."""
        if not self.wait_for_ssm_agent(instance_id, timeout_seconds=60):
            raise RuntimeError(f"SSM agent not ready on instance {instance_id} after 60 seconds")

        last_timestamp: str | None = None
        consecutive_failures = 0
        missing_container_notified = False
        end_time = time.monotonic() + timeout_seconds

        while time.monotonic() < end_time:
            if last_timestamp is None:
                command = f"docker logs --timestamps --tail 50 {container} 2>&1"
            else:
                command = f"docker logs --timestamps --since {shlex.quote(last_timestamp)} {container} 2>&1"

            try:
                command_id = self.send_shell_commands(
                    instance_id,
                    [command],
                    comment=f"Follow {container} container logs",
                    timeout_seconds=30,
                )
                result = self.wait_for_command(command_id, instance_id, timeout_seconds=30)
            except RuntimeError as exc:
                consecutive_failures += 1
                if consecutive_failures >= _MAX_CONSECUTIVE_STREAM_FAILURES:
                    raise RuntimeError(
                        f"Following {container} logs failed {consecutive_failures} consecutive times: {exc}"
                    ) from exc
                time.sleep(poll_interval)
                continue

            if result.get("Status") != "Success":
                reason = (result.get("StandardErrorContent") or result.get("StandardOutputContent") or "").strip()
                if "no such container" in reason.lower():
                    consecutive_failures = 0
                    if not missing_container_notified:
                        missing_container_notified = True
                        yield f"[FOLLOW] Container {container} not available yet: {reason}"
                else:
                    consecutive_failures += 1
                    if consecutive_failures >= _MAX_CONSECUTIVE_STREAM_FAILURES:
                        raise RuntimeError(
                            f"Following {container} logs failed {consecutive_failures} consecutive times: "
                            f"{reason or result.get('Status', 'unknown status')}"
                        )
                time.sleep(poll_interval)
                continue

            consecutive_failures = 0
            missing_container_notified = False
            for line in result.get("StandardOutputContent", "").splitlines():
                timestamp, separator, message = line.partition(" ")
                if separator and self._looks_like_docker_timestamp(timestamp):
                    if last_timestamp is not None and timestamp <= last_timestamp:
                        continue
                    last_timestamp = timestamp
                    yield message
                elif line:
                    yield line
            time.sleep(poll_interval)

        yield f"[FOLLOW TIMEOUT] Stopped following {container} logs after {timeout_seconds}s"

    @staticmethod
    def _looks_like_docker_timestamp(token: str) -> bool:
        """Return True if the token looks like a Docker RFC3339 log timestamp."""
        return len(token) >= 20 and token[:4].isdigit() and token[4:5] == "-" and "T" in token and token.endswith("Z")

    @staticmethod
    def _is_invocation_not_ready(exc: RuntimeError) -> bool:
        """Return True if the invocation has not been created yet."""
        cause = exc.__cause__
        if isinstance(cause, ClientError):
            error = cause.response.get("Error", {})
            return error.get("Code") == "InvocationDoesNotExist"
        return False


__all__ = ["CONTAINER_LOG_SERVICES", "SSMService"]
