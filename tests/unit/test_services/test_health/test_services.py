from __future__ import annotations

import httpx
import pytest

from geusemaker.services.health.client import HealthCheckClient
from geusemaker.services.health.services import (
    check_all_services,
    check_crawl4ai,
    check_n8n,
    check_ollama,
    check_postgres,
    check_qdrant,
    check_qdrant_ui,
)


def _mock_client(status: int = 200) -> HealthCheckClient:
    async def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        return httpx.Response(status)

    return HealthCheckClient(httpx.AsyncClient(transport=httpx.MockTransport(handler)))


@pytest.mark.asyncio
async def test_service_specific_checks_use_expected_paths() -> None:
    client = _mock_client()
    host = "1.2.3.4"
    for checker in (check_n8n, check_ollama, check_qdrant, check_qdrant_ui, check_crawl4ai):
        result = await checker(client, host=host)
        assert result.healthy is True
        assert host in result.endpoint


@pytest.mark.asyncio
async def test_postgres_check_via_tcp(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_open(host: str, port: int):  # noqa: ARG002
        return object(), object()

    monkeypatch.setattr("asyncio.open_connection", fake_open)
    client = _mock_client()
    result = await check_postgres(client, host="db.local", port=5432)
    assert result.healthy is True
    assert "db.local" in result.endpoint


@pytest.mark.asyncio
async def test_check_all_services_runs_parallel() -> None:
    client = _mock_client()
    results = await check_all_services(client, host="localhost")
    assert len(results) == 5  # n8n, ollama, qdrant, qdrant-ui, crawl4ai
    assert all(res.healthy for res in results)
