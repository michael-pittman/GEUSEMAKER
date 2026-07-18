"""Tests for SSMService streaming primitives (tail_file, follow_container_logs).

These tests drive the generators with a stubbed command layer so no boto3
client is ever created (avoids environment-dependent botocore failures).
"""

from __future__ import annotations

from typing import Any

import pytest

from geusemaker.services.ssm import SSMService, UserdataCompletion, UserdataLogStream


class StreamingStubSSM(SSMService):
    """SSMService with the SSM command transport stubbed out.

    Deliberately skips SSMService.__init__ so no boto3 client is created;
    the streaming generators only use the three methods overridden here.
    """

    def __init__(self, results: list[dict[str, Any] | RuntimeError], agent_ready: bool = True) -> None:
        self.sent_commands: list[str] = []
        self.agent_waits: int = 0
        self._results = list(results)
        self._agent_ready = agent_ready

    def wait_for_ssm_agent(
        self,
        instance_id: str,
        timeout_seconds: int = 60,
        poll_interval: float = 5.0,
    ) -> bool:
        self.agent_waits += 1
        return self._agent_ready

    def send_shell_commands(
        self,
        instance_ids: Any,
        commands: list[str],
        comment: str | None = None,
        timeout_seconds: int = 900,
    ) -> str:
        self.sent_commands.append(commands[0])
        return f"cmd-{len(self.sent_commands)}"

    def wait_for_command(
        self,
        command_id: str,
        instance_id: str,
        timeout_seconds: int = 900,
        poll_interval: float = 2.0,
    ) -> dict[str, Any]:
        if not self._results:
            raise AssertionError("Stub exhausted: generator polled more often than expected")
        item = self._results.pop(0)
        if isinstance(item, RuntimeError):
            raise item
        return item


def _success(stdout: str) -> dict[str, Any]:
    return {"Status": "Success", "StandardOutputContent": stdout, "StandardErrorContent": ""}


def _failure(stderr: str) -> dict[str, Any]:
    return {"Status": "Failed", "StandardOutputContent": "", "StandardErrorContent": stderr}


# ---------------------------------------------------------------------------
# tail_file
# ---------------------------------------------------------------------------


def test_tail_file_resumes_from_byte_offset() -> None:
    """The tail -c offset advances by the bytes received each poll."""
    stub = StreamingStubSSM(
        results=[
            _success("line1\nline2\n"),  # 12 bytes
            _success("line3\n"),  # 6 bytes
        ]
    )
    gen = stub.tail_file("i-123", "/var/log/geusemaker/model-preload.log", poll_interval=0)

    assert next(gen) == "line1"
    assert next(gen) == "line2"
    assert next(gen) == "line3"
    gen.close()

    assert stub.agent_waits == 1
    assert stub.sent_commands[0] == "tail -c +1 /var/log/geusemaker/model-preload.log"
    assert stub.sent_commands[1] == "tail -c +13 /var/log/geusemaker/model-preload.log"


def test_tail_file_quotes_path() -> None:
    """Paths with shell metacharacters are quoted safely."""
    stub = StreamingStubSSM(results=[_success("hello\n")])
    gen = stub.tail_file("i-123", "/var/log/my logs/app.log", poll_interval=0)

    assert next(gen) == "hello"
    gen.close()

    assert stub.sent_commands[0] == "tail -c +1 '/var/log/my logs/app.log'"


def test_tail_file_yields_only_appended_content() -> None:
    """Each poll yields only the new chunk, not previously seen lines."""
    stub = StreamingStubSSM(
        results=[
            _success("a\n"),
            _success(""),  # nothing new
            _success("b\n"),
        ]
    )
    gen = stub.tail_file("i-123", "/var/log/x.log", poll_interval=0)

    assert next(gen) == "a"
    assert next(gen) == "b"
    gen.close()
    assert len(stub.sent_commands) == 3


