"""Service-specific health checks.

Service containers bind their ports to 127.0.0.1 on the instance, so remote
health checks must go through the host NGINX reverse proxy (port 80/443)
using its path-based routing rather than hitting service ports directly.
"""

from __future__ import annotations

from collections.abc import Iterable

from geusemaker.models.health import HealthCheckConfig, HealthCheckResult
from geusemaker.services.health.client import HealthCheckClient

# NGINX path routes (see nginx-reverse-proxy.conf.j2 / nginx-ssl.conf.j2).
# Prefix is stripped before proxying, so append each service's own health path.
NGINX_ROUTES = {
    "n8n": "/",
    "ollama": "/api/ollama/api/version",
    "qdrant": "/qdrant/healthz",
    "qdrant-ui": "/qdrant-ui/",
    "crawl4ai": "/crawl4ai/health",
}


def _http_config(service_name: str, host: str, path: str) -> HealthCheckConfig:
    return HealthCheckConfig(
        service_name=service_name,
        endpoint=f"http://{host}{path}",
    )


async def check_n8n(client: HealthCheckClient, host: str) -> HealthCheckResult:
    return await client.check_http(
        url=_http_config("n8n", host, NGINX_ROUTES["n8n"]).endpoint,
        service_name="n8n",
    )


async def check_ollama(client: HealthCheckClient, host: str) -> HealthCheckResult:
    return await client.check_http(
        url=_http_config("ollama", host, NGINX_ROUTES["ollama"]).endpoint,
        service_name="ollama",
    )


async def check_qdrant(client: HealthCheckClient, host: str) -> HealthCheckResult:
    return await client.check_http(
        url=_http_config("qdrant", host, NGINX_ROUTES["qdrant"]).endpoint,
        service_name="qdrant",
    )


async def check_qdrant_ui(client: HealthCheckClient, host: str) -> HealthCheckResult:
    """Check Qdrant built-in Web UI (dashboard) health."""
    return await client.check_http(
        url=_http_config("qdrant-ui", host, NGINX_ROUTES["qdrant-ui"]).endpoint,
        service_name="qdrant-ui",
    )


async def check_crawl4ai(client: HealthCheckClient, host: str) -> HealthCheckResult:
    return await client.check_http(
        url=_http_config("crawl4ai", host, NGINX_ROUTES["crawl4ai"]).endpoint,
        service_name="crawl4ai",
    )


async def check_postgres(client: HealthCheckClient, host: str, port: int = 5432) -> HealthCheckResult:
    return await client.check_tcp(host=host, port=port, service_name="postgres")


async def check_all_services(client: HealthCheckClient, host: str) -> list[HealthCheckResult]:
    """Run all health checks in parallel for defaults."""
    return await client.check_all(_default_configs(host))


def _default_configs(host: str) -> Iterable[HealthCheckConfig]:
    return [_http_config(name, host, path) for name, path in NGINX_ROUTES.items()]


__all__ = [
    "NGINX_ROUTES",
    "check_all_services",
    "check_n8n",
    "check_ollama",
    "check_qdrant",
    "check_qdrant_ui",
    "check_crawl4ai",
    "check_postgres",
]
