"""Simple in-memory cache with TTL for discovery results."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Generic, TypeVar

_T = TypeVar("_T")


@dataclass
class _CacheEntry(Generic[_T]):
    value: _T
    expires_at: datetime


class DiscoveryCache:
    """Lightweight TTL cache used by discovery services."""

    def __init__(self, default_ttl_seconds: int = 300):
        self.default_ttl_seconds = default_ttl_seconds
        self._lock = Lock()
        self._store: dict[str, _CacheEntry[object]] = {}

    def get(self, key: str) -> _T | None:
        """Return cached value if not expired."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if entry.expires_at <= datetime.now(UTC):
                del self._store[key]
                return None
            return entry.value  # type: ignore[return-value]

    def set(self, key: str, value: _T, ttl_seconds: int | None = None) -> None:
        """Store a value with TTL."""
        ttl = ttl_seconds or self.default_ttl_seconds
        with self._lock:
            self._store[key] = _CacheEntry(
                value=value,
                expires_at=datetime.now(UTC) + timedelta(seconds=ttl),
            )

    def invalidate(self, prefix: str | None = None) -> None:
        """Invalidate entries optionally by prefix."""
        with self._lock:
            if prefix is None:
                self._store.clear()
                return
            for key in list(self._store.keys()):
                if key.startswith(prefix):
                    del self._store[key]


__all__ = ["DiscoveryCache"]
