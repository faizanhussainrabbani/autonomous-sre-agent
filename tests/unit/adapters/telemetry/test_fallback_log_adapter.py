"""
Unit tests for FallbackLogAdapter.

Tests fallback behavior: primary result returned when available,
fallback on exception, fallback on empty result, and health check.

Validates: AC-LF-4.1 (fallback chain behavior)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from sre_agent.adapters.telemetry.fallback_log_adapter import FallbackLogAdapter
from sre_agent.domain.models.canonical import (
    CanonicalLogEntry,
    DataQuality,
    ServiceLabels,
)
from sre_agent.ports.telemetry import LogQuery


def _make_entry(message: str = "test", source: str = "primary") -> CanonicalLogEntry:
    """Create a test CanonicalLogEntry."""
    return CanonicalLogEntry(
        timestamp=datetime.now(timezone.utc),
        message=message,
        severity="ERROR",
        labels=ServiceLabels(service="test-svc"),
        provider_source=source,
        quality=DataQuality.LOW,
    )


def _make_adapter(
    query_logs_result: list[CanonicalLogEntry] | Exception | None = None,
    trace_result: list[CanonicalLogEntry] | Exception | None = None,
    health: bool | Exception = True,
) -> AsyncMock:
    """Create a mock LogQuery adapter."""
    adapter = AsyncMock()

    if isinstance(query_logs_result, Exception):
        adapter.query_logs.side_effect = query_logs_result
    else:
        adapter.query_logs.return_value = query_logs_result or []

    if isinstance(trace_result, Exception):
        adapter.query_by_trace_id.side_effect = trace_result
    else:
        adapter.query_by_trace_id.return_value = trace_result or []

    if isinstance(health, Exception):
        adapter.health_check.side_effect = health
    else:
        adapter.health_check.return_value = health

    return adapter


class TestFallbackQueryLogs:
    """Tests for FallbackLogAdapter.query_logs()."""

    @pytest.mark.asyncio
    async def test_returns_primary_result_when_available(self):
        """Primary adapter result returned when non-empty; fallback not called."""
        primary_entries = [_make_entry("primary log", "loki")]
        primary = _make_adapter(query_logs_result=primary_entries)
        fallback = _make_adapter(query_logs_result=[_make_entry("fallback", "k8s")])

        adapter = FallbackLogAdapter(
            primary=primary,
            fallback=fallback,
            primary_name="loki",
            fallback_name="kubernetes",
        )

        now = datetime.now(timezone.utc)
        result = await adapter.query_logs(
            service="svc",
            start_time=now - timedelta(hours=1),
            end_time=now,
        )

        assert len(result) == 1
        assert result[0].message == "primary log"
        fallback.query_logs.assert_not_called()

    @pytest.mark.asyncio
    async def test_falls_back_on_primary_exception(self):
        """Fallback is called when primary raises an exception."""
        fallback_entries = [_make_entry("fallback log", "kubernetes")]
        primary = _make_adapter(query_logs_result=ConnectionError("Loki unreachable"))
        fallback = _make_adapter(query_logs_result=fallback_entries)

        adapter = FallbackLogAdapter(
            primary=primary,
            fallback=fallback,
            primary_name="loki",
            fallback_name="kubernetes",
        )

        now = datetime.now(timezone.utc)
        result = await adapter.query_logs(
            service="svc",
            start_time=now - timedelta(hours=1),
            end_time=now,
        )

        assert len(result) == 1
        assert result[0].message == "fallback log"
        fallback.query_logs.assert_called_once()

    @pytest.mark.asyncio
    async def test_falls_back_on_primary_empty_result(self):
        """Fallback is called when primary returns empty list."""
        fallback_entries = [_make_entry("fallback log", "kubernetes")]
        primary = _make_adapter(query_logs_result=[])
        fallback = _make_adapter(query_logs_result=fallback_entries)

        adapter = FallbackLogAdapter(
            primary=primary,
            fallback=fallback,
            primary_name="loki",
            fallback_name="kubernetes",
        )

        now = datetime.now(timezone.utc)
        result = await adapter.query_logs(
            service="svc",
            start_time=now - timedelta(hours=1),
            end_time=now,
        )

        assert len(result) == 1
        assert result[0].message == "fallback log"


class TestFallbackHealthCheck:
    """Tests for FallbackLogAdapter.health_check()."""

    @pytest.mark.asyncio
    async def test_health_check_true_if_either_healthy(self):
        """health_check returns True when fallback is healthy but primary is not."""
        primary = _make_adapter(health=False)
        fallback = _make_adapter(health=True)

        adapter = FallbackLogAdapter(
            primary=primary,
            fallback=fallback,
            primary_name="loki",
            fallback_name="kubernetes",
        )

        assert await adapter.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_false_if_both_unhealthy(self):
        """health_check returns False when both adapters are unhealthy."""
        primary = _make_adapter(health=False)
        fallback = _make_adapter(health=False)

        adapter = FallbackLogAdapter(
            primary=primary,
            fallback=fallback,
            primary_name="loki",
            fallback_name="kubernetes",
        )

        assert await adapter.health_check() is False

    @pytest.mark.asyncio
    async def test_health_check_true_if_primary_raises(self):
        """health_check returns True when primary raises but fallback is healthy."""
        primary = _make_adapter(health=Exception("primary down"))
        fallback = _make_adapter(health=True)

        adapter = FallbackLogAdapter(
            primary=primary,
            fallback=fallback,
            primary_name="loki",
            fallback_name="kubernetes",
        )

        assert await adapter.health_check() is True


class TestFallbackQueryByTraceId:
    """Tests for FallbackLogAdapter.query_by_trace_id()."""

    @pytest.mark.asyncio
    async def test_returns_primary_trace_result_when_available(self):
        """Primary trace result returned when non-empty."""
        primary_entries = [_make_entry("primary trace", "loki")]
        primary = _make_adapter(trace_result=primary_entries)
        fallback = _make_adapter(trace_result=[_make_entry("fallback", "k8s")])

        adapter = FallbackLogAdapter(primary=primary, fallback=fallback)

        result = await adapter.query_by_trace_id(trace_id="abc123")

        assert len(result) == 1
        assert result[0].message == "primary trace"
        fallback.query_by_trace_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_falls_back_trace_on_primary_exception(self):
        """Fallback used when primary raises during trace query."""
        fallback_entries = [_make_entry("fallback trace", "kubernetes")]
        primary = _make_adapter(trace_result=ConnectionError("down"))
        fallback = _make_adapter(trace_result=fallback_entries)

        adapter = FallbackLogAdapter(primary=primary, fallback=fallback)

        result = await adapter.query_by_trace_id(trace_id="abc123")

        assert len(result) == 1
        assert result[0].message == "fallback trace"

    @pytest.mark.asyncio
    async def test_falls_back_trace_on_empty_primary(self):
        """Fallback used when primary returns empty trace results."""
        fallback_entries = [_make_entry("fallback trace", "kubernetes")]
        primary = _make_adapter(trace_result=[])
        fallback = _make_adapter(trace_result=fallback_entries)

        adapter = FallbackLogAdapter(primary=primary, fallback=fallback)

        result = await adapter.query_by_trace_id(trace_id="abc123")

        assert len(result) == 1
        assert result[0].message == "fallback trace"


class TestFallbackClose:
    """Tests for FallbackLogAdapter.close()."""

    @pytest.mark.asyncio
    async def test_close_calls_both_adapters(self):
        """close() must attempt to close both primary and fallback."""
        primary = _make_adapter()
        fallback = _make_adapter()

        adapter = FallbackLogAdapter(primary=primary, fallback=fallback)
        await adapter.close()

        primary.close.assert_called_once()
        fallback.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_handles_primary_exception(self):
        """close() must not raise if primary.close() fails."""
        primary = _make_adapter()
        primary.close.side_effect = RuntimeError("close failed")
        fallback = _make_adapter()

        adapter = FallbackLogAdapter(primary=primary, fallback=fallback)
        await adapter.close()  # Should not raise

        fallback.close.assert_called_once()

