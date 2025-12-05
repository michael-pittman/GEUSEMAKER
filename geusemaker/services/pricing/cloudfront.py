"""CloudFront pricing service."""

from __future__ import annotations

from decimal import Decimal

from geusemaker.infra import AWSClientFactory
from geusemaker.models.pricing import CloudFrontPricing
from geusemaker.services.base import BaseService
from geusemaker.services.pricing.cache import PricingCache

DEFAULT_CF = {
    "PriceClass_100": CloudFrontPricing(
        price_class="PriceClass_100",
        data_transfer_gb=Decimal("0.085"),
        requests_per_10k=Decimal("0.0075"),
    ),
    "PriceClass_200": CloudFrontPricing(
        price_class="PriceClass_200",
        data_transfer_gb=Decimal("0.12"),
        requests_per_10k=Decimal("0.0090"),
    ),
    "PriceClass_All": CloudFrontPricing(
        price_class="PriceClass_All",
        data_transfer_gb=Decimal("0.14"),
        requests_per_10k=Decimal("0.0100"),
    ),
}


class CloudFrontPricingService(BaseService):
    """Provide CloudFront pricing by price class."""

    def __init__(
        self,
        client_factory: AWSClientFactory,
        cache: PricingCache | None = None,
        region: str = "us-east-1",
    ):
        super().__init__(client_factory, region)
        self.cache = cache or PricingCache()

    def get_pricing(self, price_class: str = "PriceClass_100") -> CloudFrontPricing:
        """Return CloudFront pricing for a price class."""
        cache_key = f"cloudfront:{price_class}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        pricing = DEFAULT_CF.get(price_class, DEFAULT_CF["PriceClass_100"])
        self.cache.set(cache_key, pricing)
        return pricing


__all__ = ["CloudFrontPricingService"]
