"""EC2 pricing helpers for spot and on-demand."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from geusemaker.infra import AWSClientFactory
from geusemaker.models.pricing import OnDemandPrice, SpotPrice
from geusemaker.services.base import BaseService
from geusemaker.services.pricing.cache import PricingCache

# Map region codes to Pricing API location names.
REGION_TO_LOCATION = {
    "us-east-1": "US East (N. Virginia)",
    "us-east-2": "US East (Ohio)",
    "us-west-1": "US West (N. California)",
    "us-west-2": "US West (Oregon)",
    "eu-west-1": "EU (Ireland)",
    "eu-west-2": "EU (London)",
    "eu-central-1": "EU (Frankfurt)",
    "ap-southeast-1": "Asia Pacific (Singapore)",
    "ap-southeast-2": "Asia Pacific (Sydney)",
    "ap-northeast-1": "Asia Pacific (Tokyo)",
}

# Conservative fallback values when Pricing API is unavailable.
FALLBACK_ON_DEMAND = {
    "t3.medium": Decimal("0.0416"),
    "m5.large": Decimal("0.096"),
    "g4dn.xlarge": Decimal("0.526"),
}
DEFAULT_ON_DEMAND = Decimal("0.15")
DEFAULT_SPOT_DISCOUNT = Decimal("0.4")  # 60% cheaper than on-demand.


class EC2PricingService(BaseService):
    """Query EC2 spot and on-demand pricing with caching."""

    def __init__(
        self,
        client_factory: AWSClientFactory,
        cache: PricingCache | None = None,
        region: str = "us-east-1",
        pricing_client: Any | None = None,
        ec2_client: Any | None = None,
    ):
        super().__init__(client_factory, region)
        self.cache = cache or PricingCache()
        self._pricing_client = pricing_client or self._client_factory.get_client(
            "pricing",
            region="us-east-1",
        )
        self._ec2_client = ec2_client

    def get_spot_prices(self, instance_type: str, region: str) -> list[SpotPrice]:
        """Return recent spot prices by AZ for an instance type."""
        cache_key = f"spot:{instance_type}:{region}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        start_time = datetime.now(UTC) - timedelta(hours=1)
        client = self._ec2(region)

        def _call() -> list[SpotPrice]:
            resp = client.describe_spot_price_history(
                InstanceTypes=[instance_type],
                ProductDescriptions=["Linux/UNIX"],
                StartTime=start_time,
                MaxResults=50,
            )
            history = resp.get("SpotPriceHistory", [])
            return [
                SpotPrice(
                    instance_type=item["InstanceType"],
                    availability_zone=item["AvailabilityZone"],
                    price_per_hour=Decimal(str(item["SpotPrice"])),
                    timestamp=item["Timestamp"],
                    region=region,
                )
                for item in history
            ]

        try:
            prices = self._safe_call(_call)
            if not prices:
                raise RuntimeError("empty spot price history")
        except RuntimeError:
            prices = [
                SpotPrice(
                    instance_type=instance_type,
                    availability_zone=f"{region}a",
                    price_per_hour=self._fallback_spot_price(instance_type, region),
                    timestamp=datetime.now(UTC),
                    region=region,
                ),
            ]

        self.cache.set(cache_key, prices)
        return prices

    def get_on_demand_price(
        self,
        instance_type: str,
        region: str,
        operating_system: str = "Linux",
    ) -> OnDemandPrice:
        """Return on-demand price for an instance type."""
        cache_key = f"ondemand:{instance_type}:{region}:{operating_system}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        location = REGION_TO_LOCATION.get(region, region)

        def _call() -> OnDemandPrice:
            resp = self._pricing_client.get_products(
                ServiceCode="AmazonEC2",
                Filters=[
                    {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type},
                    {"Type": "TERM_MATCH", "Field": "location", "Value": location},
                    {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": operating_system},
                    {"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": "NA"},
                    {"Type": "TERM_MATCH", "Field": "tenancy", "Value": "Shared"},
                ],
            )
            products = resp.get("PriceList", [])
            if not products:
                raise RuntimeError("empty price list")
            product = json.loads(products[0])
            terms = product.get("terms", {}).get("OnDemand", {})
            if not terms:
                raise RuntimeError("missing on-demand terms")
            price_dimensions = next(iter(terms.values())).get("priceDimensions", {})
            dim = next(iter(price_dimensions.values()))
            price_str = dim["pricePerUnit"]["USD"]
            price = Decimal(str(price_str))
            # Handle zero or invalid prices from the API
            if price <= 0:
                raise RuntimeError("invalid zero price from API")
            return OnDemandPrice(
                instance_type=instance_type,
                price_per_hour=price,
                region=region,
                operating_system=operating_system,  # type: ignore[arg-type]
            )

        try:
            od_price = self._safe_call(_call)
        except (RuntimeError, ClientError):
            od_price = OnDemandPrice(
                instance_type=instance_type,
                price_per_hour=self._fallback_on_demand(instance_type),
                region=region,
                operating_system=operating_system,  # type: ignore[arg-type]
            )

        self.cache.set(cache_key, od_price)
        return od_price

    def _fallback_on_demand(self, instance_type: str) -> Decimal:
        return FALLBACK_ON_DEMAND.get(instance_type, DEFAULT_ON_DEMAND)

    def _fallback_spot_price(self, instance_type: str, region: str) -> Decimal:
        on_demand = self._fallback_on_demand(instance_type)
        discounted = on_demand * (Decimal(1) - DEFAULT_SPOT_DISCOUNT)
        return discounted.quantize(Decimal("0.0001"))

    def _ec2(self, region: str) -> Any:
        if self._ec2_client:
            return self._ec2_client
        return self._client_factory.get_client("ec2", region=region)


__all__ = ["EC2PricingService"]
