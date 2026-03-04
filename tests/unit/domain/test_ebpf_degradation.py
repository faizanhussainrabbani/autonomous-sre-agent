"""
Tests for Phase 1.5 — eBPF graceful degradation.

Validates: AC-1.5.2.1 through AC-1.5.2.5
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from sre_agent.domain.models.canonical import (
    ComputeMechanism,
    CorrelatedSignals,
)
from sre_agent.domain.detection.signal_correlator import SignalCorrelator
from sre_agent.ports.telemetry import eBPFQuery


# ---------------------------------------------------------------------------
# Helpers — minimal mock adapters
# ---------------------------------------------------------------------------

class MockeBPFQuery(eBPFQuery):
    """Concrete eBPFQuery that does nothing; inherits default is_supported()."""

    async def get_syscall_activity(self, pod, namespace, start_time, end_time, syscall_types=None):
        return []

    async def get_network_flows(self, service, namespace, start_time, end_time):
        return []

    async def get_process_activity(self, pod, namespace, start_time, end_time):
        return []

    async def health_check(self):
        return True

    async def get_node_status(self):
        return []


def _make_correlator(ebpf_query=None) -> SignalCorrelator:
    metrics_q = AsyncMock()
    metrics_q.query = AsyncMock(return_value=[])
    trace_q = AsyncMock()
    trace_q.query_traces = AsyncMock(return_value=[])
    log_q = AsyncMock()
    log_q.query_logs = AsyncMock(return_value=[])
    return SignalCorrelator(
        metrics_query=metrics_q,
        trace_query=trace_q,
        log_query=log_q,
        ebpf_query=ebpf_query,
    )


# ---------------------------------------------------------------------------
# eBPFQuery.is_supported() tests
# ---------------------------------------------------------------------------

def test_ebpf_degrades_on_serverless():
    """AC-1.5.2.2: eBPF is NOT supported on SERVERLESS."""
    q = MockeBPFQuery()
    assert q.is_supported(ComputeMechanism.SERVERLESS) is False


def test_ebpf_degrades_on_container_instance():
    """AC-1.5.2.2: eBPF is NOT supported on CONTAINER_INSTANCE (Fargate)."""
    q = MockeBPFQuery()
    assert q.is_supported(ComputeMechanism.CONTAINER_INSTANCE) is False


def test_ebpf_supported_on_kubernetes():
    """AC-1.5.2.3: eBPF IS supported on KUBERNETES."""
    q = MockeBPFQuery()
    assert q.is_supported(ComputeMechanism.KUBERNETES) is True


def test_ebpf_supported_on_virtual_machine():
    """AC-1.5.2.3: eBPF IS supported on VIRTUAL_MACHINE."""
    q = MockeBPFQuery()
    assert q.is_supported(ComputeMechanism.VIRTUAL_MACHINE) is True


# ---------------------------------------------------------------------------
# SignalCorrelator degradation integration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_correlator_degrades_for_serverless():
    """AC-1.5.2.4: SignalCorrelator sets has_degraded_observability for serverless."""
    ebpf = MockeBPFQuery()
    correlator = _make_correlator(ebpf_query=ebpf)
    t0 = datetime.now(timezone.utc) - timedelta(minutes=5)
    t1 = datetime.now(timezone.utc)

    result = await correlator.correlate(
        service="payment-handler",
        namespace="",
        start_time=t0,
        end_time=t1,
        compute_mechanism=ComputeMechanism.SERVERLESS,
    )

    assert result.has_degraded_observability is True
    assert result.degradation_reason == "ebpf_unsupported_on_serverless"
    assert result.events == []  # No eBPF events fetched


@pytest.mark.asyncio
async def test_correlator_normal_for_kubernetes():
    """AC-1.5.2.5: No degradation on Kubernetes with eBPF available."""
    ebpf = MockeBPFQuery()
    correlator = _make_correlator(ebpf_query=ebpf)
    t0 = datetime.now(timezone.utc) - timedelta(minutes=5)
    t1 = datetime.now(timezone.utc)

    result = await correlator.correlate(
        service="checkout",
        namespace="prod",
        start_time=t0,
        end_time=t1,
        compute_mechanism=ComputeMechanism.KUBERNETES,
    )

    assert result.has_degraded_observability is False
    assert result.degradation_reason is None
