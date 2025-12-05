from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from geusemaker.models.monitoring import MonitoringState
from geusemaker.services.monitoring.monitor import HealthMonitor


class FakeClient:
    def __init__(self, statuses: list[bool]) -> None:
        self.statuses = statuses
        self.calls = 0

    async def check_all(self, configs):  # noqa: ANN001
        healthy = self.statuses[min(self.calls, len(self.statuses) - 1)]
        self.calls += 1
        return [
            SimpleNamespace(
                service_name="n8n",
                healthy=healthy,
                status_code=200 if healthy else 500,
                response_time_ms=10.0,
                error_message=None if healthy else "boom",
                endpoint=configs[0].endpoint if configs else "",
                retry_count=0,
            ),
        ]

    async def check_http(self, *args, **kwargs):  # noqa: ANN001
        return (await self.check_all([]))[0]

    async def check_tcp(self, **kwargs):  # noqa: ANN001
        return SimpleNamespace(
            service_name="postgres",
            healthy=True,
            status_code=None,
            response_time_ms=5.0,
            error_message=None,
            endpoint="localhost:5432",
            retry_count=0,
        )


@pytest.mark.asyncio
async def test_monitor_stops_after_iterations(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = FakeClient(statuses=[True, True])

    async def fake_check_all_services(client_param, host: str):  # noqa: ANN001
        return await client.check_all([])

    async def fake_check_postgres(client_param, host: str, port: int = 5432):  # noqa: ANN001
        return await client.check_tcp()

    monkeypatch.setattr("geusemaker.services.monitoring.monitor.check_all_services", fake_check_all_services)
    monkeypatch.setattr("geusemaker.services.monitoring.monitor.check_postgres", fake_check_postgres)

    monitor = HealthMonitor(client=client, log_dir=tmp_path)  # type: ignore[arg-type]
    state = await monitor.monitor(
        deployment_name="demo",
        host="localhost",
        interval_seconds=0,
        iterations=2,
    )
    assert state.total_checks == 2


@pytest.mark.asyncio
async def test_monitor_tracks_uptime_and_status_change(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = FakeClient(statuses=[True, False, True])

    async def fake_check_all_services(client_param, host: str):  # noqa: ANN001
        return await client.check_all([])

    async def fake_check_postgres(client_param, host: str, port: int = 5432):  # noqa: ANN001
        return await client.check_tcp()

    monkeypatch.setattr("geusemaker.services.monitoring.monitor.check_all_services", fake_check_all_services)
    monkeypatch.setattr("geusemaker.services.monitoring.monitor.check_postgres", fake_check_postgres)

    monitor = HealthMonitor(client=client, log_dir=tmp_path)  # type: ignore[arg-type]
    state = await monitor.monitor(
        deployment_name="demo",
        host="localhost",
        interval_seconds=0,
        iterations=3,
    )

    assert isinstance(state, MonitoringState)
    metrics = state.service_metrics["n8n"]
    assert metrics.total_checks == 3
    assert metrics.failed_checks == 1
    assert 0 < metrics.uptime_percentage < 100


class CollectorNotifier:
    def __init__(self) -> None:
        self.events: list[SimpleNamespace] = []

    def notify(self, event):  # noqa: ANN001
        self.events.append(event)


@pytest.mark.asyncio
async def test_monitor_emits_alert_on_unhealthy(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = FakeClient(statuses=[False, False, False])
    collector = CollectorNotifier()

    async def fake_check_all_services(client_param, host: str):  # noqa: ANN001
        return await client.check_all([])

    async def fake_check_postgres(client_param, host: str, port: int = 5432):  # noqa: ANN001
        return await client.check_tcp()

    monkeypatch.setattr("geusemaker.services.monitoring.monitor.check_all_services", fake_check_all_services)
    monkeypatch.setattr("geusemaker.services.monitoring.monitor.check_postgres", fake_check_postgres)

    monitor = HealthMonitor(client=client, notifiers=[collector], log_dir=tmp_path, alert_threshold=2)  # type: ignore[arg-type]
    await monitor.monitor(
        deployment_name="demo",
        host="localhost",
        interval_seconds=0,
        iterations=3,
    )
    alert_events = [event for event in collector.events if event.event_type == "alert"]
    assert alert_events, "Expected at least one alert event when service is unhealthy"


@pytest.mark.asyncio
async def test_monitor_reuses_state_and_updates_interval(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = FakeClient(statuses=[True])

    async def fake_check_all_services(client_param, host: str):  # noqa: ANN001
        return await client.check_all([])

    async def fake_check_postgres(client_param, host: str, port: int = 5432):  # noqa: ANN001
        return await client.check_tcp()

    monkeypatch.setattr("geusemaker.services.monitoring.monitor.check_all_services", fake_check_all_services)
    monkeypatch.setattr("geusemaker.services.monitoring.monitor.check_postgres", fake_check_postgres)

    state = MonitoringState(deployment_name="demo", check_interval_seconds=30)
    monitor = HealthMonitor(client=client, log_dir=tmp_path)  # type: ignore[arg-type]
    await monitor.monitor(
        deployment_name="demo",
        host="localhost",
        interval_seconds=5,
        iterations=1,
        state=state,
    )
    assert state.check_interval_seconds == 5
    assert state.total_checks == 1


class RecordingNotifier:
    def __init__(self) -> None:
        self.events: list[SimpleNamespace] = []

    def notify(self, event):  # noqa: ANN001
        self.events.append(event)


@pytest.mark.asyncio
async def test_monitor_records_resource_metrics_and_alerts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = FakeClient(statuses=[True])
    recorder = RecordingNotifier()

    async def fake_check_all_services(client_param, host: str):  # noqa: ANN001
        return await client.check_all([])

    async def fake_check_postgres(client_param, host: str, port: int = 5432):  # noqa: ANN001
        return await client.check_tcp()

    async def resource_sampler(host: str):  # noqa: ANN001
        return {"cpu": 95.0, "memory": 50.0, "disk": 10.0}

    monkeypatch.setattr("geusemaker.services.monitoring.monitor.check_all_services", fake_check_all_services)
    monkeypatch.setattr("geusemaker.services.monitoring.monitor.check_postgres", fake_check_postgres)

    monitor = HealthMonitor(
        client=client,  # type: ignore[arg-type]
        notifiers=[recorder],
        log_dir=tmp_path,
        resource_sampler=resource_sampler,
        alert_cooldown_seconds=60,
    )
    state = await monitor.monitor(
        deployment_name="demo",
        host="localhost",
        interval_seconds=0,
        iterations=1,
    )
    metrics = state.service_metrics["n8n"]
    assert metrics.cpu_percent == 95.0
    assert metrics.memory_percent == 50.0
    assert metrics.disk_percent == 10.0
    assert any(event.event_type == "alert" and event.service_name == "system" for event in recorder.events)


@pytest.mark.asyncio
async def test_monitor_alerts_throttled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = FakeClient(statuses=[False, False])
    recorder = RecordingNotifier()

    async def fake_check_all_services(client_param, host: str):  # noqa: ANN001
        return await client.check_all([])

    async def fake_check_postgres(client_param, host: str, port: int = 5432):  # noqa: ANN001
        return await client.check_tcp()

    monkeypatch.setattr("geusemaker.services.monitoring.monitor.check_all_services", fake_check_all_services)
    monkeypatch.setattr("geusemaker.services.monitoring.monitor.check_postgres", fake_check_postgres)

    monitor = HealthMonitor(
        client=client,  # type: ignore[arg-type]
        notifiers=[recorder],
        log_dir=tmp_path,
        alert_threshold=1,
        alert_cooldown_seconds=300,
    )
    await monitor.monitor(
        deployment_name="demo",
        host="localhost",
        interval_seconds=0,
        iterations=2,
    )
    alerts = [event for event in recorder.events if event.event_type == "alert" and event.service_name == "n8n"]
    assert len(alerts) == 1
