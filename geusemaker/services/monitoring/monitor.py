"""Continuous health monitoring service."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path

from geusemaker.models import DeploymentState
from geusemaker.models.health import HealthCheckResult
from geusemaker.models.monitoring import HealthEvent, MonitoringState, ServiceMetrics
from geusemaker.services.health import (
    HealthCheckClient,
    check_all_services,
    check_postgres,
)
from geusemaker.services.monitoring.notifiers import (
    ConsoleNotifier,
    LogNotifier,
    Notifier,
    RichAlertNotifier,
)

LOGGER = logging.getLogger(__name__)
DEFAULT_LOG_DIR = Path.home() / ".geusemaker" / "logs"


class HealthMonitor:
    """Periodically checks service health and tracks metrics."""

    def __init__(
        self,
        client: HealthCheckClient | None = None,
        notifiers: Iterable[Notifier] | None = None,
        log_dir: Path | None = None,
        alert_threshold: int = 3,
        log_level: str = "info",
        alert_cooldown_seconds: int = 300,
        resource_sampler: Callable[[str], Awaitable[dict[str, float] | None] | dict[str, float] | None] | None = None,
        resource_thresholds: dict[str, float] | None = None,
    ):
        self._client = client or HealthCheckClient()
        self._alert_threshold = max(1, alert_threshold)
        self._recent_alerts: dict[tuple[str, str], datetime] = {}
        self._alert_cooldown_seconds = max(0, alert_cooldown_seconds)
        self._resource_sampler = resource_sampler or self._default_resource_sampler
        self._resource_thresholds = resource_thresholds or {
            "cpu": 90.0,
            "memory": 90.0,
            "disk": 95.0,
        }
        notifier_list = list(notifiers or [])

        log_path = (log_dir or DEFAULT_LOG_DIR) / "health_events.log"
        if not any(isinstance(notifier, LogNotifier) for notifier in notifier_list):
            notifier_list.append(LogNotifier(log_path, level=log_level))
        if not any(isinstance(notifier, ConsoleNotifier) for notifier in notifier_list):
            notifier_list.append(ConsoleNotifier())
        if not any(isinstance(notifier, RichAlertNotifier) for notifier in notifier_list):
            notifier_list.append(RichAlertNotifier())
        self._notifiers = notifier_list

    async def start(
        self,
        deployment: DeploymentState,
        interval_seconds: int = 60,
        iterations: int | None = None,
        include_postgres: bool = True,
        stop_event: asyncio.Event | None = None,
        on_iteration: Callable[[MonitoringState], Awaitable[None] | None] | None = None,
    ) -> MonitoringState:
        """Start monitoring using a deployment record."""
        host = deployment.public_ip or deployment.private_ip
        if not host:
            msg = "Deployment does not include a reachable host address"
            raise ValueError(msg)

        return await self.monitor(
            deployment_name=deployment.stack_name,
            host=host,
            interval_seconds=interval_seconds,
            iterations=iterations,
            include_postgres=include_postgres,
            stop_event=stop_event,
            on_iteration=on_iteration,
        )

    async def monitor(
        self,
        deployment_name: str,
        host: str,
        interval_seconds: int = 60,
        iterations: int | None = None,
        include_postgres: bool = True,
        stop_event: asyncio.Event | None = None,
        state: MonitoringState | None = None,
        on_iteration: Callable[[MonitoringState], Awaitable[None] | None] | None = None,
    ) -> MonitoringState:
        """Run monitoring for the specified number of iterations (None = infinite)."""
        state = state or MonitoringState(
            deployment_name=deployment_name,
            check_interval_seconds=interval_seconds,
        )
        state.check_interval_seconds = interval_seconds
        count = 0
        try:
            while iterations is None or count < iterations:
                await self.run_once(state, host, include_postgres)
                count += 1

                if on_iteration:
                    maybe_awaitable = on_iteration(state)
                    if asyncio.iscoroutine(maybe_awaitable):
                        await maybe_awaitable

                if iterations is not None and count >= iterations:
                    break
                if stop_event and stop_event.is_set():
                    break
                await self._sleep(interval_seconds, stop_event)
        except asyncio.CancelledError:
            LOGGER.info("Monitoring cancelled; returning latest state.")
        return state

    async def run_once(
        self,
        state: MonitoringState,
        host: str,
        include_postgres: bool = True,
    ) -> None:
        """Run a single monitoring iteration and update the provided state."""
        results = await self._run_checks(host, include_postgres)
        resources = await self._collect_resources(host)
        self._record_results(state, results, resources)

    async def _sleep(self, interval_seconds: int, stop_event: asyncio.Event | None) -> None:
        if stop_event is None:
            await asyncio.sleep(interval_seconds)
            return
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except TimeoutError:
            return

    async def _run_checks(self, host: str, include_postgres: bool) -> list[HealthCheckResult]:
        results = await check_all_services(self._client, host=host)
        if include_postgres:
            results.append(await check_postgres(self._client, host=host, port=5432))
        return results

    async def _collect_resources(self, host: str) -> dict[str, float] | None:
        try:
            sample = self._resource_sampler(host)
            if asyncio.iscoroutine(sample):
                return await sample
            return sample
        except Exception as exc:  # noqa: BLE001
            LOGGER.debug("Resource sampling failed: %s", exc)
            return None

    async def _default_resource_sampler(self, host: str) -> dict[str, float] | None:  # noqa: ARG002
        try:
            import psutil  # type: ignore
        except Exception:
            return None
        return await asyncio.to_thread(
            lambda: {
                "cpu": psutil.cpu_percent(interval=None),
                "memory": psutil.virtual_memory().percent,
                "disk": psutil.disk_usage("/").percent,
            },
        )

    def _record_results(
        self,
        state: MonitoringState,
        results: list[HealthCheckResult],
        resources: dict[str, float] | None,
    ) -> None:
        state.total_checks += 1
        resource_alert_triggered = False
        for result in results:
            metrics = state.service_metrics.get(result.service_name) or ServiceMetrics(
                service_name=result.service_name,
            )
            previous_status = metrics.last_status
            metrics.record(result.healthy, result.response_time_ms)
            if resources:
                metrics.cpu_percent = resources.get("cpu", 0.0)
                metrics.memory_percent = resources.get("memory", 0.0)
                metrics.disk_percent = resources.get("disk", 0.0)
                metrics.last_resource_check = datetime.now(UTC)
            state.service_metrics[result.service_name] = metrics

            self._notify(
                HealthEvent(
                    service_name=result.service_name,
                    event_type="check",
                    previous_status=previous_status,
                    new_status="healthy" if result.healthy else "unhealthy",
                    details=result.error_message,
                ),
            )
            if previous_status != metrics.last_status and previous_status != "unknown":
                self._notify(
                    HealthEvent(
                        service_name=result.service_name,
                        event_type="status_change",
                        previous_status=previous_status,
                        new_status=metrics.last_status,
                        details=result.error_message,
                    ),
                )
            if metrics.last_status == "unhealthy" and (
                previous_status in {"healthy", "unknown"} or metrics.consecutive_failures >= self._alert_threshold
            ):
                if self._should_alert((result.service_name, "health")):
                    self._notify(
                        HealthEvent(
                            service_name=result.service_name,
                            event_type="alert",
                            previous_status=previous_status,
                            new_status=metrics.last_status,
                            details=result.error_message or f"{metrics.consecutive_failures} consecutive failures",
                        ),
                    )
            if resources and not resource_alert_triggered:
                details = self._resource_alert_details(resources)
                if details and self._should_alert(("system", "resource")):
                    resource_alert_triggered = True
                    self._notify(
                        HealthEvent(
                            service_name="system",
                            event_type="alert",
                            previous_status=None,
                            new_status="unhealthy",
                            details=details,
                        ),
                    )

    def _resource_alert_details(self, resources: dict[str, float]) -> str | None:
        breaches: list[str] = []
        cpu = resources.get("cpu")
        mem = resources.get("memory")
        disk = resources.get("disk")
        if cpu is not None and cpu > self._resource_thresholds.get("cpu", 90.0):
            breaches.append(f"CPU {cpu:.1f}%")
        if mem is not None and mem > self._resource_thresholds.get("memory", 90.0):
            breaches.append(f"Memory {mem:.1f}%")
        if disk is not None and disk > self._resource_thresholds.get("disk", 95.0):
            breaches.append(f"Disk {disk:.1f}%")
        return "; ".join(breaches) if breaches else None

    def _should_alert(self, key: tuple[str, str]) -> bool:
        now = datetime.now(UTC)
        last = self._recent_alerts.get(key)
        if last and (now - last).total_seconds() < self._alert_cooldown_seconds:
            return False
        self._recent_alerts[key] = now
        return True

    def _notify(self, event: HealthEvent) -> None:
        for notifier in self._notifiers:
            try:
                notifier.notify(event)
            except Exception as exc:  # noqa: BLE001
                LOGGER.debug("Notifier error: %s", exc)


__all__ = ["HealthMonitor"]
