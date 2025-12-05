from __future__ import annotations

from decimal import Decimal

from geusemaker.services.pricing import PricingCache
from geusemaker.services.pricing.efs import EFSPricingService


class EmptyPricingClient:
    def __init__(self) -> None:
        self.calls = 0

    def get_products(self, **_: object) -> dict:
        self.calls += 1
        return {"PriceList": []}


class FakeFactory:
    def __init__(self, pricing_client: EmptyPricingClient) -> None:
        self._pricing = pricing_client

    def get_client(self, service_name: str, region: str = "us-east-1") -> object:  # noqa: ARG002
        if service_name == "pricing":
            return self._pricing
        raise KeyError(service_name)


def test_efs_pricing_fallback_and_cache() -> None:
    pricing_client = EmptyPricingClient()
    factory = FakeFactory(pricing_client)
    cache = PricingCache(ttl_seconds=60)

    service = EFSPricingService(factory, cache=cache, pricing_client=pricing_client)
    pricing = service.get_pricing("us-east-1")
    assert pricing.standard_gb_month == Decimal("0.30")

    # Cached call should not increase pricing client invocations.
    _ = service.get_pricing("us-east-1")
    assert pricing_client.calls == 1
