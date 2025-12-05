"""ALB service."""

from __future__ import annotations

from typing import Any

from geusemaker.infra import AWSClientFactory
from geusemaker.services.base import BaseService


class ALBService(BaseService):
    """Manage Application Load Balancers."""

    def __init__(self, client_factory: AWSClientFactory, region: str = "us-east-1"):
        super().__init__(client_factory, region)
        self._elbv2 = self._client("elbv2")

    def create_alb(
        self,
        name: str,
        subnets: list[str],
        security_groups: list[str],
        scheme: str = "internet-facing",
        tags: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Create an ALB with basic listeners."""

        def _call() -> dict[str, Any]:
            return self._elbv2.create_load_balancer(  # type: ignore[no-any-return]
                Name=name,
                Subnets=subnets,
                SecurityGroups=security_groups,
                Scheme=scheme,
                Type="application",
                IpAddressType="ipv4",
                Tags=tags or [],
            )

        return self._safe_call(_call)


__all__ = ["ALBService"]
