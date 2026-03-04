"""
Top-level shared test fixtures for the Autonomous SRE Agent.

Provides reusable fixtures for event bus, event store, canonical models,
and common test utilities used across unit, integration, and e2e tests.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from sre_agent.domain.models.canonical import (
    AnomalyAlert,
    AnomalyType,
    CanonicalMetric,
    CanonicalTrace,
    CanonicalLogEntry,
    DomainEvent,
    EventTypes,
    IncidentPhase,
    ServiceEdge,
    ServiceGraph,
    ServiceLabels,
    ServiceNode,
    Severity,
    TraceSpan,
)
from sre_agent.events.in_memory import InMemoryEventBus, InMemoryEventStore
from sre_agent.config.settings import DetectionConfig


# ---------------------------------------------------------------------------
# Event Infrastructure Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def event_bus() -> InMemoryEventBus:
    """Fresh InMemoryEventBus for each test."""
    return InMemoryEventBus()


@pytest.fixture
def event_store() -> InMemoryEventStore:
    """Fresh InMemoryEventStore for each test."""
    return InMemoryEventStore()


# ---------------------------------------------------------------------------
# Canonical Model Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_labels() -> ServiceLabels:
    """Standard service labels for svc-a."""
    return ServiceLabels(
        service="svc-a",
        namespace="default",
        pod="svc-a-abc123-xyz",
        node="k3d-agent-0",
    )


@pytest.fixture
def sample_metric(sample_labels: ServiceLabels) -> CanonicalMetric:
    """A valid CanonicalMetric for testing."""
    return CanonicalMetric(
        name="http_request_duration_seconds",
        value=0.250,
        timestamp=datetime.now(timezone.utc),
        labels=sample_labels,
        unit="seconds",
        provider_source="prometheus",
    )


@pytest.fixture
def sample_alert(sample_labels: ServiceLabels) -> AnomalyAlert:
    """A valid AnomalyAlert for correlation testing."""
    return AnomalyAlert(
        alert_id=str(uuid4()),
        anomaly_type=AnomalyType.LATENCY_SPIKE,
        service=sample_labels.service,
        namespace=sample_labels.namespace,
        severity=Severity.WARNING,
        message="Latency spike detected: p99 > 3σ for > 2 minutes",
        timestamp=datetime.now(timezone.utc),
        metric_name="http_request_duration_seconds",
        current_value=1.5,
        threshold_value=0.5,
        sigma_deviation=3.2,
    )


@pytest.fixture
def simple_service_graph() -> ServiceGraph:
    """A→B→C linear dependency chain for blast radius testing."""
    nodes = [
        ServiceNode(service="svc-a", namespace="default"),
        ServiceNode(service="svc-b", namespace="default"),
        ServiceNode(service="svc-c", namespace="default"),
    ]
    edges = [
        ServiceEdge(source="svc-a", target="svc-b"),
        ServiceEdge(source="svc-b", target="svc-c"),
    ]
    return ServiceGraph(nodes=nodes, edges=edges)


@pytest.fixture
def detection_config() -> DetectionConfig:
    """Default detection configuration for tests."""
    return DetectionConfig()


@pytest.fixture
def sample_domain_event() -> DomainEvent:
    """A valid DomainEvent for event bus testing."""
    return DomainEvent(
        event_type=EventTypes.ANOMALY_DETECTED,
        timestamp=datetime.now(timezone.utc),
        payload={
            "service": "svc-a",
            "anomaly_type": "latency_spike",
            "severity": "WARNING",
        },
    )