def test_tail_file_honors_close() -> None:
    """close() stops the generator cleanly without further polling."""
    stub = StreamingStubSSM(results=[_success("a\n"), _success("b\n")])
    gen = stub.tail_file("i-123", "/var/log/x.log", poll_interval=0)

    assert next(gen) == "a"
    gen.close()

    with pytest.raises(StopIteration):
        next(gen)
    assert len(stub.sent_commands) == 1


def test_tail_file_times_out_explicitly() -> None:
    """An exhausted timeout yields an explicit final timeout line."""
    stub = StreamingStubSSM(results=[])
    gen = stub.tail_file("i-123", "/var/log/x.log", poll_interval=0, timeout_seconds=0)

    lines = list(gen)
    assert lines == ["[TAIL TIMEOUT] Stopped tailing /var/log/x.log after 0s"]
    assert stub.sent_commands == []


def test_tail_file_surfaces_missing_file_once_and_keeps_polling() -> None:
    """A missing file is reported once and polling continues until it appears."""
    missing = "tail: cannot open '/var/log/x.log' for reading: No such file or directory"
    stub = StreamingStubSSM(
        results=[
            _failure(missing),
            _failure(missing),
            _success("appeared\n"),
        ]
    )
    gen = stub.tail_file("i-123", "/var/log/x.log", poll_interval=0)

    first = next(gen)
    assert first.startswith("[TAIL]")
    assert "No such file" in first
    # The second missing-file failure is NOT re-surfaced; next yield is content.
    assert next(gen) == "appeared"
    gen.close()
    assert len(stub.sent_commands) == 3


def test_tail_file_raises_after_consecutive_failures() -> None:
    """Non-missing-file failures raise RuntimeError after 3 consecutive polls."""
    stub = StreamingStubSSM(
        results=[
            _failure("permission denied"),
            _failure("permission denied"),
            _failure("permission denied"),
        ]
    )
    gen = stub.tail_file("i-123", "/var/log/x.log", poll_interval=0)

    with pytest.raises(RuntimeError, match="3 consecutive times"):
        next(gen)


def test_tail_file_raises_after_consecutive_transport_errors() -> None:
    """RuntimeError from the SSM transport also counts toward the failure cap."""
    stub = StreamingStubSSM(
        results=[
            RuntimeError("AWS call failed: throttled"),
            RuntimeError("AWS call failed: throttled"),
            RuntimeError("AWS call failed: throttled"),
        ]
    )
    gen = stub.tail_file("i-123", "/var/log/x.log", poll_interval=0)

    with pytest.raises(RuntimeError, match="3 consecutive times"):
        next(gen)


def test_tail_file_failure_counter_resets_on_success() -> None:
    """A successful poll resets the consecutive failure counter."""
    stub = StreamingStubSSM(
        results=[
            _failure("permission denied"),
            _failure("permission denied"),
            _success("ok\n"),
            _failure("permission denied"),
            _failure("permission denied"),
            _success("again\n"),
        ]
    )
    gen = stub.tail_file("i-123", "/var/log/x.log", poll_interval=0)

    assert next(gen) == "ok"
    assert next(gen) == "again"
    gen.close()


def test_tail_file_raises_when_agent_not_ready() -> None:
    """SSM agent never coming online raises RuntimeError like stream_userdata_logs."""
    stub = StreamingStubSSM(results=[], agent_ready=False)
    gen = stub.tail_file("i-123", "/var/log/x.log", poll_interval=0)

    with pytest.raises(RuntimeError, match="SSM agent not ready"):
        next(gen)


# ---------------------------------------------------------------------------
# follow_container_logs
# ---------------------------------------------------------------------------


def test_follow_container_logs_unknown_service_raises_value_error() -> None:
    """Unknown services raise ValueError eagerly (before the generator runs)."""
    stub = StreamingStubSSM(results=[])
    with pytest.raises(ValueError, match="Unknown service 'redis'"):
        stub.follow_container_logs("i-123", "redis")
    assert stub.agent_waits == 0


