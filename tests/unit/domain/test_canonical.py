"""
Tests for the canonical data model — Task 13.1.

Validates: AC-1.1.1 through AC-1.1.5
"""

from datetime import datetime, timezone
from uuid import UUID

from sre_agent.domain.models.canonical import (
    AnomalyAlert,
    AnomalyType,
    CanonicalEvent,
    CanonicalLogEntry,
    CanonicalMetric,
    CanonicalTrace,
    CorrelatedSignals,
    DataQuality,
    DomainEvent,
    EventTypes,
    IncidentPhase,
    OperationalPhase,
    ServiceEdge,
    ServiceGraph,
    ServiceLabels,
    ServiceNode,
    Severity,
    SignalType,
    TraceSpan,
)


class TestServiceLabels:
    """AC-1.1.1: Labels aligned with OTel semantic conventions."""

    def test_create_full_labels(self):
        labels = ServiceLabels(
            service="payment-service",
            namespace="production",
            pod="payment-service-abc123",
            node="ip-10-0-1-50",
        )
        assert labels.service == "payment-service"
        assert labels.namespace == "production"
        assert labels.pod == "payment-service-abc123"
        assert labels.node == "ip-10-0-1-50"

    def test_labels_are_frozen(self):
        labels = ServiceLabels(service="svc", namespace="ns")
        try:
            labels.service = "other"  # type: ignore
            assert False, "Should raise FrozenInstanceError"
        except AttributeError:
            pass  # Expected: frozen=True

    def test_extra_labels(self):
        labels = ServiceLabels(
            service="svc",
            namespace="ns",
            extra={"team": "platform", "tier": "1"},
        )
        assert labels.extra["team"] == "platform"


class TestCanonicalMetric:
    """AC-1.1.1: Canonical metric format."""

    def test_create_metric(self):
        now = datetime.now(timezone.utc)
        metric = CanonicalMetric(
            name="http_request_duration_seconds",
            value=0.250,
            timestamp=now,
            labels=ServiceLabels(service="api-gateway", namespace="production"),
            unit="seconds",
        )
        assert metric.name == "http_request_duration_seconds"
        assert metric.value == 0.250
        assert metric.timestamp == now
        assert metric.labels.service == "api-gateway"
        assert metric.unit == "seconds"
        assert metric.quality == DataQuality.HIGH
        assert not metric.is_low_quality

    def test_low_quality_metric(self):
        metric = CanonicalMetric(
            name="test",
            value=1.0,
            timestamp=datetime.now(timezone.utc),
            labels=ServiceLabels(service="unknown", namespace=""),
            quality=DataQuality.LOW,
        )
        assert metric.is_low_quality

    def test_provider_source_for_audit(self):
        metric = CanonicalMetric(
            name="cpu_usage",
            value=0.75,
            timestamp=datetime.now(timezone.utc),
            labels=ServiceLabels(service="svc", namespace="ns"),
            provider_source="otel",
        )
        assert metric.provider_source == "otel"


class TestCanonicalTrace:
    """AC-1.1.2: Canonical trace format."""

    def test_create_trace_with_spans(self):
        root_span = TraceSpan(
            span_id="span-001",
            parent_span_id=None,
            service="api-gateway",
            operation="GET /users",
            duration_ms=150.0,
            status_code=200,
        )
        child_span = TraceSpan(
            span_id="span-002",
            parent_span_id="span-001",
            service="user-service",
            operation="findUser",
            duration_ms=80.0,
        )
        trace = CanonicalTrace(
            trace_id="trace-abc-123",
            spans=[root_span, child_span],
        )
        assert trace.trace_id == "trace-abc-123"
        assert len(trace.spans) == 2
        assert trace.is_complete
        assert trace.root_span == root_span
        assert trace.duration_ms == 150.0
        assert trace.services_involved == {"api-gateway", "user-service"}

    def test_incomplete_trace(self):
        trace = CanonicalTrace(
            trace_id="trace-xyz",
            spans=[TraceSpan(span_id="s1", parent_span_id=None, service="a", operation="op", duration_ms=10)],
            is_complete=False,
            missing_services=["service-b", "service-c"],
            quality=DataQuality.INCOMPLETE,
        )
        assert not trace.is_complete
        assert "service-b" in trace.missing_services
        assert trace.quality == DataQuality.INCOMPLETE

    def test_empty_trace_root_span(self):
        trace = CanonicalTrace(trace_id="empty")
        assert trace.root_span is None
        assert trace.duration_ms == 0.0


