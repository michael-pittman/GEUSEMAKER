from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from geusemaker.cli.commands import monitor as monitor_cmd
from geusemaker.cli.main import cli


def test_monitor_start_background_sets_pid(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Avoid launching real process
    spawned = {}

    def fake_popen(cmd, stdout=None, stderr=None):  # noqa: ANN001
        spawned["cmd"] = cmd

        class FakeProc:
            pid = 12345

            def __init__(self, stdout_handle, stderr_handle):  # noqa: ANN001
                spawned["stdout"] = stdout_handle
                spawned["stderr"] = stderr_handle

        return FakeProc(stdout, stderr)

    monkeypatch.setattr("geusemaker.cli.commands.monitor.subprocess.Popen", fake_popen)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "monitor",
            "demo",
            "--host",
            "localhost",
            "--background",
            "--checks",
            "1",
            "--interval",
            "10",
            "--log-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0
    pid_file = monitor_cmd._pid_path("demo")
    pid_file.unlink(missing_ok=True)
    assert spawned["stdout"].name.endswith(".monitor.out.log")
    assert spawned["stderr"].name.endswith(".monitor.err.log")


def test_monitor_stop_without_pid(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["monitor", "stop", "missing"])
    assert result.exit_code == 1


def test_monitor_start_rejects_running_pid(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pid_file = monitor_cmd._pid_path("demo")
    pid_file.write_text("99999")
    monkeypatch.setattr("geusemaker.cli.commands.monitor._pid_running", lambda pid: True)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "monitor",
            "demo",
            "--host",
            "localhost",
            "--background",
            "--checks",
            "1",
            "--interval",
            "10",
            "--log-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 1
    pid_file.unlink(missing_ok=True)


def test_monitor_stop_sends_signal(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    called = {}

    def fake_kill(pid, sig):  # noqa: ANN001
        called["pid"] = pid
        called["sig"] = sig

    monkeypatch.setattr("os.kill", fake_kill)
    pid_file = monitor_cmd._pid_path("demo")
    pid_file.write_text("123")
    runner = CliRunner()
    result = runner.invoke(cli, ["monitor", "stop", "demo"])
    assert result.exit_code == 0
    assert called["pid"] == 123
    assert pid_file.exists() is False
