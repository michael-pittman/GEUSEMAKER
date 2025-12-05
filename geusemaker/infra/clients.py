"""AWS client factory with caching."""

from __future__ import annotations

import logging
from typing import Any

from boto3 import Session  # type: ignore[import-untyped]
from botocore.exceptions import (  # type: ignore[import-untyped]
    BotoCoreError,
    NoCredentialsError,
)

LOGGER = logging.getLogger(__name__)


class AWSClientFactory:
    """Factory for creating authenticated AWS clients."""

    def __init__(self, profile_name: str | None = None):
        self._session = Session(profile_name=profile_name)
        self._clients: dict[str, Any] = {}

    def get_client(self, service: str, region: str = "us-east-1") -> Any:
        """Get or create a cached boto3 client."""
        key = f"{service}:{region}"
        if key not in self._clients:
            try:
                self._clients[key] = self._session.client(
                    service_name=service,
                    region_name=region,
                )
            except (BotoCoreError, NoCredentialsError) as exc:
                LOGGER.error("Failed to create %s client: %s", service, exc)
                raise
        return self._clients[key]

    def clear_cache(self) -> None:
        """Clear cached clients (useful for testing)."""
        self._clients.clear()


__all__ = ["AWSClientFactory"]
