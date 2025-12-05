"""Base service helper with cached AWS clients."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from botocore.exceptions import (  # type: ignore[import-untyped]
    BotoCoreError,
    ClientError,
)

from geusemaker.infra import AWSClientFactory

_T = TypeVar("_T")


class BaseService:
    """Base class for AWS-backed services."""

    def __init__(self, client_factory: AWSClientFactory, region: str = "us-east-1"):
        self._client_factory = client_factory
        self.region = region

    def _client(self, service_name: str) -> Any:
        """Return a cached boto3 client."""
        return self._client_factory.get_client(service_name, region=self.region)

    def _safe_call(self, fn: Callable[[], _T]) -> _T:
        """Wrap a boto3 call to provide consistent error handling."""
        try:
            return fn()
        except (ClientError, BotoCoreError) as exc:
            raise RuntimeError(f"AWS call failed: {exc}") from exc


__all__ = ["BaseService"]