def test_follow_container_logs_targets_container_and_seeds_with_tail() -> None:
    """The docker command targets the mapped container; first poll seeds via --tail."""
    stub = StreamingStubSSM(results=[_success("2026-07-17T10:00:00.000000001Z hello\n")])
    gen = stub.follow_container_logs("i-123", "qdrant", poll_interval=0)

    assert next(gen) == "hello"
    gen.close()

    assert stub.sent_commands[0] == "docker logs --timestamps --tail 50 qdrant 2>&1"


def test_follow_container_logs_dedupes_on_timestamp_boundary() -> None:
    """Overlapping polls drop lines at or before the last timestamp seen."""
    stub = StreamingStubSSM(
        results=[
            _success("2026-07-17T10:00:00.000000001Z alpha\n2026-07-17T10:00:00.000000002Z beta\n"),
            _success(
                "2026-07-17T10:00:00.000000001Z alpha\n"
                "2026-07-17T10:00:00.000000002Z beta\n"
                "2026-07-17T10:00:00.000000003Z gamma\n"
            ),
        ]
    )
    gen = stub.follow_container_logs("i-123", "n8n", poll_interval=0)

    assert next(gen) == "alpha"
    assert next(gen) == "beta"
    assert next(gen) == "gamma"
    gen.close()

    assert stub.sent_commands[1] == ("docker logs --timestamps --since 2026-07-17T10:00:00.000000002Z n8n 2>&1")


def test_follow_container_logs_yields_unparseable_lines_verbatim() -> None:
    """Lines without a Docker timestamp bypass de-duplication and keep their text."""
    stub = StreamingStubSSM(results=[_success("not-a-timestamp raw line\n")])
    gen = stub.follow_container_logs("i-123", "postgres", poll_interval=0)

    assert next(gen) == "not-a-timestamp raw line"
    gen.close()


def test_follow_container_logs_times_out_explicitly() -> None:
    """An exhausted timeout yields an explicit final timeout line."""
    stub = StreamingStubSSM(results=[])
    gen = stub.follow_container_logs("i-123", "ollama", poll_interval=0, timeout_seconds=0)

    lines = list(gen)
    assert lines == ["[FOLLOW TIMEOUT] Stopped following ollama logs after 0s"]


def test_follow_container_logs_missing_container_surfaced_once() -> None:
    """A missing container is reported once and polling continues."""
    missing = "Error: No such container: crawl4ai"
    stub = StreamingStubSSM(
        results=[
            _failure(missing),
            _failure(missing),
            _success("2026-07-17T10:00:00.000000001Z started\n"),
        ]
    )
    gen = stub.follow_container_logs("i-123", "crawl4ai", poll_interval=0)

    first = next(gen)
    assert first.startswith("[FOLLOW]")
    assert "No such container" in first
    assert next(gen) == "started"
    gen.close()


def test_follow_container_logs_raises_after_consecutive_failures() -> None:
    """Persistent non-missing-container failures raise RuntimeError."""
    stub = StreamingStubSSM(
        results=[
            _failure("docker daemon not running"),
            _failure("docker daemon not running"),
            _failure("docker daemon not running"),
        ]
    )
    gen = stub.follow_container_logs("i-123", "n8n", poll_interval=0)

    with pytest.raises(RuntimeError, match="3 consecutive times"):
        next(gen)


def test_follow_container_logs_raises_when_agent_not_ready() -> None:
    """SSM agent never coming online raises RuntimeError."""
    stub = StreamingStubSSM(results=[], agent_ready=False)
    gen = stub.follow_container_logs("i-123", "n8n", poll_interval=0)

    with pytest.raises(RuntimeError, match="SSM agent not ready"):
        next(gen)


# ---------------------------------------------------------------------------
# stream_userdata_logs — typed terminal completion
# ---------------------------------------------------------------------------


def _drain(gen: Any) -> tuple[list[str], Any]:
    """Consume a generator, returning (yielded lines, StopIteration.value)."""
    lines: list[str] = []
    try:
        while True:
            lines.append(next(gen))
    except StopIteration as stop:
        return lines, stop.value


