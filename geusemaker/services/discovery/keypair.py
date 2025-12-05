"""Key pair discovery service."""

from __future__ import annotations

from typing import Any

from geusemaker.infra import AWSClientFactory
from geusemaker.models.discovery import KeyPairInfo
from geusemaker.services.base import BaseService
from geusemaker.services.discovery.cache import DiscoveryCache


def _tags_to_dict(tags: list[dict[str, Any]] | None) -> dict[str, str]:
    return {tag["Key"]: tag["Value"] for tag in tags or [] if "Key" in tag and "Value" in tag}


class KeyPairDiscoveryService(BaseService):
    """List SSH key pairs in a region."""

    def __init__(
        self,
        client_factory: AWSClientFactory,
        region: str = "us-east-1",
        cache: DiscoveryCache | None = None,
    ):
        super().__init__(client_factory, region)
        self._ec2 = self._client("ec2")
        self._cache = cache or DiscoveryCache()

    def list_key_pairs(self, use_cache: bool = True) -> list[KeyPairInfo]:
        """Return key pair metadata for the region."""
        cache_key = f"keypairs:{self.region}"
        cached = self._cache.get(cache_key) if use_cache else None
        if cached is not None:
            return cached  # type: ignore[return-value]

        def _call() -> list[KeyPairInfo]:
            response = self._ec2.describe_key_pairs()
            pairs: list[KeyPairInfo] = []
            for kp in response.get("KeyPairs", []):
                tags = _tags_to_dict(kp.get("Tags"))
                key_type = (kp.get("KeyType") or "unknown").lower()
                if key_type not in ("rsa", "ed25519"):
                    key_type = "unknown"
                pairs.append(
                    KeyPairInfo(
                        key_name=kp.get("KeyName", ""),
                        key_fingerprint=kp.get("KeyFingerprint", ""),
                        key_type=key_type,  # type: ignore[arg-type]
                        created_at=kp.get("CreateTime"),
                        tags=tags,
                    ),
                )
            return pairs

        pairs = self._safe_call(_call)
        if use_cache:
            self._cache.set(cache_key, pairs)
        return pairs


__all__ = ["KeyPairDiscoveryService"]
