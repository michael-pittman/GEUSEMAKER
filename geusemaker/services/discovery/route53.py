"""Route 53 discovery service."""

from __future__ import annotations

from geusemaker.infra import AWSClientFactory
from geusemaker.models.discovery import HostedZoneInfo
from geusemaker.services.base import BaseService


class Route53DiscoveryService(BaseService):
    """Discover Route 53 hosted zones."""

    def __init__(self, client_factory: AWSClientFactory):
        # Route53 is a global service; region is unused for the API endpoint.
        super().__init__(client_factory, region="us-east-1")
        self._route53 = self._client("route53")

    def list_hosted_zones(self) -> list[HostedZoneInfo]:
        """List hosted zones (public + private). Caller can filter as needed."""

        def _call() -> list[HostedZoneInfo]:
            zones: list[HostedZoneInfo] = []
            paginator = self._route53.get_paginator("list_hosted_zones")
            for page in paginator.paginate():
                for z in page.get("HostedZones", []):
                    # API returns Id like "/hostedzone/Z123" - normalize to bare ID.
                    raw_id = z.get("Id", "")
                    hosted_zone_id = raw_id.split("/")[-1] if raw_id else raw_id
                    zones.append(
                        HostedZoneInfo(
                            hosted_zone_id=hosted_zone_id,
                            name=str(z.get("Name", "")).rstrip("."),
                            private_zone=bool(z.get("Config", {}).get("PrivateZone", False)),
                        )
                    )
            # Sort by name for stable interactive selection.
            zones.sort(key=lambda item: item.name)
            return zones

        return self._safe_call(_call)


__all__ = ["Route53DiscoveryService"]

