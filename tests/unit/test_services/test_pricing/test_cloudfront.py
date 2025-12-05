from __future__ import annotations

from decimal import Decimal

from geusemaker.services.pricing import PricingCache
from geusemaker.services.pricing.cloudfront import CloudFrontPricingService


class FakeFactory:
    def get_client(self, service_name: str, region: str = "us-east-1") -> object:  # noqa: ARG002
        raise KeyError(service_name)


def test_cloudfront_pricing_defaults_and_cache() -> None:
    service = CloudFrontPricingService(FakeFactory(), cache=PricingCache(ttl_seconds=10))
    pricing = service.get_pricing("PriceClass_100")
    assert pricing.data_transfer_gb == Decimal("0.085")

    cached = service.get_pricing("PriceClass_100")
    assert cached.price_class == "PriceClass_100"
