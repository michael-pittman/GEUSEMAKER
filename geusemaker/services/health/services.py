"""Service-specific health checks."""

from __future__ import annotations

from collections.abc import Iterable

from geusemaker.models.health import HealthCheckConfig, HealthCheckResult
from geusemaker.services.health.client import HealthCheckClient


def _http_config(service_name: str, host: str, port: int, path: str) -> HealthCheckConfig:
    return HealthCheckConfig(
        service_name=service_name,
        endpoint=f"http://{host}:{port}{path}",
    )


async def check_n8n(client: HealthCheckClient, host: str, port: int = 5678) -> HealthCheckResult:
    return await client.check_http(
        url=_http_config("n8n", host, port, "/healthz").endpoint,
        service_name="n8n",
    )


async def check_ollama(client: HealthCheckClient, host: str, port: int = 11434) -> HealthCheckResult:
    return await client.check_http(
        url=_http_config("ollama", host, port, "/api/version").endpoint,
        service_name="ollama",
    )


async def check_qdrant(client: HealthCheckClient, host: str, port: int = 6333) -> HealthCheckResult:
    return await client.check_http(
        url=_http_config("qdrant", host, port, "/health").endpoint,
        service_name="qdrant",
    )


async def check_qdrant_ui(client: HealthCheckClient, host: str, port: int = 6333) -> HealthCheckResult:
    """Check Qdrant built-in Web UI (dashboard) health."""
    return await client.check_http(
        url=_http_config("qdrant-ui", host, port, "/dashboard").endpoint,
        service_name="qdrant-ui",
    )


async def check_crawl4ai(client: HealthCheckClient, host: str, port: int = 11235) -> HealthCheckResult:
    return await client.check_http(
        url=_http_config("crawl4ai", host, port, "/health").endpoint,
        service_name="crawl4ai",
    )


async def check_postgres(client: HealthCheckClient, host: str, port: int = 5432) -> HealthCheckResult:
    return await client.check_tcp(host=host, port=port, service_name="postgres")


async def check_all_services(client: HealthCheckClient, host: str) -> list[HealthCheckResult]:
    """Run all health checks in parallel for defaults."""
    return await client.check_all(_default_configs(host))


def _default_configs(host: str) -> Iterable[HealthCheckConfig]:
    return [
        _http_config("n8n", host, 5678, "/healthz"),
        _http_config("ollama", host, 11434, "/api/version"),
        _http_config("qdrant", host, 6333, "/health"),
        _http_config("qdrant-ui", host, 6333, "/dashboard"),
        _http_config("crawl4ai", host, 11235, "/health"),
    ]


__all__ = [
    "check_all_services",
    "check_n8n",
    "check_ollama",
    "check_qdrant",
    "check_qdrant_ui",
    "check_crawl4ai",
    "check_postgres",
]
