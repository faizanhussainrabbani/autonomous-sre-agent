"""
Diagnostic Cache — semantic caching of LLM diagnosis results.

Caches by alert fingerprint (service + anomaly_type + metric) to
avoid redundant LLM API calls for recurring incidents.

Phase 2.2: Token Optimization
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field

import structlog

from sre_agent.ports.diagnostics import DiagnosisResult

logger = structlog.get_logger(__name__)


@dataclass
class CacheEntry:
    """A single cache entry with TTL tracking."""

    result: DiagnosisResult
    created_at: float
    ttl_seconds: float
    hit_count: int = 0


class DiagnosticCache:
    """In-memory semantic cache for diagnosis results.

    Caches by alert fingerprint (service + anomaly_type + metric_name).
    Prevents redundant LLM calls for recurring incidents.
    """

    def __init__(self, default_ttl: float = 14400.0) -> None:
        """Initialize the cache.

        Args:
            default_ttl: Default TTL in seconds (4 hours).
        """
        self._cache: dict[str, CacheEntry] = {}
        self._default_ttl = default_ttl

    @staticmethod
    def _fingerprint(service: str, anomaly_type: str, metric: str) -> str:
        """Generate a cache key from alert attributes."""
        raw = f"{service}:{anomaly_type}:{metric}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def get(
        self,
        service: str,
        anomaly_type: str,
        metric: str,
    ) -> DiagnosisResult | None:
        """Look up a cached diagnosis result.

        Returns:
            Cached DiagnosisResult or None if miss/expired.
        """
        key = self._fingerprint(service, anomaly_type, metric)
        entry = self._cache.get(key)

        if entry is None:
            return None

        if time.monotonic() - entry.created_at > entry.ttl_seconds:
            del self._cache[key]
            logger.debug("cache_expired", key=key)
            return None

        entry.hit_count += 1
        logger.info(
            "diagnostic_cache_hit",
            key=key,
            hit_count=entry.hit_count,
            age_seconds=round(time.monotonic() - entry.created_at),
        )
        return entry.result

    def put(
        self,
        service: str,
        anomaly_type: str,
        metric: str,
        result: DiagnosisResult,
        ttl: float | None = None,
    ) -> None:
        """Store a diagnosis result in the cache."""
        key = self._fingerprint(service, anomaly_type, metric)
        self._cache[key] = CacheEntry(
            result=result,
            created_at=time.monotonic(),
            ttl_seconds=ttl or self._default_ttl,
        )
        logger.debug("diagnostic_cache_stored", key=key, ttl=ttl or self._default_ttl)

    def invalidate(self, service: str, anomaly_type: str, metric: str) -> None:
        """Remove a specific entry from the cache."""
        key = self._fingerprint(service, anomaly_type, metric)
        self._cache.pop(key, None)

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()

    @property
    def size(self) -> int:
        """Return the number of entries in the cache."""
        return len(self._cache)
