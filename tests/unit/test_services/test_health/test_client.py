from __future__ import annotations

import asyncio

import httpx
import pytest

from geusemaker.models.health import HealthCheckConfig
from geusemaker.services.health.client import HealthCheckClient


@pytest.mark.asyncio
async def test_http_check_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        return httpx.Response(200, json={"status": "ok"})

    client = HealthCheckClient(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    result = await client.check_http("http://example.com/health")

    assert result.healthy is True
    assert result.status_code == 200
    assert result.response_time_ms >= 0


@pytest.mark.asyncio
async def test_http_check_failure_with_retries() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    client = HealthCheckClient(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    result = await client.check_http(
        "http://example.com/health",
        expected_status=200,
        max_retries=2,
        base_delay=0.01,
    )

    assert result.healthy is False
    assert result.status_code == 500
    assert result.retry_count == 2
    assert calls == 3  # initial + 2 retries


@pytest.mark.asyncio
async def test_http_check_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        raise httpx.ReadTimeout("timeout")

    client = HealthCheckClient(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    result = await client.check_http(
        "http://example.com/health",
        timeout_seconds=0.01,
        max_retries=1,
        base_delay=0.01,
    )

    assert result.healthy is False
    assert "timeout" in (result.error_message or "").lower()


@pytest.mark.asyncio
async def test_tcp_check_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_open(host: str, port: int) -> tuple[object, object]:  # noqa: ARG002
        return object(), object()

    monkeypatch.setattr(asyncio, "open_connection", fake_open)
    client = HealthCheckClient()
    result = await client.check_tcp("localhost", 5432, timeout_seconds=0.1)

    assert result.healthy is True


@pytest.mark.asyncio
async def test_tcp_check_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_open(host: str, port: int) -> tuple[object, object]:  # noqa: ARG002
        raise ConnectionRefusedError("refused")

    monkeypatch.setattr(asyncio, "open_connection", fake_open)
    client = HealthCheckClient()
    result = await client.check_tcp("localhost", 5432, timeout_seconds=0.1)

    assert result.healthy is False
    assert "refused" in (result.error_message or "")


@pytest.mark.asyncio
async def test_check_all_parallel(monkeypatch: pytest.MonkeyPatch) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        return httpx.Response(200)

    client = HealthCheckClient(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    configs = [
        HealthCheckConfig(service_name="svc1", endpoint="http://example.com/a"),
        HealthCheckConfig(service_name="svc2", endpoint="http://example.com/b"),
    ]
    results = await client.check_all(configs)

    assert len(results) == 2
    assert all(result.healthy for result in results)
