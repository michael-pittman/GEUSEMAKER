"""Monitor command for continuous health checks."""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

import click
from rich.live import Live

from geusemaker.cli import console
from geusemaker.cli.branding import EMOJI
from geusemaker.cli.display.monitor import render_monitor_state
from geusemaker.infra.state import StateManager
from geusemaker.models.monitoring import MonitoringState
from geusemaker.services.monitoring import HealthMonitor

PID_DIR = Path.home() / ".geusemaker" / "monitoring"
DEFAULT_LOG_DIR = Path.home() / ".geusemaker" / "logs"


class DefaultCommandGroup(click.Group):
    """Click group that falls back to a default command."""

    def __init__(self, *args: Any, default_cmd: str | None = None, **kwargs: Any):
        self.default_cmd = default_cmd
        super().__init__(*args, **kwargs)

    def parse_args(self, ctx: click.Context, args: list[str]) -> None:  # type: ignore[override]
        if self.default_cmd and args and args[0] not in self.commands:
            args.insert(0, self.default_cmd)
        super().parse_args(ctx, args)


def _pid_path(stack_name: str) -> Path:
    PID_DIR.mkdir(parents=True, exist_ok=True)
    return PID_DIR / f"{stack_name}.pid"


def _pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _ensure_pid_available(stack_name: str) -> None:
    pid_file = _pid_path(stack_name)
    if not pid_file.exists():
        return
    try:
        existing_pid = int(pid_file.read_text().strip())
    except ValueError:
        pid_file.unlink(missing_ok=True)
        return
    if _pid_running(existing_pid):
        console.print(f"{EMOJI['warning']} Monitor for {stack_name} already running (pid {existing_pid}).")
        raise SystemExit(1)
    pid_file.unlink(missing_ok=True)


@click.group("monitor", cls=DefaultCommandGroup, default_cmd="start", invoke_without_command=True)
def monitor_group() -> None:
    """Monitoring commands."""


@monitor_group.command("start")
@click.argument("stack_name")
@click.option("--host", help="Override host/IP of deployment.")
@click.option("--interval", default=60, show_default=True, help="Check interval in seconds (min 10s).")
@click.option("--checks", default=0, show_default=True, help="Number of iterations (0=infinite).")
@click.option("--background", is_flag=True, default=False, help="Run in background (writes PID file).")
@click.option(
    "--state-dir",
    type=click.Path(file_okay=False, dir_okay=True, resolve_path=True),
    help="Optional state directory (default ~/.geusemaker).",
)
@click.option(
    "--log-dir",
    type=click.Path(file_okay=False, dir_okay=True, resolve_path=True),
    help="Directory to write health event logs (default ~/.geusemaker/logs).",
)
@click.option(
    "--log-level",
    default="info",
    show_default=True,
    type=click.Choice(["debug", "info", "warning", "error"], case_sensitive=False),
    help="Log level for health event entries.",
)
@click.option(
    "--include-postgres/--skip-postgres",
    default=True,
    show_default=True,
    help="Include PostgreSQL TCP health check.",
)
def start_monitor(
    stack_name: str,
    host: str | None,
    interval: int,
    checks: int,
    background: bool,
    state_dir: str | None,
    log_dir: str | None,
    log_level: str,
    include_postgres: bool,
) -> None:
    """Start monitoring a deployment."""
    iterations = None if checks == 0 else checks
    interval = max(interval, 10)
    log_dir_path = Path(log_dir) if log_dir else DEFAULT_LOG_DIR
    log_dir_path.mkdir(parents=True, exist_ok=True)

    resolved_host = host or _load_host(stack_name, state_dir)
    if not resolved_host:
        console.print(
            f"{EMOJI['error']} Unable to resolve host for '{stack_name}'. "
            "Provide --host or ensure deployment state exists.",
        )
        raise SystemExit(1)

    if background:
        _ensure_pid_available(stack_name)
        _launch_background(
            stack_name,
            resolved_host,
            interval,
            iterations,
            log_dir_path,
            log_level,
            include_postgres,
        )
        return

    try:
        asyncio.run(
            _run_live(
                resolved_host,
                stack_name,
                interval,
                iterations,
                log_dir_path,
                log_level,
                include_postgres,
            ),
        )
    except KeyboardInterrupt:
        console.print(f"{EMOJI['warning']} Monitoring interrupted; exiting.")


