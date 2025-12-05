"""ALB pricing service."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from geusemaker.infra import AWSClientFactory
from geusemaker.models.pricing import ALBPricing
from geusemaker.services.base import BaseService
from geusemaker.services.pricing.cache import PricingCache

DEFAULT_ALB = {"hourly_price": Decimal("0.0225"), "lcu_price": Decimal("0.008")}


class ELBPricingService(BaseService):
    """Return ALB pricing with sensible defaults."""

    def __init__(
        self,
        client_factory: AWSClientFactory,
        cache: PricingCache | None = None,
        region: str = "us-east-1",
        elb_client: Any | None = None,
    ):
        super().__init__(client_factory, region)
        self.cache = cache or PricingCache()
        self._elb_client = elb_client

    def get_pricing(self, region: str) -> ALBPricing:
        """Return ALB hourly and LCU pricing."""
        cache_key = f"alb:{region}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        pricing = ALBPricing(
            region=region,
            hourly_price=DEFAULT_ALB["hourly_price"],
            lcu_price=DEFAULT_ALB["lcu_price"],
        )
        # ALB pricing is largely region-neutral; caching avoids redundant calls.
        self.cache.set(cache_key, pricing)
        return pricing


__all__ = ["ELBPricingService"]
