"""Unit tests for SignalCorrelator branch behavior."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from sre_agent.domain.detection.signal_correlator import SignalCorrelator
from sre_agent.domain.models.canonical import (
    CanonicalEvent,
    CanonicalLogEntry,
    CanonicalMetric,
    CanonicalTrace,
    ServiceLabels,
    TraceSpan,
)


def _make_correlator(ebpf_query=None) -> tuple[SignalCorrelator, MagicMock, MagicMock, MagicMock]:
    metrics_query = MagicMock()
    metrics_query.query = AsyncMock(return_value=[])

    trace_query = MagicMock()
    trace_query.query_traces = AsyncMock(return_value=[])
    trace_query.get_trace = AsyncMock(return_value=None)

    log_query = MagicMock()
    log_query.query_logs = AsyncMock(return_value=[])
    log_query.query_by_trace_id = AsyncMock(return_value=[])

    correlator = SignalCorrelator(
        metrics_query=metrics_query,
        trace_query=trace_query,
        log_query=log_query,
        ebpf_query=ebpf_query,
    )
    return correlator, metrics_query, trace_query, log_query


async def test_correlate_by_trace_id_returns_none_when_trace_missing() -> None:
    correlator, _, trace_query, _ = _make_correlator()
    trace_query.get_trace = AsyncMock(return_value=None)

    result = await correlator.correlate_by_trace_id("trace-123")

    assert result is None


async def test_correlate_by_trace_id_returns_none_when_trace_has_no_timestamps() -> None:
    correlator, _, trace_query, _ = _make_correlator()
    trace = CanonicalTrace(
        trace_id="trace-123",
        spans=[
            TraceSpan(
                span_id="span-1",
                parent_span_id=None,
                service="checkout",
                operation="request",
                duration_ms=12.0,
            ),
        ],
    )
    trace_query.get_trace = AsyncMock(return_value=trace)

    result = await correlator.correlate_by_trace_id("trace-123")

    assert result is None


async def test_correlate_by_trace_id_builds_window_and_uses_root_span_service() -> None:
    correlator, _, trace_query, log_query = _make_correlator()
    now = datetime.now(UTC)
    labels = ServiceLabels(service="checkout")
    trace = CanonicalTrace(
        trace_id="trace-123",
        spans=[
            TraceSpan(
                span_id="root",
                parent_span_id=None,
                service="checkout",
                operation="http.request",
                duration_ms=42.0,
                start_time=now,
                end_time=now + timedelta(seconds=1),
            ),
        ],
    )
    trace_query.get_trace = AsyncMock(return_value=trace)
    log_query.query_by_trace_id = AsyncMock(
        return_value=[
            CanonicalLogEntry(
                timestamp=now + timedelta(milliseconds=100),
                message="trace correlated log",
                severity="INFO",
                labels=labels,
            ),
        ],
    )

    result = await correlator.correlate_by_trace_id("trace-123")

    assert result is not None
    assert result.service == "checkout"
    assert len(result.traces) == 1
    assert len(result.logs) == 1
    log_query.query_by_trace_id.assert_awaited_once()


async def test_safe_query_returns_none_when_query_raises() -> None:
    correlator, _, _, _ = _make_correlator()

    async def raise_error(*_args, **_kwargs):
        raise RuntimeError("query failed")

    assert await correlator._safe_query(raise_error) is None


async def test_fetch_ebpf_events_returns_empty_without_adapter() -> None:
    correlator, _, _, _ = _make_correlator(ebpf_query=None)
    now = datetime.now(UTC)

    events = await correlator._fetch_ebpf_events(
        service="checkout",
        namespace="prod",
        start_time=now - timedelta(minutes=5),
        end_time=now,
    )

    assert events == []


async def test_fetch_ebpf_events_merges_syscalls_and_network_flows() -> None:
    now = datetime.now(UTC)
    labels = ServiceLabels(service="checkout")

    syscall_event = CanonicalEvent(
        event_type="syscall",
        source="ebpf",
        timestamp=now,
        metadata={"name": "open"},
        labels=labels,
    )
    flow_event = CanonicalEvent(
        event_type="network_flow",
        source="ebpf",
        timestamp=now + timedelta(seconds=1),
        metadata={"bytes": 128},
        labels=labels,
    )

    ebpf_query = MagicMock()
    ebpf_query.get_syscall_activity = AsyncMock(return_value=[syscall_event])
    ebpf_query.get_network_flows = AsyncMock(return_value=[flow_event])

    correlator, _, _, _ = _make_correlator(ebpf_query=ebpf_query)

    events = await correlator._fetch_ebpf_events(
        service="checkout",
        namespace="prod",
        start_time=now - timedelta(minutes=5),
        end_time=now + timedelta(minutes=1),
    )

    assert events == [syscall_event, flow_event]


async def test_fetch_metrics_extends_results_for_each_metric_name() -> None:
    now = datetime.now(UTC)
    labels = ServiceLabels(service="checkout")
    metric = CanonicalMetric(
        name="http_requests_total",
        value=12.0,
        timestamp=now,
        labels=labels,
    )

    correlator, metrics_query, _, _ = _make_correlator()
    metrics_query.query = AsyncMock(side_effect=[[metric], []])

    result = await correlator._fetch_metrics(
        service="checkout",
        metric_names=["http_requests_total", "latency"],
        start_time=now - timedelta(minutes=5),
        end_time=now,
    )

    assert result == [metric]