def _launch_background(
    stack_name: str,
    host: str,
    interval: int,
    iterations: int | None,
    log_dir: Path,
    log_level: str,
    include_postgres: bool,
) -> None:
    pid_file = _pid_path(stack_name)
    stdout_path = log_dir / f"{stack_name}.monitor.out.log"
    stderr_path = log_dir / f"{stack_name}.monitor.err.log"
    cmd = [
        sys.executable,
        "-m",
        "geusemaker.cli.main",
        "monitor",
        "run",
        "--host",
        host,
        "--stack-name",
        stack_name,
        "--interval",
        str(interval),
        "--checks",
        str(iterations or 0),
        "--log-dir",
        str(log_dir),
        "--log-level",
        log_level.lower(),
    ]
    if not include_postgres:
        cmd.append("--skip-postgres")
    with (
        stdout_path.open("a", encoding="utf-8") as stdout_handle,
        stderr_path.open(
            "a",
            encoding="utf-8",
        ) as stderr_handle,
    ):
        proc = subprocess.Popen(cmd, stdout=stdout_handle, stderr=stderr_handle)  # noqa: S603
    pid_file.write_text(str(proc.pid))
    console.print(
        f"{EMOJI['check']} Monitoring started in background (pid {proc.pid}). "
        f"Logs: {stdout_path.name}, {stderr_path.name}",
    )


def _load_host(stack_name: str, state_dir: str | None) -> str | None:
    manager = StateManager(base_path=Path(state_dir) if state_dir else None)
    state = asyncio.run(manager.load_deployment(stack_name))
    if state is None:
        return None
    return state.public_ip or state.private_ip


@monitor_group.command("run", hidden=True)
@click.option("--host", required=True)
@click.option("--stack-name", "-s", required=True)
@click.option("--interval", default=60, show_default=True)
@click.option("--checks", default=0, show_default=True)
@click.option(
    "--log-dir",
    type=click.Path(file_okay=False, dir_okay=True, resolve_path=True),
    required=True,
)
@click.option("--log-level", default="info", show_default=True)
@click.option(
    "--include-postgres/--skip-postgres",
    default=True,
    show_default=True,
)
def run_monitor(
    host: str,
    stack_name: str,
    interval: int,
    checks: int,
    log_dir: str,
    log_level: str,
    include_postgres: bool,
) -> None:
    """Internal command used for background monitoring."""
    iterations = None if checks == 0 else checks
    interval = max(interval, 10)
    asyncio.run(
        _run_loop(
            host,
            stack_name,
            interval,
            iterations,
            Path(log_dir),
            log_level,
            include_postgres,
        ),
    )


@monitor_group.command("stop")
@click.argument("stack_name")
def stop_monitor(stack_name: str) -> None:
    """Stop a background monitor."""
    pid_file = _pid_path(stack_name)
    if not pid_file.exists():
        console.print(f"{EMOJI['warning']} No PID file found for {stack_name}.")
        raise SystemExit(1)
    pid = int(pid_file.read_text().strip())
    try:
        os.kill(pid, signal.SIGTERM)
        pid_file.unlink(missing_ok=True)
        console.print(f"{EMOJI['check']} Stopped monitor for {stack_name} (pid {pid}).")
    except ProcessLookupError:
        console.print(f"{EMOJI['warning']} Process {pid} not found; removing stale PID file.")
        pid_file.unlink(missing_ok=True)
        raise SystemExit(1)


async def _run_loop(
    host: str,
    stack_name: str,
    interval: int,
    iterations: int | None,
    log_dir: Path,
    log_level: str,
    include_postgres: bool,
) -> None:
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    monitor = HealthMonitor(log_dir=log_dir, log_level=log_level)
    await monitor.monitor(
        deployment_name=stack_name,
        host=host,
        interval_seconds=interval,
        iterations=iterations,
        include_postgres=include_postgres,
        stop_event=stop_event,
    )


async def _run_live(
    host: str,
    stack_name: str,
    interval: int,
    iterations: int | None,
    log_dir: Path,
    log_level: str,
    include_postgres: bool,
) -> None:
    monitor = HealthMonitor(log_dir=log_dir, log_level=log_level)
    state = MonitoringState(deployment_name=stack_name, check_interval_seconds=interval)

    with Live(render_monitor_state(state), refresh_per_second=4, console=console) as live:
        try:
            await monitor.monitor(
                deployment_name=stack_name,
                host=host,
                interval_seconds=interval,
                iterations=iterations,
                include_postgres=include_postgres,
                state=state,
                on_iteration=lambda s: live.update(render_monitor_state(s), refresh=True),
            )
        except KeyboardInterrupt:
            console.print(f"{EMOJI['warning']} Monitoring interrupted; returning latest snapshot.")


__all__ = ["monitor_group"]
