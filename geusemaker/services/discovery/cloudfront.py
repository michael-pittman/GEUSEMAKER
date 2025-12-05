"""CloudFront discovery and validation."""

from __future__ import annotations

from geusemaker.infra import AWSClientFactory
from geusemaker.models.discovery import CloudFrontInfo, ValidationResult
from geusemaker.services.base import BaseService
from geusemaker.services.discovery.cache import DiscoveryCache


class CloudFrontDiscoveryService(BaseService):
    """Discover CloudFront distributions (global service)."""

    def __init__(
        self,
        client_factory: AWSClientFactory,
        region: str = "us-east-1",
        cache: DiscoveryCache | None = None,
    ):
        super().__init__(client_factory, region)
        self._cloudfront = self._client("cloudfront")
        # Longer TTL because CloudFront rarely changes quickly
        self._cache = cache or DiscoveryCache(default_ttl_seconds=600)

    def list_distributions(self, use_cache: bool = True) -> list[CloudFrontInfo]:
        """Return CloudFront distributions with key metadata."""
        cache_key = "cloudfront:distributions"
        cached = self._cache.get(cache_key) if use_cache else None
        if cached is not None:
            return cached  # type: ignore[return-value]

        def _call() -> list[CloudFrontInfo]:
            resp = self._cloudfront.list_distributions()
            items = resp.get("DistributionList", {}).get("Items", []) or []
            distributions: list[CloudFrontInfo] = []
            for item in items:
                dist_id = item["Id"]
                detail = self._cloudfront.get_distribution(Id=dist_id).get(
                    "Distribution",
                    {},
                )
                config = detail.get("DistributionConfig", {})
                origins_cfg = config.get("Origins", {}).get("Items", []) or []
                origins = [origin.get("DomainName", "") for origin in origins_cfg]
                default_cache_cfg = config.get("DefaultCacheBehavior", {})
                default_cache = {
                    "target_origin": default_cache_cfg.get("TargetOriginId", ""),
                    "viewer_protocol_policy": default_cache_cfg.get(
                        "ViewerProtocolPolicy",
                        "",
                    ),
                }
                viewer_cert = config.get("ViewerCertificate", {})
                ssl_cert = viewer_cert.get("ACMCertificateArn") or viewer_cert.get(
                    "IAMCertificateId",
                )
                distributions.append(
                    CloudFrontInfo(
                        distribution_id=dist_id,
                        domain_name=item.get("DomainName", detail.get("DomainName", "")),
                        status=item.get("Status", "InProgress"),
                        origins=origins,
                        default_cache_behavior=default_cache,
                        enabled=config.get("Enabled", True),
                        ssl_certificate=ssl_cert,
                    ),
                )
            return distributions

        distributions = self._safe_call(_call)
        if use_cache:
            self._cache.set(cache_key, distributions)
        return distributions

    def validate_distribution_origin(
        self,
        distribution_id: str,
        origin_domain: str,
    ) -> ValidationResult:
        """Validate that the distribution references a given origin."""
        distribution = next(
            (dist for dist in self.list_distributions() if dist.distribution_id == distribution_id),
            None,
        )
        if distribution is None:
            return ValidationResult.failed(
                f"Distribution {distribution_id} not found",
            )
        result = ValidationResult.ok()
        if origin_domain not in distribution.origins:
            result.add_issue(
                f"Origin {origin_domain} not configured on distribution {distribution_id}",
            )
        return result


__all__ = ["CloudFrontDiscoveryService"]
