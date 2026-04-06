"""Contract smoke tests for abstract port method stubs.

These tests execute abstract method bodies directly to ensure interface
signatures remain callable and to keep contract modules covered.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sre_agent.domain.models.canonical import ComputeMechanism, DomainEvent
from sre_agent.ports.cloud_operator import CloudOperatorPort
from sre_agent.ports.compressor import CompressorPort
from sre_agent.ports.diagnostics import DiagnosticPort
from sre_agent.ports.embedding import EmbeddingPort
from sre_agent.ports.events import EventBus, EventStore
from sre_agent.ports.llm import LLMReasoningPort
from sre_agent.ports.lock_manager import DistributedLockManagerPort
from sre_agent.ports.remediation import RemediationPort
from sre_agent.ports.reranker import RerankerPort
from sre_agent.ports.telemetry import (
    BaselineQuery,
    DependencyGraphQuery,
    LogQuery,
    MetricsQuery,
    TelemetryProvider,
    TraceQuery,
    eBPFQuery,
)
from sre_agent.ports.vector_store import VectorStorePort


@pytest.mark.asyncio
async def test_port_abstract_stubs_are_callable() -> None:
    now = datetime.now(UTC)
    event = DomainEvent(event_type="test.event")

    # cloud_operator
    assert CloudOperatorPort.provider_name.fget(object()) is None
    assert CloudOperatorPort.supported_mechanisms.fget(object()) is None
    assert await CloudOperatorPort.restart_compute_unit(object(), "resource") is None
    assert await CloudOperatorPort.scale_capacity(object(), "resource", 2) is None
    assert await CloudOperatorPort.health_check(object()) is None

    # compressor
    assert CompressorPort.compress(object(), "text") is None
    assert CompressorPort.compress_batch(object(), ["text"]) is None

    # diagnostics
    assert await DiagnosticPort.diagnose(object(), object()) is None
    assert await DiagnosticPort.health_check(object()) is None

    # embedding
    assert await EmbeddingPort.embed_text(object(), "text") is None
    assert await EmbeddingPort.embed_batch(object(), ["text"]) is None
    assert EmbeddingPort.get_dimensions(object()) is None
    assert await EmbeddingPort.health_check(object()) is None

    # events
    assert await EventBus.publish(object(), event) is None
    assert await EventBus.subscribe(object(), "test.event", lambda _event: None) is None
    assert await EventBus.unsubscribe(object(), "test.event", lambda _event: None) is None
    assert await EventStore.append(object(), event) is None
    assert await EventStore.get_events(object(), "agg-1") is None

    # llm
    assert await LLMReasoningPort.generate_hypothesis(object(), object()) is None
    assert await LLMReasoningPort.validate_hypothesis(object(), object()) is None
    assert LLMReasoningPort.count_tokens(object(), "hello") is None
    assert LLMReasoningPort.get_token_usage(object()) is None
    assert await LLMReasoningPort.health_check(object()) is None

    # lock manager
    assert await DistributedLockManagerPort.acquire_lock(object(), object()) is None
    assert await DistributedLockManagerPort.release_lock(object(), "lock", "agent") is None
    assert await DistributedLockManagerPort.is_lock_valid(object(), "lock", "agent", 1) is None

    # remediation
    assert await RemediationPort.create_plan(object(), object(), object()) is None
    assert await RemediationPort.execute_action(object(), object()) is None
    assert await RemediationPort.verify_outcome(object(), object()) is None
    assert await RemediationPort.rollback_action(object(), object()) is None

    # reranker
    assert RerankerPort.rerank(object(), "query", [], top_k=5) is None

    # telemetry baseline
    assert BaselineQuery.get_baseline(object(), "svc", "metric", now) is None
    assert BaselineQuery.compute_deviation(object(), "svc", "metric", 1.0, now) is None
    assert await BaselineQuery.ingest(object(), "svc", "metric", 1.0, now) is None

    # telemetry metrics
    assert await MetricsQuery.query(object(), "svc", "metric", now, now) is None
    assert await MetricsQuery.query_instant(object(), "svc", "metric", now) is None
    assert await MetricsQuery.list_metrics(object(), "svc") is None

    # telemetry traces
    assert await TraceQuery.get_trace(object(), "trace-id") is None
    assert await TraceQuery.query_traces(object(), "svc", now, now) is None

    # telemetry logs
    assert await LogQuery.query_logs(object(), "svc", now, now) is None
    assert await LogQuery.query_by_trace_id(object(), "trace-id", now, now) is None

    # dependency graph
    assert await DependencyGraphQuery.get_graph(object()) is None
    assert await DependencyGraphQuery.get_service_dependencies(object(), "svc", True) is None
    assert await DependencyGraphQuery.get_service_health(object(), "svc") is None

    # ebpf
    assert await eBPFQuery.get_syscall_activity(object(), "pod", "ns", now, now) is None
    assert await eBPFQuery.get_network_flows(object(), "svc", "ns", now, now) is None
    assert await eBPFQuery.get_process_activity(object(), "pod", "ns", now, now) is None
    assert await eBPFQuery.health_check(object()) is None
    assert await eBPFQuery.get_node_status(object()) is None
    assert eBPFQuery.is_supported(object(), ComputeMechanism.KUBERNETES) is True

    # telemetry provider
    assert TelemetryProvider.name.fget(object()) is None
    assert TelemetryProvider.metrics.fget(object()) is None
    assert TelemetryProvider.traces.fget(object()) is None
    assert TelemetryProvider.logs.fget(object()) is None
    assert TelemetryProvider.dependency_graph.fget(object()) is None
    assert await TelemetryProvider.health_check(object()) is None
    assert await TelemetryProvider.close(object()) is None

    # vector store
    assert await VectorStorePort.store(object(), object()) is None
    assert await VectorStorePort.store_batch(object(), []) is None
    assert await VectorStorePort.search(object(), object()) is None
    assert await VectorStorePort.delete(object(), "doc") is None
    assert await VectorStorePort.delete_stale(object(), now) is None
    assert await VectorStorePort.count(object()) is None
    assert await VectorStorePort.health_check(object()) is None
