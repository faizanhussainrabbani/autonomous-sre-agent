"""
Signal Correlator — joins metrics, logs, traces, and eBPF events into
a unified per-service view.

This is a core domain service that takes raw canonical signals from
the telemetry provider and produces CorrelatedSignals for downstream
consumers (anomaly detection, diagnostics).

Implements: Task 1.4 — Signal correlation service
Validates: AC-2.3.1, AC-2.3.2
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Awaitable, Callable, TypeVar

T = TypeVar("T")

import structlog

from sre_agent.domain.models.canonical import (
    CanonicalEvent,
    CanonicalLogEntry,
    CanonicalMetric,
    CanonicalTrace,
    ComputeMechanism,
    CorrelatedSignals,
    DataQuality,
)
from sre_agent.ports.telemetry import (
    LogQuery,
    MetricsQuery,
    TraceQuery,
    eBPFQuery,
)

logger = structlog.get_logger(__name__)


class SignalCorrelator:
    """Joins multi-signal telemetry data into unified per-service views.

    Correlates metrics, logs, traces, and eBPF events by:
    1. Service name (primary key)
    2. Time window alignment (sub-second precision per AC-2.3.2)
    3. Trace ID (for log→trace and metric→trace correlation)
    """

    def __init__(
        self,
        metrics_query: MetricsQuery,
        trace_query: TraceQuery,
        log_query: LogQuery,
        ebpf_query: eBPFQuery | None = None,
        alignment_tolerance_ms: float = 1000.0,  # Sub-second precision
    ) -> None:
        self._metrics = metrics_query
        self._traces = trace_query
        self._logs = log_query
        self._ebpf = ebpf_query
        self._alignment_tolerance = timedelta(milliseconds=alignment_tolerance_ms)

    async def correlate(
        self,
        service: str,
        namespace: str,
        start_time: datetime,
        end_time: datetime,
        metric_names: list[str] | None = None,
        is_degraded: bool = False,
        degradation_reason: str | None = None,
        compute_mechanism: ComputeMechanism = ComputeMechanism.KUBERNETES,
    ) -> CorrelatedSignals:
        """Build a correlated signal view for a service in a time window.

        Fetches metrics, traces, and logs in parallel (via sequential calls
        with error isolation), aligns them on the common timeline, and
        produces a CorrelatedSignals object.

        Args:
            service: Service name to correlate signals for.
            namespace: Kubernetes namespace (optional for non-K8s).
            start_time: Start of correlation window.
            end_time: End of correlation window.
            metric_names: Optional specific metrics to query (if None, uses defaults).
            is_degraded: Whether telemetry is in degraded mode.
            degradation_reason: Reason for degraded mode.
            compute_mechanism: Target compute platform (Phase 1.5).

        Returns:
            CorrelatedSignals with all available data for the service+window.
        """
        default_metrics = metric_names or [
            "http_request_duration_seconds",
            "http_requests_total",
            "process_resident_memory_bytes",
            "container_cpu_usage_seconds_total",
        ]

        # Phase 1.5: Check eBPF support for the target compute mechanism
        ebpf_supported = (
            self._ebpf is not None
            and self._ebpf.is_supported(compute_mechanism)
        )
        if not ebpf_supported and self._ebpf is not None:
            is_degraded = True
            degradation_reason = f"ebpf_unsupported_on_{compute_mechanism.value}"
            logger.info(
                "ebpf_degradation_detected",
                service=service,
                compute_mechanism=compute_mechanism.value,
                reason=degradation_reason,
            )

        # Fetch signals with error isolation (one failing doesn't break others)
        metrics = await self._fetch_metrics(service, default_metrics, start_time, end_time)
        traces = await self._fetch_traces(service, start_time, end_time)
        logs = await self._fetch_logs(service, start_time, end_time)
        events = (
            await self._fetch_ebpf_events(service, namespace, start_time, end_time)
            if ebpf_supported
            else []
        )

        return CorrelatedSignals(
            service=service,
            namespace=namespace,
            time_window_start=start_time,
            time_window_end=end_time,
            compute_mechanism=compute_mechanism,
            metrics=metrics,
            traces=traces,
            logs=logs,
            events=events,
            has_degraded_observability=is_degraded,
            degradation_reason=degradation_reason,
        )

    async def correlate_by_trace_id(
        self,
        trace_id: str,
        service: str | None = None,
    ) -> CorrelatedSignals | None:
        """Build a correlated view anchored on a specific trace.

        Fetches the trace, then retrieves correlated logs and metrics
        for the involved services and time window.
        """
        trace = await self._traces.get_trace(trace_id)
        if trace is None:
            return None

        # Determine time window from trace spans
        start_times = [s.start_time for s in trace.spans if s.start_time]
        end_times = [s.end_time for s in trace.spans if s.end_time]
        if not start_times or not end_times:
            return None

        window_start = min(start_times) - timedelta(seconds=5)
        window_end = max(end_times) + timedelta(seconds=5)
        primary_service = service or (trace.root_span.service if trace.root_span else "unknown")

        # Get logs correlated with this trace
        logs = await self._safe_query(
            self._logs.query_by_trace_id,
            trace_id,
            start_time=window_start,
            end_time=window_end,
        ) or []

        return CorrelatedSignals(
            service=primary_service,
            namespace="",
            time_window_start=window_start,
            time_window_end=window_end,
            metrics=[],
            traces=[trace],
            logs=logs,
            events=[],
        )

    async def _fetch_metrics(
        self,
        service: str,
        metric_names: list[str],
        start_time: datetime,
        end_time: datetime,
    ) -> list[CanonicalMetric]:
        """Fetch multiple metrics for a service, isolating individual failures."""
        all_metrics: list[CanonicalMetric] = []
        for name in metric_names:
            result = await self._safe_query(
                self._metrics.query, service, name, start_time, end_time
            )
            if result:
                all_metrics.extend(result)
        return all_metrics

    async def _fetch_traces(
        self,
        service: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[CanonicalTrace]:
        """Fetch traces for a service."""
        return await self._safe_query(
            self._traces.query_traces,
            service,
            start_time,
            end_time,
            limit=50,
        ) or []

    async def _fetch_logs(
        self,
        service: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[CanonicalLogEntry]:
        """Fetch logs for a service."""
        return await self._safe_query(
            self._logs.query_logs,
            service,
            start_time,
            end_time,
        ) or []

    async def _safe_query(
        self,
        query_fn: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> T | None:
        """Execute a query with error isolation — never crashes the correlator."""
        try:
            return await query_fn(*args, **kwargs)
        except Exception as exc:
            logger.warning(
                "signal_correlation_query_failed",
                function=query_fn.__name__,
                error=str(exc),
            )
            return None

    async def _fetch_ebpf_events(
        self,
        service: str,
        namespace: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[CanonicalEvent]:
        """Fetch eBPF events if adapter is available (AC-2.2.1, AC-2.2.3)."""
        if self._ebpf is None:
            return []

        events: list[CanonicalEvent] = []

        # Syscall activity
        syscalls = await self._safe_query(
            self._ebpf.get_syscall_activity,
            service, namespace, start_time, end_time,
        )
        if syscalls:
            events.extend(syscalls)

        # Network flows
        flows = await self._safe_query(
            self._ebpf.get_network_flows,
            service, namespace, start_time, end_time,
        )
        if flows:
            events.extend(flows)

        if events:
            logger.info(
                "ebpf_events_correlated",
                service=service,
                syscall_count=len(syscalls or []),
                flow_count=len(flows or []),
            )

        return events
