"""EFS pricing service."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from geusemaker.infra import AWSClientFactory
from geusemaker.models.pricing import EFSPricing
from geusemaker.services.base import BaseService
from geusemaker.services.pricing.cache import PricingCache
from geusemaker.services.pricing.ec2 import REGION_TO_LOCATION

DEFAULT_EFS = {"standard_gb_month": Decimal("0.30"), "ia_gb_month": Decimal("0.025")}


class EFSPricingService(BaseService):
    """Query or estimate EFS pricing."""

    def __init__(
        self,
        client_factory: AWSClientFactory,
        cache: PricingCache | None = None,
        region: str = "us-east-1",
        pricing_client: Any | None = None,
    ):
        super().__init__(client_factory, region)
        self.cache = cache or PricingCache()
        self._pricing_client = pricing_client or self._client_factory.get_client(
            "pricing",
            region="us-east-1",
        )

    def get_pricing(self, region: str) -> EFSPricing:
        """Return EFS pricing for a region."""
        cache_key = f"efs:{region}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        location = REGION_TO_LOCATION.get(region, region)

        def _call() -> EFSPricing:
            resp = self._pricing_client.get_products(
                ServiceCode="AmazonEFS",
                Filters=[
                    {"Type": "TERM_MATCH", "Field": "productFamily", "Value": "Storage"},
                    {"Type": "TERM_MATCH", "Field": "location", "Value": location},
                ],
            )
            products = resp.get("PriceList", [])
            if not products:
                raise RuntimeError("empty EFS price list")
            product = json.loads(products[0])
            terms = product.get("terms", {}).get("OnDemand", {})
            dim = next(iter(next(iter(terms.values())).get("priceDimensions", {}).values()))
            price_str = dim["pricePerUnit"]["USD"]
            price = Decimal(str(price_str))
            return EFSPricing(
                region=region,
                standard_gb_month=price,
                ia_gb_month=DEFAULT_EFS["ia_gb_month"],
                throughput_mibps=None,
            )

        try:
            pricing = self._safe_call(_call)
        except RuntimeError:
            pricing = EFSPricing(
                region=region,
                standard_gb_month=DEFAULT_EFS["standard_gb_month"],
                ia_gb_month=DEFAULT_EFS["ia_gb_month"],
                throughput_mibps=None,
            )

        self.cache.set(cache_key, pricing)
        return pricing


__all__ = ["EFSPricingService"]
