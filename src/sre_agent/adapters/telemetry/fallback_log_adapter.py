"""
Fallback Log Adapter — resilient log query decorator.

Composes a primary ``LogQuery`` with a fallback ``LogQuery``, transparently
retrying with the fallback when the primary fails or returns empty results.
Follows the Decorator pattern (Nygard's "Release It!") to isolate fallback
logic in an infrastructure concern.

The domain sees only a single ``LogQuery`` instance — adding or removing
fallback sources requires only bootstrap changes, not domain changes.

Implements: Phase 2.9B — FallbackLogAdapter Decorator
Validates: AC-LF-4.1 (fallback chain)
"""

from __future__ import annotations

from datetime import datetime

import structlog

from sre_agent.domain.models.canonical import CanonicalLogEntry
from sre_agent.ports.telemetry import LogQuery

logger = structlog.get_logger(__name__)


class FallbackLogAdapter(LogQuery):
    """LogQuery decorator composing primary + fallback adapters.

    Transparent to the domain — wired at bootstrap only. Logs every
    fallback activation with structured fields for operational visibility.

    Args:
        primary: Primary log query adapter (e.g., LokiLogAdapter).
        fallback: Fallback log query adapter (e.g., KubernetesLogAdapter).
        primary_name: Human-readable name for the primary adapter (for logging).
        fallback_name: Human-readable name for the fallback adapter (for logging).
    """

    def __init__(
        self,
        primary: LogQuery,
        fallback: LogQuery,
        *,
        primary_name: str = "primary",
        fallback_name: str = "fallback",
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._primary_name = primary_name
        self._fallback_name = fallback_name

    async def query_logs(
        self,
        service: str,
        start_time: datetime,
        end_time: datetime,
        severity: str | None = None,
        trace_id: str | None = None,
        search_text: str | None = None,
        limit: int = 1000,
    ) -> list[CanonicalLogEntry]:
        """Query logs from primary; fall back on exception or empty result."""
        try:
            result = await self._primary.query_logs(
                service=service,
                start_time=start_time,
                end_time=end_time,
                severity=severity,
                trace_id=trace_id,
                search_text=search_text,
                limit=limit,
            )
            if result:
                return result
            # Primary returned empty — try fallback
            logger.info(
                "fallback_log_adapter_empty_primary",
                primary=self._primary_name,
                fallback=self._fallback_name,
                service=service,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "fallback_log_adapter_primary_failed",
                primary=self._primary_name,
                fallback=self._fallback_name,
                error=str(exc),
                service=service,
            )

        return await self._fallback.query_logs(
            service=service,
            start_time=start_time,
            end_time=end_time,
            severity=severity,
            trace_id=trace_id,
            search_text=search_text,
            limit=limit,
        )

    async def query_by_trace_id(
        self,
        trace_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[CanonicalLogEntry]:
        """Query by trace ID from primary; fall back on exception or empty."""
        try:
            result = await self._primary.query_by_trace_id(
                trace_id=trace_id,
                start_time=start_time,
                end_time=end_time,
            )
            if result:
                return result
            logger.info(
                "fallback_log_adapter_empty_primary",
                primary=self._primary_name,
                fallback=self._fallback_name,
                method="query_by_trace_id",
                trace_id=trace_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "fallback_log_adapter_primary_failed",
                primary=self._primary_name,
                fallback=self._fallback_name,
                method="query_by_trace_id",
                error=str(exc),
                trace_id=trace_id,
            )

        return await self._fallback.query_by_trace_id(
            trace_id=trace_id,
            start_time=start_time,
            end_time=end_time,
        )

    async def health_check(self) -> bool:
        """Return True if either primary or fallback is healthy."""
        primary_ok = False
        fallback_ok = False

        try:
            primary_ok = await self._primary.health_check()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "fallback_log_adapter_health_check_failed",
                adapter=self._primary_name,
                error=str(exc),
            )

        try:
            fallback_ok = await self._fallback.health_check()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "fallback_log_adapter_health_check_failed",
                adapter=self._fallback_name,
                error=str(exc),
            )

        return primary_ok or fallback_ok

    async def close(self) -> None:
        """Close both adapters."""
        try:
            await self._primary.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "fallback_log_adapter_close_failed",
                adapter=self._primary_name,
                error=str(exc),
            )
        try:
            await self._fallback.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "fallback_log_adapter_close_failed",
                adapter=self._fallback_name,
                error=str(exc),
            )
