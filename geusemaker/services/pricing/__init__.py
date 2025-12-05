"""Pricing service façade for GeuseMaker."""

from __future__ import annotations

from geusemaker.infra import AWSClientFactory
from geusemaker.models.pricing import (
    ALBPricing,
    CloudFrontPricing,
    EFSPricing,
    OnDemandPrice,
    SpotPrice,
)
from geusemaker.services.pricing.cache import PricingCache
from geusemaker.services.pricing.cloudfront import CloudFrontPricingService
from geusemaker.services.pricing.ec2 import EC2PricingService
from geusemaker.services.pricing.efs import EFSPricingService
from geusemaker.services.pricing.elb import ELBPricingService


class PricingService:
    """High-level pricing façade exposing resource-specific services."""

    def __init__(self, client_factory: AWSClientFactory, region: str = "us-east-1", cache_ttl_seconds: int = 900):
        cache = PricingCache(ttl_seconds=cache_ttl_seconds)
        self.ec2 = EC2PricingService(client_factory, cache=cache, region=region)
        self.efs = EFSPricingService(client_factory, cache=cache, region=region)
        self.elb = ELBPricingService(client_factory, cache=cache, region=region)
        self.cloudfront = CloudFrontPricingService(client_factory, cache=cache, region=region)

    def get_spot_prices(self, instance_type: str, region: str) -> list[SpotPrice]:
        return self.ec2.get_spot_prices(instance_type=instance_type, region=region)

    def get_on_demand_price(self, instance_type: str, region: str, operating_system: str = "Linux") -> OnDemandPrice:
        return self.ec2.get_on_demand_price(
            instance_type=instance_type,
            region=region,
            operating_system=operating_system,
        )

    def get_efs_pricing(self, region: str) -> EFSPricing:
        return self.efs.get_pricing(region=region)

    def get_alb_pricing(self, region: str) -> ALBPricing:
        return self.elb.get_pricing(region=region)

    def get_cloudfront_pricing(self, price_class: str = "PriceClass_100") -> CloudFrontPricing:
        return self.cloudfront.get_pricing(price_class=price_class)


__all__ = [
    "PricingService",
    "PricingCache",
    "EC2PricingService",
    "EFSPricingService",
    "ELBPricingService",
    "CloudFrontPricingService",
]
