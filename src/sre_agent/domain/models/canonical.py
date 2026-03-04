"""
Autonomous SRE Agent — Canonical Data Model

This module defines the provider-independent data types that ALL core domain logic
operates on. No external SDK types (Prometheus, New Relic, etc.) should appear
outside of adapter code.

Aligned with OpenTelemetry Semantic Conventions where applicable.
See: https://opentelemetry.io/docs/specs/semconv/

Implements: Task 13.1 — Define canonical data model
Validates: AC-1.1.1 through AC-1.1.5
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SignalType(Enum):
    """Type of telemetry signal."""
    METRIC = "metric"
    TRACE = "trace"
    LOG = "log"
    EBPF_EVENT = "ebpf_event"


class DataQuality(Enum):
    """Quality classification for telemetry data."""
    HIGH = "high"
    LOW = "low"           # Missing labels, enrichment failed
    INCOMPLETE = "incomplete"  # Partial trace, missing spans
    LATE = "late"         # Arrived >60s after emission


class Severity(Enum):
    """Incident severity levels (Sev 1 = most critical)."""
    SEV1 = 1
    SEV2 = 2
    SEV3 = 3
    SEV4 = 4


class AnomalyType(Enum):
    """Types of anomalies the detection engine can identify."""
    LATENCY_SPIKE = "latency_spike"
    ERROR_RATE_SURGE = "error_rate_surge"
    MEMORY_PRESSURE = "memory_pressure"
    DISK_EXHAUSTION = "disk_exhaustion"
    CERTIFICATE_EXPIRY = "certificate_expiry"
    MULTI_DIMENSIONAL = "multi_dimensional"
    DEPLOYMENT_INDUCED = "deployment_induced"
    INVOCATION_ERROR_SURGE = "invocation_error_surge"  # Phase 1.5: Serverless
    TRAFFIC_ANOMALY = "traffic_anomaly"


class IncidentPhase(Enum):
    """Current phase in the incident saga pipeline."""
    DETECTED = "detected"
    CLASSIFIED = "classified"
    DIAGNOSING = "diagnosing"
    DIAGNOSED = "diagnosed"
    VALIDATING = "validating"
    AUTHORIZING = "authorizing"
    REMEDIATING = "remediating"
    VERIFYING = "verifying"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    FAILED = "failed"


class OperationalPhase(Enum):
    """Agent operational phase (phased rollout)."""
    OBSERVE = "observe"
    ASSIST = "assist"
    AUTONOMOUS = "autonomous"
    PREDICTIVE = "predictive"


class ComputeMechanism(Enum):
    """Target compute platform for a service instance.

    Used to adapt detection heuristics and select the correct
    remediation operator (CloudOperatorPort).
    """
    KUBERNETES = "kubernetes"
    SERVERLESS = "serverless"           # AWS Lambda, Azure Functions
    VIRTUAL_MACHINE = "virtual_machine"  # EC2, Azure VM
    CONTAINER_INSTANCE = "container_instance"  # ECS Fargate, Azure Container Instances


# ---------------------------------------------------------------------------
# Labels — aligned with OTel Semantic Conventions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ServiceLabels:
    """Standard labels for identifying a service/compute instance.

    Naming follows OTel semantic conventions where applicable:
        service.name      → service
        service.namespace → namespace (optional; primarily K8s)
        k8s.pod.name      → pod (optional; K8s only)
        k8s.node.name     → node (optional; K8s only)

    Phase 1.5: compute_mechanism, resource_id, and platform_metadata
    provide compute-agnostic identification for Serverless, VM, and
    Container Instance targets.
    """
    service: str
    namespace: str = ""
    compute_mechanism: ComputeMechanism = ComputeMechanism.KUBERNETES
    resource_id: str = ""  # Universal ID: Pod UID, ECS Task ARN, Lambda ARN, etc.
    pod: str = ""
    node: str = ""
    platform_metadata: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Canonical Metric (AC-1.1.1)
# ---------------------------------------------------------------------------

@dataclass
class CanonicalMetric:
    """Provider-independent metric data point.

    Downstream consumers (anomaly detection, diagnostics, dashboard) use ONLY
    this type — never Prometheus QueryResult, New Relic MetricTimeslice, etc.
    """
    name: str
    value: float
    timestamp: datetime
    labels: ServiceLabels
    unit: str = ""
    quality: DataQuality = DataQuality.HIGH

    # Metadata
    provider_source: str = ""  # "otel", "newrelic", etc. — for audit only
    ingestion_timestamp: datetime | None = None

    @property
    def is_low_quality(self) -> bool:
        return self.quality != DataQuality.HIGH


# ---------------------------------------------------------------------------
# Canonical Trace (AC-1.1.2)
# ---------------------------------------------------------------------------

@dataclass
class TraceSpan:
    """A single span within a distributed trace."""
    span_id: str
    parent_span_id: str | None
    service: str
    operation: str
    duration_ms: float
    status_code: int = 200
    error: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    start_time: datetime | None = None
    end_time: datetime | None = None


@dataclass
class CanonicalTrace:
    """Provider-independent distributed trace.

    Assembled from spans across multiple services. Completeness flag indicates
    whether expected spans are missing (informing diagnostic confidence).
    """
    trace_id: str
    spans: list[TraceSpan] = field(default_factory=list)
    is_complete: bool = True
    missing_services: list[str] = field(default_factory=list)  # Services with expected but absent spans
    quality: DataQuality = DataQuality.HIGH

    # Metadata
    provider_source: str = ""
    ingestion_timestamp: datetime | None = None

    @property
    def root_span(self) -> TraceSpan | None:
        """Return the root span (no parent)."""
        for span in self.spans:
            if span.parent_span_id is None:
                return span
        return None

    @property
    def duration_ms(self) -> float:
        """Total trace duration from root span."""
        root = self.root_span
        return root.duration_ms if root else 0.0

    @property
    def services_involved(self) -> set[str]:
        """All services that have spans in this trace."""
        return {span.service for span in self.spans}


# ---------------------------------------------------------------------------
# Canonical Log Entry (AC-1.1.3)
# ---------------------------------------------------------------------------

@dataclass
class CanonicalLogEntry:
    """Provider-independent log entry with trace correlation."""
    timestamp: datetime
    message: str
    severity: str  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    labels: ServiceLabels
    trace_id: str | None = None
    span_id: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    quality: DataQuality = DataQuality.HIGH

    # Metadata
    provider_source: str = ""
    ingestion_timestamp: datetime | None = None


# ---------------------------------------------------------------------------
# Canonical Event (AC-1.1.4)
# ---------------------------------------------------------------------------

@dataclass
class CanonicalEvent:
    """Provider-independent system event (eBPF, K8s, deployment, etc.)."""
    event_type: str  # "oom_kill", "network_flow", "syscall", "deployment", etc.
    source: str      # "ebpf", "kubernetes", "argocd", etc.
    timestamp: datetime
    metadata: dict[str, Any] = field(default_factory=dict)
    labels: ServiceLabels | None = None
    quality: DataQuality = DataQuality.HIGH

    # Metadata
    provider_source: str = ""
    ingestion_timestamp: datetime | None = None


# ---------------------------------------------------------------------------
# Service Dependency Graph
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ServiceNode:
    """A node in the service dependency graph."""
    service: str
    version: str = ""
    namespace: str = ""
    compute_mechanism: ComputeMechanism = ComputeMechanism.KUBERNETES
    tier: int = 3  # 1 = revenue-critical, 2 = customer-facing, 3 = internal
    is_healthy: bool = True


@dataclass(frozen=True)
class ServiceEdge:
    """A directed edge in the service dependency graph (caller → callee)."""
    source: str  # Caller service name
    target: str  # Callee service name
    protocol: str = "http"  # http, grpc, kafka, etc.
    avg_latency_ms: float = 0.0
    error_rate: float = 0.0


@dataclass
class ServiceGraph:
    """Complete service dependency graph with health information."""
    nodes: dict[str, ServiceNode] = field(default_factory=dict)
    edges: list[ServiceEdge] = field(default_factory=list)
    last_updated: datetime | None = None

    def get_upstream(self, service: str) -> list[str]:
        """Services that call this service (callers)."""
        return [e.source for e in self.edges if e.target == service]

    def get_downstream(self, service: str) -> list[str]:
        """Services this service calls (callees)."""
        return [e.target for e in self.edges if e.source == service]

    def get_transitive_downstream(self, service: str, _visited: set[str] | None = None) -> set[str]:
        """All services reachable from this service (transitive closure)."""
        if _visited is None:
            _visited = set()
        for downstream in self.get_downstream(service):
            if downstream not in _visited:
                _visited.add(downstream)
                self.get_transitive_downstream(downstream, _visited)
        return _visited


# ---------------------------------------------------------------------------
# Correlated Signal View
# ---------------------------------------------------------------------------

@dataclass
class CorrelatedSignals:
    """Unified view of all signals for a service within a time window.

    Produced by the signal correlator (Task 1.4). Used by anomaly detection
    and diagnostics — provides the complete picture for a service.
    """
    service: str
    namespace: str = ""
    time_window_start: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    time_window_end: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    compute_mechanism: ComputeMechanism = ComputeMechanism.KUBERNETES
    metrics: list[CanonicalMetric] = field(default_factory=list)
    traces: list[CanonicalTrace] = field(default_factory=list)
    logs: list[CanonicalLogEntry] = field(default_factory=list)
    events: list[CanonicalEvent] = field(default_factory=list)
    has_degraded_observability: bool = False
    degradation_reason: str | None = None


# ---------------------------------------------------------------------------
# Anomaly Alert
# ---------------------------------------------------------------------------

@dataclass
class AnomalyAlert:
    """An anomaly detected by the detection engine.

    This is the primary output of Phase 1 — a structured alert that downstream
    phases (diagnosis, remediation) consume.
    """
    alert_id: UUID = field(default_factory=uuid4)
    anomaly_type: AnomalyType = AnomalyType.LATENCY_SPIKE
    service: str = ""
    namespace: str = ""
    resource_id: str = ""  # Phase 1.5: Universal compute unit identifier
    compute_mechanism: ComputeMechanism = ComputeMechanism.KUBERNETES
    severity: Severity | None = None  # Assigned in Phase 2 by severity classifier
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Detection details
    metric_name: str = ""
    current_value: float = 0.0
    baseline_value: float = 0.0
    deviation_sigma: float = 0.0
    description: str = ""

    # Correlation
    correlated_incident_id: UUID | None = None  # Set by alert correlation engine
    is_deployment_induced: bool = False
    deployment_details: dict[str, Any] | None = None  # commit SHA, deployer, etc.

    # Context
    correlated_signals: CorrelatedSignals | None = None
    related_alerts: list[UUID] = field(default_factory=list)

    # Stage timing (AC-4.4 — per-stage latency instrumentation)
    detected_at: datetime | None = None
    alert_generated_at: datetime | None = None


# ---------------------------------------------------------------------------
# Domain Events — Event Sourcing (Engineering Standards §1.5)
# ---------------------------------------------------------------------------

@dataclass
class DomainEvent:
    """Base class for all domain events in the event store."""
    event_id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: str = ""
    aggregate_id: UUID | None = None  # Incident ID this event belongs to
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        return bool(self.event_type)


# Pre-defined event types for Phase 1
class EventTypes:
    """Constants for domain event types."""
    ANOMALY_DETECTED = "anomaly.detected"
    ANOMALY_CORRELATED = "anomaly.correlated"
    ALERT_SUPPRESSED = "alert.suppressed"
    OBSERVABILITY_DEGRADED = "observability.degraded"
    PROVIDER_HEALTH_CHANGED = "provider.health_changed"
    DEPENDENCY_GRAPH_UPDATED = "dependency_graph.updated"
    BASELINE_UPDATED = "baseline.updated"
    INCIDENT_CREATED = "incident.created"
