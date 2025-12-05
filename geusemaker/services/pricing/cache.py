"""Lightweight TTL cache for pricing data."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any


class PricingCache:
    """Simple in-memory cache with TTL semantics."""

    def __init__(self, ttl_seconds: int = 900):
        self.ttl_seconds = ttl_seconds
        self._store: dict[str, tuple[datetime, Any]] = {}

    def get(self, key: str) -> Any | None:
        """Return cached value if it is still valid."""
        entry = self._store.get(key)
        if not entry:
            return None
        expires_at, value = entry
        if datetime.now(UTC) >= expires_at:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        """Store a value with an expiry time."""
        expires_at = datetime.now(UTC) + timedelta(seconds=self.ttl_seconds)
        self._store[key] = (expires_at, value)

    def invalidate(self, key: str | None = None) -> None:
        """Remove a cached entry or clear the cache."""
        if key:
            self._store.pop(key, None)
        else:
            self._store.clear()


__all__ = ["PricingCache"]
