from __future__ import annotations

from decimal import Decimal

from geusemaker.services.pricing import PricingCache
from geusemaker.services.pricing.elb import ELBPricingService


class FakeFactory:
    def get_client(self, service_name: str, region: str = "us-east-1") -> object:  # noqa: ARG002
        raise KeyError(service_name)


def test_elb_pricing_defaults_and_cache() -> None:
    service = ELBPricingService(FakeFactory(), cache=PricingCache(ttl_seconds=10))
    pricing = service.get_pricing("us-east-1")
    assert pricing.hourly_price == Decimal("0.0225")
    assert pricing.lcu_price == Decimal("0.008")

    cached = service.get_pricing("us-east-1")
    assert cached.hourly_price == pricing.hourly_price
