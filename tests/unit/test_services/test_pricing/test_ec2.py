from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

from geusemaker.services.pricing import PricingCache
from geusemaker.services.pricing.ec2 import EC2PricingService


class FakePricingClient:
    def __init__(self) -> None:
        self.calls = 0

    def get_products(self, **_: object) -> dict:
        self.calls += 1
        payload = {
            "terms": {
                "OnDemand": {
                    "abc123": {
                        "priceDimensions": {
                            "dim1": {
                                "pricePerUnit": {"USD": "0.0416"},
                            },
                        },
                    },
                },
            },
        }
        return {"PriceList": [json.dumps(payload)]}


class FakeEC2Client:
    def __init__(self) -> None:
        self.calls = 0

    def describe_spot_price_history(self, **_: object) -> dict:
        self.calls += 1
        return {
            "SpotPriceHistory": [
                {
                    "InstanceType": "t3.medium",
                    "AvailabilityZone": "us-east-1a",
                    "SpotPrice": "0.0125",
                    "Timestamp": datetime.now(UTC),
                },
            ],
        }


class FakeFactory:
    def __init__(self, pricing_client: FakePricingClient, ec2_client: FakeEC2Client) -> None:
        self._pricing = pricing_client
        self._ec2 = ec2_client

    def get_client(self, service_name: str, region: str = "us-east-1") -> object:  # noqa: ARG002
        if service_name == "pricing":
            return self._pricing
        if service_name == "ec2":
            return self._ec2
        raise KeyError(service_name)


def test_on_demand_price_parsed_and_cached() -> None:
    pricing_client = FakePricingClient()
    ec2_client = FakeEC2Client()
    factory = FakeFactory(pricing_client, ec2_client)
    cache = PricingCache(ttl_seconds=60)
    service = EC2PricingService(factory, cache=cache, pricing_client=pricing_client, ec2_client=ec2_client)

    price = service.get_on_demand_price("t3.medium", "us-east-1")
    assert price.price_per_hour == Decimal("0.0416")
    assert pricing_client.calls == 1

    second = service.get_on_demand_price("t3.medium", "us-east-1")
    assert second.price_per_hour == Decimal("0.0416")
    assert pricing_client.calls == 1  # cached


def test_spot_price_history_parsed() -> None:
    pricing_client = FakePricingClient()
    ec2_client = FakeEC2Client()
    factory = FakeFactory(pricing_client, ec2_client)
    cache = PricingCache(ttl_seconds=60)
    service = EC2PricingService(factory, cache=cache, pricing_client=pricing_client, ec2_client=ec2_client)

    prices = service.get_spot_prices("t3.medium", "us-east-1")
    assert prices[0].availability_zone == "us-east-1a"
    assert prices[0].price_per_hour == Decimal("0.0125")
    assert ec2_client.calls == 1