class TestCanonicalLogEntry:
    """AC-1.1.3: Canonical log format."""

    def test_create_log_with_trace_correlation(self):
        log = CanonicalLogEntry(
            timestamp=datetime.now(timezone.utc),
            message="Request failed: connection timeout",
            severity="ERROR",
            labels=ServiceLabels(service="payment-service", namespace="prod"),
            trace_id="trace-abc-123",
            span_id="span-001",
        )
        assert log.trace_id == "trace-abc-123"
        assert log.severity == "ERROR"
        assert "timeout" in log.message


class TestCanonicalEvent:
    """AC-1.1.4: Canonical event format."""

    def test_create_ebpf_event(self):
        event = CanonicalEvent(
            event_type="oom_kill",
            source="ebpf",
            timestamp=datetime.now(timezone.utc),
            metadata={"pid": 12345, "comm": "java", "oom_score": 850},
            labels=ServiceLabels(service="heap-heavy", namespace="prod"),
        )
        assert event.event_type == "oom_kill"
        assert event.source == "ebpf"
        assert event.metadata["pid"] == 12345

    def test_create_deployment_event(self):
        event = CanonicalEvent(
            event_type="deployment",
            source="kubernetes",
            timestamp=datetime.now(timezone.utc),
            metadata={
                "commit_sha": "abc123",
                "deployer": "ci-bot",
                "image": "app:v1.2.3",
            },
        )
        assert event.event_type == "deployment"
        assert event.metadata["commit_sha"] == "abc123"


class TestServiceGraph:
    """Service dependency graph operations."""

    def _build_graph(self) -> ServiceGraph:
        """A → B → C, A → D."""
        return ServiceGraph(
            nodes={
                "A": ServiceNode(service="A", namespace="ns"),
                "B": ServiceNode(service="B", namespace="ns"),
                "C": ServiceNode(service="C", namespace="ns"),
                "D": ServiceNode(service="D", namespace="ns"),
            },
            edges=[
                ServiceEdge(source="A", target="B"),
                ServiceEdge(source="B", target="C"),
                ServiceEdge(source="A", target="D"),
            ],
        )

    def test_get_upstream(self):
        graph = self._build_graph()
        assert graph.get_upstream("B") == ["A"]
        assert graph.get_upstream("A") == []

    def test_get_downstream(self):
        graph = self._build_graph()
        assert set(graph.get_downstream("A")) == {"B", "D"}
        assert graph.get_downstream("C") == []

    def test_get_transitive_downstream(self):
        graph = self._build_graph()
        transitive = graph.get_transitive_downstream("A")
        assert transitive == {"B", "C", "D"}

    def test_transitive_from_leaf(self):
        graph = self._build_graph()
        assert graph.get_transitive_downstream("C") == set()


class TestAnomalyAlert:
    """Anomaly alert structure."""

    def test_create_alert(self):
        alert = AnomalyAlert(
            anomaly_type=AnomalyType.LATENCY_SPIKE,
            service="api-gateway",
            namespace="production",
            metric_name="http_request_duration_seconds_p99",
            current_value=2.5,
            baseline_value=0.3,
            deviation_sigma=4.2,
            description="p99 latency is 4.2σ above baseline",
        )
        assert isinstance(alert.alert_id, UUID)
        assert alert.anomaly_type == AnomalyType.LATENCY_SPIKE
        assert alert.severity is None  # Assigned in Phase 2
        assert alert.deviation_sigma == 4.2

    def test_deployment_induced_flag(self):
        alert = AnomalyAlert(
            anomaly_type=AnomalyType.DEPLOYMENT_INDUCED,
            service="svc",
            is_deployment_induced=True,
            deployment_details={"commit_sha": "abc123"},
        )
        assert alert.is_deployment_induced
        assert alert.deployment_details["commit_sha"] == "abc123"


class TestDomainEvent:
    """Event sourcing domain events."""

    def test_create_event(self):
        event = DomainEvent(
            event_type=EventTypes.ANOMALY_DETECTED,
            payload={"service": "api-gateway", "anomaly": "latency_spike"},
        )
        assert isinstance(event.event_id, UUID)
        assert event.event_type == EventTypes.ANOMALY_DETECTED
        assert event.is_valid

    def test_invalid_event(self):
        event = DomainEvent()
        assert not event.is_valid


class TestEnums:
    """Enum completeness and correctness."""

    def test_severity_ordering(self):
        assert Severity.SEV1.value < Severity.SEV4.value

    def test_incident_phases(self):
        assert len(IncidentPhase) == 11

    def test_operational_phases(self):
        phases = [OperationalPhase.OBSERVE, OperationalPhase.ASSIST,
                  OperationalPhase.AUTONOMOUS, OperationalPhase.PREDICTIVE]
        assert len(phases) == 4

    def test_anomaly_types(self):
        assert len(AnomalyType) == 7

    def test_data_quality_values(self):
        assert DataQuality.HIGH.value == "high"
        assert DataQuality.LATE.value == "late"
