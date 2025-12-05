"""CloudFront service."""

from __future__ import annotations

from typing import Any

from geusemaker.infra import AWSClientFactory
from geusemaker.services.base import BaseService


class CloudFrontService(BaseService):
    """Manage CloudFront distributions."""

    def __init__(self, client_factory: AWSClientFactory, region: str = "us-east-1"):
        # CloudFront is global; region kept for interface consistency.
        super().__init__(client_factory, region)
        self._cf = self._client("cloudfront")

    def create_distribution(self, config: dict[str, Any]) -> dict[str, Any]:
        """Create a distribution using a caller-provided config."""

        def _call() -> dict[str, Any]:
            return self._cf.create_distribution(DistributionConfig=config)  # type: ignore[no-any-return]

        return self._safe_call(_call)


__all__ = ["CloudFrontService"]
