"""HTTP/TCP health checks with retries and timing."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterable

import httpx

from geusemaker.models.health import HealthCheckConfig, HealthCheckResult


class HealthCheckClient:
    """Performs health checks against service endpoints."""

    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client or httpx.AsyncClient(follow_redirects=True)

    async def check_http(
        self,
        url: str,
        expected_status: int = 200,
        timeout_seconds: float = 10.0,
        max_retries: int = 3,
        base_delay: float = 0.5,
        max_delay: float = 5.0,
        service_name: str = "http",
    ) -> HealthCheckResult:
        """Check an HTTP endpoint with retries and timing."""
        attempt = 0
        start = time.perf_counter()
        last_error: str | None = None
        status_code: int | None = None

        while attempt <= max_retries:
            try:
                response = await self._client.get(
                    url,
                    timeout=timeout_seconds,
                )
                status_code = response.status_code
                if status_code == expected_status:
                    return HealthCheckResult(
                        service_name=service_name,
                        healthy=True,
                        status_code=status_code,
                        response_time_ms=(time.perf_counter() - start) * 1000,
                        endpoint=url,
                        retry_count=attempt,
                    )
                last_error = f"Unexpected status {status_code}"
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                last_error = str(exc)

            attempt += 1
            if attempt > max_retries:
                break
            await asyncio.sleep(min(base_delay * (2 ** (attempt - 1)), max_delay))

        return HealthCheckResult(
            service_name=service_name,
            healthy=False,
            status_code=status_code,
            response_time_ms=(time.perf_counter() - start) * 1000,
            error_message=last_error,
            endpoint=url,
            retry_count=attempt - 1,
        )

    async def check_tcp(
        self,
        host: str,
        port: int,
        timeout_seconds: float = 5.0,
        service_name: str = "tcp",
    ) -> HealthCheckResult:
        """Check a TCP endpoint by opening a socket."""
        start = time.perf_counter()
        addr = f"{host}:{port}"
        try:
            await asyncio.wait_for(
                asyncio.open_connection(host=host, port=port),
                timeout=timeout_seconds,
            )
            return HealthCheckResult(
                service_name=service_name,
                healthy=True,
                status_code=None,
                response_time_ms=(time.perf_counter() - start) * 1000,
                endpoint=addr,
            )
        except (TimeoutError, OSError) as exc:
            return HealthCheckResult(
                service_name=service_name,
                healthy=False,
                status_code=None,
                response_time_ms=(time.perf_counter() - start) * 1000,
                error_message=str(exc),
                endpoint=addr,
            )

    async def check_all(self, configs: Iterable[HealthCheckConfig]) -> list[HealthCheckResult]:
        """Run multiple checks in parallel."""
        tasks = [
            self.check_http(
                url=config.endpoint,
                expected_status=config.expected_status,
                timeout_seconds=config.timeout_seconds,
                max_retries=config.max_retries,
                base_delay=config.retry_delay_seconds,
                service_name=config.service_name,
            )
            for config in configs
        ]
        return await asyncio.gather(*tasks)


__all__ = ["HealthCheckClient"]