def test_stream_userdata_logs_success_on_completion_marker() -> None:
    """The completion marker terminates the stream with SUCCESS."""
    stub = StreamingStubSSM(results=[_success("Installing docker...\nGeuseMaker initialization complete!\n")])
    gen = stub.stream_userdata_logs("i-123", poll_interval=0)

    lines, completion = _drain(gen)

    assert completion is UserdataCompletion.SUCCESS
    assert "Installing docker..." in lines
    assert "GeuseMaker initialization complete!" in lines
    # Only the single tail poll was needed; no guard check after the marker.
    assert len(stub.sent_commands) == 1


def test_stream_userdata_logs_success_on_completion_guard() -> None:
    """A completion guard file (no marker line) terminates with SUCCESS."""
    stub = StreamingStubSSM(
        results=[
            _success("boot line\n"),  # tail poll
            _success("done"),  # completion guard check -> done
        ]
    )
    gen = stub.stream_userdata_logs("i-123", poll_interval=0)

    lines, completion = _drain(gen)

    assert completion is UserdataCompletion.SUCCESS
    assert lines == ["boot line"]
    assert stub.sent_commands[-1] == ("[ -f /var/lib/geusemaker/userdata-complete ] && echo 'done' || echo 'running'")


def test_stream_userdata_logs_error_on_error_marker_and_guard() -> None:
    """An error marker confirmed by the error guard terminates with ERROR."""
    stub = StreamingStubSSM(
        results=[
            _success("ERROR: userdata failed at line 42\n"),  # tail poll
            _success("error"),  # error guard check -> error
        ]
    )
    gen = stub.stream_userdata_logs("i-123", poll_interval=0)

    lines, completion = _drain(gen)

    assert completion is UserdataCompletion.ERROR
    assert lines == ["ERROR: userdata failed at line 42"]
    assert stub.sent_commands[-1] == "[ -f /var/lib/geusemaker/userdata-error ] && echo 'error' || echo 'ok'"


def test_stream_userdata_logs_timeout_when_no_terminal_marker() -> None:
    """Exhausting the timeout without a terminal marker yields TIMEOUT."""
    stub = StreamingStubSSM(results=[])
    gen = stub.stream_userdata_logs("i-123", poll_interval=0, timeout_seconds=0)

    lines, completion = _drain(gen)

    assert completion is UserdataCompletion.TIMEOUT
    assert lines == []
    # No polling happened, but the agent readiness check still ran.
    assert stub.agent_waits == 1
    assert stub.sent_commands == []


def test_stream_userdata_logs_raises_when_agent_not_ready() -> None:
    """SSM agent never coming online raises RuntimeError (unchanged behavior)."""
    stub = StreamingStubSSM(results=[], agent_ready=False)
    gen = stub.stream_userdata_logs("i-123", poll_interval=0)

    with pytest.raises(RuntimeError, match="SSM agent not ready"):
        next(gen)


def test_userdata_log_stream_captures_completion() -> None:
    """UserdataLogStream exposes the terminal reason after full iteration."""
    stub = StreamingStubSSM(results=[_success("line1\nGeuseMaker initialization complete!\n")])
    stream = UserdataLogStream(stub.stream_userdata_logs("i-123", poll_interval=0))

    lines = list(stream)

    assert stream.completion is UserdataCompletion.SUCCESS
    assert "line1" in lines


def test_userdata_log_stream_completion_none_when_abandoned() -> None:
    """Abandoning iteration early leaves completion as None."""
    stub = StreamingStubSSM(results=[_success("boot line\n"), _success("done")])
    stream = UserdataLogStream(stub.stream_userdata_logs("i-123", poll_interval=0))

    assert next(stream) == "boot line"
    stream.close()

    assert stream.completion is None


def test_resolve_container_name_known_services() -> None:
    """All known services resolve to their container names (case-insensitive)."""
    for service in ("n8n", "ollama", "qdrant", "crawl4ai", "postgres"):
        assert SSMService.resolve_container_name(service) == service
    assert SSMService.resolve_container_name("N8N") == "n8n"


def test_resolve_container_name_unknown_service() -> None:
    """Unknown services raise ValueError listing the known set."""
    with pytest.raises(ValueError, match="Known services"):
        SSMService.resolve_container_name("userdata")
