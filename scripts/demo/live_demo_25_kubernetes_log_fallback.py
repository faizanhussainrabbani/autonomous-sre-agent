#!/usr/bin/env python3
"""Live Demo 25 — Kubernetes Log Fallback & Resilient Log Chain (Phase 2.9B)
=============================================================================

Proves Phase 2.9B deliverables:

  P1.3  ``KubernetesLogAdapter`` implements ``LogQuery`` and retrieves pod logs
        directly from the Kubernetes API — no Grafana Loki dependency required.

  2.9B  ``FallbackLogAdapter`` composes a primary (Loki) and fallback (K8s API)
        ``LogQuery``.  When Loki is down the adapter automatically degrades to
        the Kubernetes API, transparently returning ``CanonicalLogEntry`` with
        ``provider_source="kubernetes"``.

This demo does **not** require a real Kubernetes cluster.  It uses mocked
``CoreV1Api`` responses to simulate pod log retrieval, proving the adapter
contract, severity inference, trace-ID filtering, and the decorator fallback.

Architecture exercised::

    ┌────────────────────────────────────────────────┐
    │  FallbackLogAdapter (Decorator)                │
    │                                                │
    │  ┌──────────────┐    ┌───────────────────────┐ │
    │  │ LokiLogAdapter│───▶ Primary: query_logs() │ │
    │  │ (SIMULATED    │    │  raises ConnectionErr │ │
    │  │  UNAVAILABLE) │    └───────────┬───────────┘ │
    │  └──────────────┘                │ fallback     │
    │                                  ▼              │
    │  ┌──────────────┐    ┌───────────────────────┐ │
    │  │ K8sLogAdapter │───▶ Fallback: query_logs()│ │
    │  │ (CoreV1Api)   │    │  returns logs from    │ │
    │  │               │    │  read_pod_log()       │ │
    │  └──────────────┘    └───────────────────────┘ │
    └────────────────────────────────────────────────┘
                           │
                           ▼
                  list[CanonicalLogEntry]
                  provider_source="kubernetes"

Usage::

    # No external dependencies required — fully self-contained
    SKIP_PAUSES=1 python3 scripts/demo/live_demo_25_kubernetes_log_fallback.py
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from _demo_utils import (
    banner,
    env_bool,
    fail,
    field,
    info,
    ok,
    pause_if_interactive,
    phase,
    step,
)

SKIP_PAUSES = env_bool("SKIP_PAUSES", False)


class DemoError(RuntimeError):
    pass


def pause(prompt: str = "Press Enter to continue...") -> None:
    pause_if_interactive(SKIP_PAUSES, prompt)


# ---------------------------------------------------------------------------
# Mock Kubernetes objects
# ---------------------------------------------------------------------------

def _make_mock_pod(name: str, service: str) -> MagicMock:
    """Create a mock V1Pod with metadata."""
    pod = MagicMock()
    pod.metadata = MagicMock()
    pod.metadata.name = name
    pod.metadata.namespace = "prod"
    pod.metadata.labels = {"app": service}
    pod.status = MagicMock()
    pod.status.phase = "Running"
    return pod


def _make_pod_log_text() -> str:
    """Simulate realistic pod log output with mixed severities."""
    return (
        "2026-04-02T10:00:01Z INFO  Starting order-service v2.4.1\n"
        "2026-04-02T10:00:02Z INFO  Connected to PostgreSQL at db.prod.internal:5432\n"
        "2026-04-02T10:00:15Z WARN  Connection pool nearing capacity: 48/50 active\n"
        "2026-04-02T10:00:30Z ERROR Exception in request handler: ConnectionPoolExhausted\n"
        "2026-04-02T10:00:30Z ERROR   at com.app.OrderController.createOrder(OrderController.java:142)\n"
        "2026-04-02T10:00:31Z ERROR trace_id=a1b2c3d4e5f6 span_id=9876 Failed to acquire connection\n"
        "2026-04-02T10:00:45Z WARN  Retry attempt 3/5 for downstream fraud-check service\n"
        "2026-04-02T10:01:00Z ERROR trace_id=a1b2c3d4e5f6 Request timeout after 30s\n"
        "2026-04-02T10:01:01Z INFO  Health check passed (degraded mode)\n"
    )


def _make_mock_core_v1_api(pod_count: int = 3) -> MagicMock:
    """Build a mock CoreV1Api that returns pods and log text."""
    api = MagicMock()

    # list_namespaced_pod returns pod list
    pod_list = MagicMock()
    pod_list.items = [
        _make_mock_pod(f"order-service-{i}", "order-service")
        for i in range(pod_count)
    ]
    api.list_namespaced_pod.return_value = pod_list

    # read_namespaced_pod_log returns text
    api.read_namespaced_pod_log.return_value = _make_pod_log_text()

    # list_namespace for health check
    api.list_namespace.return_value = MagicMock(items=[MagicMock()])

    return api


# ---------------------------------------------------------------------------
# Phase functions
# ---------------------------------------------------------------------------

def phase1_adapter_interface() -> None:
    """Prove KubernetesLogAdapter implements LogQuery."""
    phase(1, "Adapter Interface — LogQuery Port Compliance")

    step("1.1  KubernetesLogAdapter is a subclass of LogQuery")
    from sre_agent.adapters.telemetry.kubernetes.pod_log_adapter import KubernetesLogAdapter
    from sre_agent.ports.telemetry import LogQuery

    assert issubclass(KubernetesLogAdapter, LogQuery)
    ok(f"issubclass(KubernetesLogAdapter, LogQuery) = True")
    field("Port", "ports.telemetry.LogQuery")
    field("Adapter", "adapters.telemetry.kubernetes.pod_log_adapter.KubernetesLogAdapter")

    step("1.2  Adapter exposes all required LogQuery methods")
    required = ["query_logs", "query_by_trace_id", "health_check", "close"]
    for method in required:
        assert hasattr(KubernetesLogAdapter, method), f"Missing method: {method}"
        ok(f"  {method}()")

    info("AC-LF-4.1 ✔  KubernetesLogAdapter implements LogQuery")


async def phase2_query_logs() -> None:
    """Demonstrate pod log retrieval with severity inference."""
    phase(2, "Pod Log Retrieval — query_logs()")

    step("2.1  Create adapter with mocked CoreV1Api (3 pods)")
    from sre_agent.adapters.telemetry.kubernetes.pod_log_adapter import KubernetesLogAdapter

    mock_api = _make_mock_core_v1_api(pod_count=3)
    adapter = KubernetesLogAdapter(core_v1_api=mock_api, namespace="prod")
    ok("KubernetesLogAdapter(namespace='prod') created")

    step("2.2  Query logs for order-service")
    now = datetime.now(timezone.utc)
    results = await adapter.query_logs(
        service="order-service",
        start_time=now - timedelta(hours=1),
        end_time=now,
    )

    from sre_agent.domain.models.canonical import CanonicalLogEntry

    ok(f"Returned {len(results)} CanonicalLogEntry instances")
    assert len(results) > 0, "Expected non-empty results"
    assert all(isinstance(e, CanonicalLogEntry) for e in results)

    step("2.3  Verify provider_source and data quality")
    entry = results[0]
    field("type", type(entry).__name__)
    field("provider_source", entry.provider_source)
    field("quality", entry.quality)
    assert entry.provider_source == "kubernetes"
    ok("provider_source = 'kubernetes'")

    step("2.4  Severity inference from log text")
    severities = {e.severity for e in results}
    field("Detected severities", sorted(severities))
    error_entries = [e for e in results if e.severity == "ERROR"]
    warn_entries = [e for e in results if e.severity == "WARNING"]
    info_entries = [e for e in results if e.severity == "INFO"]
    ok(f"ERROR: {len(error_entries)} entries")
    ok(f"WARNING: {len(warn_entries)} entries")
    ok(f"INFO: {len(info_entries)} entries")
    assert "ERROR" in severities, "Expected ERROR severity from log text containing 'ERROR'"
    assert "WARNING" in severities, "Expected WARNING severity from log text containing 'WARN'"
    assert "INFO" in severities, "Expected INFO severity for lines without keywords"

    step("2.5  Verify 5-pod cap (10 pods available, max 5 queried)")
    mock_api_10 = _make_mock_core_v1_api(pod_count=10)
    adapter_10 = KubernetesLogAdapter(core_v1_api=mock_api_10, namespace="prod")
    await adapter_10.query_logs(
        service="order-service",
        start_time=now - timedelta(hours=1),
        end_time=now,
    )
    call_count = mock_api_10.read_namespaced_pod_log.call_count
    assert call_count <= 5, f"Expected ≤5 pod reads, got {call_count}"
    ok(f"10 pods available, but only {call_count} queried (capped at 5)")

    info("AC-LF-4.2 ✔  query_logs() returns list[CanonicalLogEntry] with provider_source='kubernetes'")


async def phase3_trace_id_filtering() -> None:
    """Demonstrate client-side trace ID correlation."""
    phase(3, "Trace ID Filtering — query_by_trace_id()")

    step("3.1  Query logs by trace ID (format: trace_id=...)")
    from sre_agent.adapters.telemetry.kubernetes.pod_log_adapter import KubernetesLogAdapter

    mock_api = _make_mock_core_v1_api(pod_count=2)
    adapter = KubernetesLogAdapter(core_v1_api=mock_api, namespace="prod")

    results = await adapter.query_by_trace_id(trace_id="a1b2c3d4e5f6")

    ok(f"Returned {len(results)} entries matching trace_id=a1b2c3d4e5f6")
    for entry in results:
        assert "a1b2c3d4e5f6" in entry.message
        field("  matched line", entry.message[:80])

    step("3.2  Non-matching trace ID returns empty")
    empty = await adapter.query_by_trace_id(trace_id="nonexistent-trace")
    assert len(empty) == 0
    ok("Non-matching trace ID returns empty list (correct)")


async def phase4_fallback_decorator() -> None:
    """Demonstrate FallbackLogAdapter composing primary + fallback."""
    phase(4, "Fallback Log Adapter — Decorator Pattern")

    from sre_agent.adapters.telemetry.fallback_log_adapter import FallbackLogAdapter
    from sre_agent.adapters.telemetry.kubernetes.pod_log_adapter import KubernetesLogAdapter
    from sre_agent.domain.models.canonical import CanonicalLogEntry
    from sre_agent.ports.telemetry import LogQuery

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=1)

    step("4.1  FallbackLogAdapter implements LogQuery")
    assert issubclass(FallbackLogAdapter, LogQuery)
    ok("issubclass(FallbackLogAdapter, LogQuery) = True")

    step("4.2  Scenario A: Primary succeeds — fallback NOT called")
    primary_result = [
        CanonicalLogEntry(
            timestamp=now,
            message="Loki log: connection pool error",
            severity="ERROR",
            labels=MagicMock(service="order-service"),
            provider_source="otel",
        ),
    ]
    primary = AsyncMock(spec=LogQuery)
    primary.query_logs = AsyncMock(return_value=primary_result)
    fallback = AsyncMock(spec=LogQuery)
    fallback.query_logs = AsyncMock(return_value=[])

    adapter = FallbackLogAdapter(
        primary=primary, fallback=fallback,
        primary_name="loki", fallback_name="kubernetes_api",
    )
    result = await adapter.query_logs("order-service", start, now)

    assert len(result) == 1
    assert result[0].provider_source == "otel"
    fallback.query_logs.assert_not_called()
    ok("Primary returned data → fallback NOT called")
    field("provider_source", "otel (from primary)")

    step("4.3  Scenario B: Primary raises ConnectionError — fallback activated")
    primary_fail = AsyncMock(spec=LogQuery)
    primary_fail.query_logs = AsyncMock(side_effect=ConnectionError("Loki unreachable"))

    mock_api = _make_mock_core_v1_api(pod_count=2)
    k8s_fallback = KubernetesLogAdapter(core_v1_api=mock_api, namespace="prod")

    adapter_fail = FallbackLogAdapter(
        primary=primary_fail, fallback=k8s_fallback,
        primary_name="loki", fallback_name="kubernetes_api",
    )
    result_fallback = await adapter_fail.query_logs("order-service", start, now)

    assert len(result_fallback) > 0
    assert all(e.provider_source == "kubernetes" for e in result_fallback)
    ok(f"Loki raised ConnectionError → K8s fallback returned {len(result_fallback)} entries")
    field("provider_source", "kubernetes (from fallback)")

    step("4.4  Scenario C: Primary returns empty — fallback activated")
    primary_empty = AsyncMock(spec=LogQuery)
    primary_empty.query_logs = AsyncMock(return_value=[])

    adapter_empty = FallbackLogAdapter(
        primary=primary_empty, fallback=k8s_fallback,
        primary_name="loki", fallback_name="kubernetes_api",
    )
    result_empty_fallback = await adapter_empty.query_logs("order-service", start, now)

    assert len(result_empty_fallback) > 0
    ok(f"Loki returned [] → K8s fallback returned {len(result_empty_fallback)} entries")

    step("4.5  Health check: True if either adapter healthy")
    primary_down = AsyncMock(spec=LogQuery)
    primary_down.health_check = AsyncMock(return_value=False)
    fallback_up = AsyncMock(spec=LogQuery)
    fallback_up.health_check = AsyncMock(return_value=True)

    adapter_health = FallbackLogAdapter(
        primary=primary_down, fallback=fallback_up,
        primary_name="loki", fallback_name="kubernetes_api",
    )
    health = await adapter_health.health_check()
    assert health is True
    ok("Primary down + fallback up → health_check() = True")

    info("Decorator is transparent to domain — SignalCorrelator sees one LogQuery instance.")


async def phase5_graceful_degradation() -> None:
    """Demonstrate graceful degradation when K8s API is unreachable."""
    phase(5, "Graceful Degradation — Error Handling")

    from sre_agent.adapters.telemetry.kubernetes.pod_log_adapter import KubernetesLogAdapter

    step("5.1  Kubernetes API throws exception → returns empty list")
    broken_api = MagicMock()
    broken_api.list_namespaced_pod.side_effect = Exception("API server unreachable")

    adapter = KubernetesLogAdapter(core_v1_api=broken_api, namespace="prod")
    now = datetime.now(timezone.utc)
    result = await adapter.query_logs("order-service", now - timedelta(hours=1), now)

    assert result == []
    ok("query_logs() returned [] on API failure (no exception propagated)")

    step("5.2  Health check returns False on error")
    broken_api.list_namespace.side_effect = Exception("Connection refused")
    health = await adapter.health_check()
    assert health is False
    ok("health_check() returned False (no exception propagated)")

    info("Graceful degradation preserves the diagnosis pipeline even when K8s is down.")
    info("The LLM runs with whatever evidence is available — partial data beats no data.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    try:
        banner("Live Demo 25: Kubernetes Log Fallback & Resilient Log Chain")
        info("Phase 2.9B — P1.3 (KubernetesLogAdapter), FallbackLogAdapter decorator")
        info("No external dependencies required — runs with mocked Kubernetes API")
        pause()

        phase1_adapter_interface()
        pause()

        await phase2_query_logs()
        pause()

        await phase3_trace_id_filtering()
        pause()

        await phase4_fallback_decorator()
        pause()

        await phase5_graceful_degradation()

        banner("Demo 25 Complete — All Phase 2.9B Acceptance Criteria Verified")
        ok("P1.3  KubernetesLogAdapter implements LogQuery port")
        ok("P1.3  Pod log retrieval with severity inference and trace-ID filtering")
        ok("P1.3  5-pod cap enforced to bound latency")
        ok("2.9B  FallbackLogAdapter activates on exception or empty result")
        ok("2.9B  Health check passes if either adapter is healthy")
        ok("2.9B  Graceful degradation — no exceptions propagate to caller")

    except DemoError as exc:
        fail(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
