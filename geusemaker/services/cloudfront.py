"""CloudFront service."""

from __future__ import annotations

import time
from typing import Any

from geusemaker.infra import AWSClientFactory
from geusemaker.services.base import BaseService


class CloudFrontService(BaseService):
    """Manage CloudFront distributions."""

    def __init__(self, client_factory: AWSClientFactory, region: str = "us-east-1"):
        # CloudFront is global; region kept for interface consistency.
        super().__init__(client_factory, region)
        self._cf = self._client("cloudfront")

    def create_distribution(self, config: dict[str, Any]) -> dict[str, Any]:
        """Create a distribution using a caller-provided config."""

        def _call() -> dict[str, Any]:
            return self._cf.create_distribution(DistributionConfig=config)  # type: ignore[no-any-return]

        return self._safe_call(_call)

    def create_distribution_with_alb_origin(
        self,
        alb_dns_name: str,
        caller_reference: str,
        enabled: bool = True,
        comment: str = "",
        cache_behaviors: list[dict[str, Any]] | None = None,
        ssl_certificate_arn: str | None = None,
        alternate_domain_names: list[str] | None = None,
        default_ttl: int = 0,
        min_ttl: int = 0,
        max_ttl: int = 0,
        compress: bool = True,
        price_class: str = "PriceClass_100",
        security_headers_policy_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Create CloudFront distribution with ALB as custom origin.

        Args:
            alb_dns_name: ALB DNS name (e.g., my-alb-123456.us-east-1.elb.amazonaws.com)
            caller_reference: Unique reference for this distribution
            enabled: Whether distribution should be enabled after creation
            comment: Optional description for the distribution
            cache_behaviors: Optional list of path-specific cache behaviors
            ssl_certificate_arn: Optional ACM certificate ARN for custom domains
            alternate_domain_names: Optional list of CNAMEs for custom domains
            default_ttl: Default TTL for cached objects (seconds)
            min_ttl: Minimum TTL for cached objects (seconds)
            max_ttl: Maximum TTL for cached objects (seconds)
            compress: Enable automatic compression for objects
            price_class: Price class (PriceClass_100, PriceClass_200, PriceClass_All)
            security_headers_policy_id: Optional managed policy ID for security headers

        Returns:
            CloudFront CreateDistribution API response with Distribution and ETag

        Raises:
            RuntimeError: If distribution creation fails
        """
        # Build origin configuration for ALB
        origin_id = f"ALB-{alb_dns_name}"
        origin = {
            "Id": origin_id,
            "DomainName": alb_dns_name,
            "CustomOriginConfig": {
                "HTTPPort": 80,
                "HTTPSPort": 443,
                "OriginProtocolPolicy": "https-only",  # Enforce HTTPS between CloudFront and ALB
                "OriginSslProtocols": {"Quantity": 1, "Items": ["TLSv1.2"]},
                "OriginReadTimeout": 30,
                "OriginKeepaliveTimeout": 5,
            },
        }

        # Build default cache behavior
        default_cache_behavior: dict[str, Any] = {
            "TargetOriginId": origin_id,
            "ViewerProtocolPolicy": "redirect-to-https",  # Enforce HTTPS for all viewers
            "AllowedMethods": {
                "Quantity": 7,
                "Items": ["HEAD", "DELETE", "POST", "GET", "OPTIONS", "PUT", "PATCH"],
                "CachedMethods": {"Quantity": 2, "Items": ["HEAD", "GET"]},
            },
            "Compress": compress,
            "ForwardedValues": {
                "QueryString": True,
                "Cookies": {"Forward": "all"},
                "Headers": {"Quantity": 1, "Items": ["Host"]},
            },
            "MinTTL": min_ttl,
            "DefaultTTL": default_ttl,
            "MaxTTL": max_ttl,
        }

        # Add security headers policy if provided
        if security_headers_policy_id:
            default_cache_behavior["ResponseHeadersPolicyId"] = security_headers_policy_id

        # Build distribution config
        distribution_config: dict[str, Any] = {
            "CallerReference": caller_reference,
            "Comment": comment,
            "Enabled": enabled,
            "Origins": {"Quantity": 1, "Items": [origin]},
            "DefaultCacheBehavior": default_cache_behavior,
            "PriceClass": price_class,
            "HttpVersion": "http2and3",
            "IsIPV6Enabled": True,
        }

        # Add cache behaviors if provided
        if cache_behaviors:
            distribution_config["CacheBehaviors"] = {
                "Quantity": len(cache_behaviors),
                "Items": cache_behaviors,
            }

        # Add SSL/custom domain configuration if provided
        if ssl_certificate_arn and alternate_domain_names:
            distribution_config["Aliases"] = {
                "Quantity": len(alternate_domain_names),
                "Items": alternate_domain_names,
            }
            distribution_config["ViewerCertificate"] = {
                "ACMCertificateArn": ssl_certificate_arn,
                "SSLSupportMethod": "sni-only",
                "MinimumProtocolVersion": "TLSv1.2_2021",
            }
        else:
            # Use default CloudFront certificate
            distribution_config["ViewerCertificate"] = {
                "CloudFrontDefaultCertificate": True,
                "MinimumProtocolVersion": "TLSv1.2_2021",
            }

        def _call() -> dict[str, Any]:
            return self._cf.create_distribution(DistributionConfig=distribution_config)  # type: ignore[no-any-return]

        return self._safe_call(_call)

    def build_cache_behavior(
        self,
        path_pattern: str,
        target_origin_id: str,
        ttl: int = 0,
        forward_all: bool = True,
        compress: bool = False,
        viewer_protocol: str = "allow-all",
    ) -> dict[str, Any]:
        """
        Build a cache behavior configuration for a specific path pattern.

        Args:
            path_pattern: Path pattern (e.g., "/n8n/*", "/static/*")
            target_origin_id: ID of the origin to route requests to
            ttl: Time to live for cached objects (seconds)
            forward_all: If True, forward all query strings, cookies, and headers
            compress: Enable automatic compression
            viewer_protocol: Viewer protocol policy (allow-all, redirect-to-https, https-only)

        Returns:
            Cache behavior configuration dict
        """
        behavior: dict[str, Any] = {
            "PathPattern": path_pattern,
            "TargetOriginId": target_origin_id,
            "ViewerProtocolPolicy": viewer_protocol,
            "AllowedMethods": {
                "Quantity": 7,
                "Items": ["HEAD", "DELETE", "POST", "GET", "OPTIONS", "PUT", "PATCH"],
                "CachedMethods": {"Quantity": 2, "Items": ["HEAD", "GET"]},
            },
            "Compress": compress,
            "MinTTL": 0,
            "DefaultTTL": ttl,
            "MaxTTL": ttl if ttl > 0 else 31536000,  # 1 year max if no caching
        }

        if forward_all:
            behavior["ForwardedValues"] = {
                "QueryString": True,
                "Cookies": {"Forward": "all"},
                "Headers": {"Quantity": 1, "Items": ["*"]},
            }
        else:
            behavior["ForwardedValues"] = {
                "QueryString": False,
                "Cookies": {"Forward": "none"},
                "Headers": {"Quantity": 0},
            }

        return behavior

    def wait_for_deployed(
        self,
        distribution_id: str,
        max_attempts: int = 60,
        delay: int = 30,
    ) -> None:
        """
        Wait for CloudFront distribution to reach 'Deployed' status.

        CloudFront distributions can take 15-30 minutes to deploy globally.

        Args:
            distribution_id: CloudFront distribution ID
            max_attempts: Maximum number of polling attempts (default 60 = 30 min)
            delay: Seconds between polling attempts (default 30s)

        Raises:
            RuntimeError: If distribution doesn't deploy within timeout or enters error state
        """

        def _call() -> None:
            for attempt in range(max_attempts):
                resp = self._cf.get_distribution(Id=distribution_id)
                status = resp["Distribution"]["Status"]

                if status == "Deployed":
                    return

                if status in ("Failed", "Cancelled"):
                    raise RuntimeError(f"Distribution entered {status} state")

                if attempt < max_attempts - 1:
                    time.sleep(delay)

            raise RuntimeError(
                f"Distribution did not deploy within {max_attempts * delay}s. "
                f"Check AWS Console for distribution {distribution_id}"
            )

        self._safe_call(_call)

    def get_distribution(self, distribution_id: str) -> dict[str, Any]:
        """
        Get CloudFront distribution details.

        Args:
            distribution_id: CloudFront distribution ID

        Returns:
            GetDistribution API response with Distribution and ETag

        Raises:
            RuntimeError: If distribution doesn't exist or API call fails
        """

        def _call() -> dict[str, Any]:
            return self._cf.get_distribution(Id=distribution_id)  # type: ignore[no-any-return]

        return self._safe_call(_call)

    def create_invalidation(
        self,
        distribution_id: str,
        paths: list[str],
        caller_reference: str,
    ) -> dict[str, Any]:
        """
        Create CloudFront cache invalidation for specified paths.

        Args:
            distribution_id: CloudFront distribution ID
            paths: List of paths to invalidate (e.g., ["/index.html", "/assets/*"])
            caller_reference: Unique reference for this invalidation

        Returns:
            CreateInvalidation API response with Invalidation and Location

        Raises:
            RuntimeError: If invalidation creation fails
        """

        def _call() -> dict[str, Any]:
            return self._cf.create_invalidation(  # type: ignore[no-any-return]
                DistributionId=distribution_id,
                InvalidationBatch={
                    "Paths": {"Quantity": len(paths), "Items": paths},
                    "CallerReference": caller_reference,
                },
            )

        return self._safe_call(_call)

    def delete_distribution(self, distribution_id: str, etag: str) -> None:
        """
        Delete CloudFront distribution.

        Distribution must be disabled before deletion and must reach 'Deployed' status.

        Args:
            distribution_id: CloudFront distribution ID
            etag: ETag from get_distribution() response

        Raises:
            RuntimeError: If deletion fails
        """

        def _call() -> None:
            self._cf.delete_distribution(Id=distribution_id, IfMatch=etag)

        self._safe_call(_call)

    def disable_distribution(self, distribution_id: str, etag: str) -> dict[str, Any]:
        """
        Disable CloudFront distribution (required before deletion).

        Args:
            distribution_id: CloudFront distribution ID
            etag: ETag from get_distribution() response

        Returns:
            UpdateDistribution API response with updated Distribution and ETag

        Raises:
            RuntimeError: If update fails
        """

        def _call() -> dict[str, Any]:
            # Get current config
            resp = self._cf.get_distribution(Id=distribution_id)
            config = resp["Distribution"]["DistributionConfig"]

            # Disable the distribution
            config["Enabled"] = False

            # Update distribution
            return self._cf.update_distribution(  # type: ignore[no-any-return]
                Id=distribution_id,
                DistributionConfig=config,
                IfMatch=etag,
            )

        return self._safe_call(_call)


__all__ = ["CloudFrontService"]
