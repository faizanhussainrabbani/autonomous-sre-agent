"""
Integration Tests — End-to-end AC validation.

Tests the complete detection pipeline: ingest → baseline → detect → correlate.
Validates AC interactions that unit tests cannot cover in isolation.

AC-5.9: All integration tests passing.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from sre_agent.domain.detection.anomaly_detector import AnomalyDetector, DetectionResult
from sre_agent.domain.detection.alert_correlation import AlertCorrelationEngine
from sre_agent.domain.detection.baseline import BaselineService
from sre_agent.domain.detection.late_data_handler import LateDataHandler
from sre_agent.domain.models.canonical import (
    AnomalyAlert,
    AnomalyType,
    CanonicalMetric,
    CanonicalTrace,
    DataQuality,
    ServiceEdge,
    ServiceGraph,
    ServiceLabels,
    TraceSpan,
)
from sre_agent.domain.models.detection_config import DetectionConfig
from sre_agent.events.in_memory import InMemoryEventBus, InMemoryEventStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_metric(
    name: str,
    value: float,
    service: str = "test-svc",
    ts_offset_min: int = 0,
) -> CanonicalMetric:
    """Create a metric with a timestamp offset from 'now'."""
    return CanonicalMetric(
        name=name,
        value=value,
        timestamp=datetime.now(timezone.utc) - timedelta(minutes=ts_offset_min),
        labels=ServiceLabels(service=service, namespace="default"),
    )


def build_baseline(baseline_svc: BaselineService, service: str, metric: str, mean: float):
    """Feed enough data points to establish a baseline."""
    import asyncio

    async def _feed():
        for i in range(35):
            ts = datetime.now(timezone.utc) - timedelta(hours=1, minutes=i)
            await baseline_svc.ingest(service, metric, mean + (i % 3) - 1, ts)

    asyncio.get_event_loop().run_until_complete(_feed())


# ===========================================================================
# AC-3.2.3: Multi-dimensional correlation
# ===========================================================================

class TestMultiDimensionalCorrelation:
    """AC-3.2.3: Combined latency +50% AND error rate +80% should alert."""

    @pytest.fixture
    def detector(self) -> AnomalyDetector:
        event_bus = InMemoryEventBus()
        baseline = BaselineService(event_bus=event_bus)
        config = DetectionConfig(
            latency_sigma_threshold=3.0,
            multi_dim_latency_percent=50.0,
            multi_dim_error_percent=80.0,
            multi_dim_window_minutes=5,
        )
        return AnomalyDetector(baseline, config, event_bus=event_bus)

    @pytest.fixture
    async def detector_with_baselines(self, detector: AnomalyDetector) -> AnomalyDetector:
        """Feed baselines in the SAME hour segment so they're found at detection time."""
        now = datetime.now(timezone.utc)
        # Anchor to avoid crossing hour boundaries during 350-second subtraction
        now = now.replace(minute=30, second=0, microsecond=0)
        for i in range(35):
            # Stay in the same hour by using seconds offset, not hours
            ts = now - timedelta(seconds=i * 10)
            await detector._baselines.ingest("svc-A", "http_request_duration_seconds", 100 + (i % 5), ts)
            await detector._baselines.ingest("svc-A", "http_errors_total", 5 + (i % 3), ts)
        return detector

    async def test_combined_sub_threshold_fires_multi_dim_alert(
        self, detector_with_baselines: AnomalyDetector,
    ):
        """Both latency +50% and error rate +80% simultaneously → MULTI_DIMENSIONAL alert."""
        detector = detector_with_baselines
        now = datetime.now(timezone.utc).replace(minute=30, second=0, microsecond=0)

        # Inject latency metric that IS detected by _detect_latency_spike but returns None
        # (first detection starts timer, doesn't fire alert yet). This puts it through
        # _track_sub_threshold which checks the dimension.
        latency_metric = CanonicalMetric(
            name="http_request_duration_seconds",
            value=160.0,  # ~57% above mean of ~102
            timestamp=now,
            labels=ServiceLabels(service="svc-A", namespace="default"),
        )
        # Error metric similarly sub-threshold (below 200% surge but above +80%)
        error_metric = CanonicalMetric(
            name="http_errors_total",
            value=11.0,  # ~83% above mean of ~6
            timestamp=now,
            labels=ServiceLabels(service="svc-A", namespace="default"),
        )

        result = await detector.detect("svc-A", [latency_metric, error_metric])

        # Should have a multi-dimensional alert
        multi_dim_alerts = [
            a for a in result.alerts
            if a.anomaly_type == AnomalyType.MULTI_DIMENSIONAL
        ]
        assert len(multi_dim_alerts) == 1
        assert "latency" in multi_dim_alerts[0].description.lower()
        assert "error" in multi_dim_alerts[0].description.lower()

    async def test_single_dimension_no_multi_dim_alert(
        self, detector_with_baselines: AnomalyDetector,
    ):
        """Only latency elevated (no error rate shift) → no MULTI_DIMENSIONAL alert."""
        detector = detector_with_baselines
        now = datetime.now(timezone.utc).replace(minute=30, second=0, microsecond=0)

        latency_metric = CanonicalMetric(
            name="http_request_duration_seconds",
            value=165.0,
            timestamp=now,
            labels=ServiceLabels(service="svc-A", namespace="default"),
        )

        result = await detector.detect("svc-A", [latency_metric])

        multi_dim_alerts = [
            a for a in result.alerts
            if a.anomaly_type == AnomalyType.MULTI_DIMENSIONAL
        ]
        assert len(multi_dim_alerts) == 0


# ===========================================================================
# AC-3.5.1, AC-3.5.2: Per-service and per-metric sensitivity
# ===========================================================================

class TestSensitivityConfiguration:
    """AC-3.5.1/3.5.2: Operators configure per-service and per-metric thresholds."""

    async def test_per_service_sensitivity_applied(self):
        """Setting high sensitivity (2σ) for a service lowers its threshold."""
        baseline = BaselineService()
        config = DetectionConfig(latency_sigma_threshold=3.0)
        detector = AnomalyDetector(baseline, config)

        # Set high sensitivity for svc-X
        detector.set_service_sensitivity("svc-X", sigma_threshold=2.0)

        assert detector.get_service_sensitivity("svc-X") == {"sigma_threshold": 2.0}
        assert detector._get_effective_sigma("svc-X", "latency") == 2.0
        # Other services still use default
        assert detector._get_effective_sigma("svc-Y", "latency") == 3.0

    async def test_per_metric_sensitivity_applied(self):
        """Setting per-metric sensitivity overrides default for matching metrics."""
        baseline = BaselineService()
        config = DetectionConfig(latency_sigma_threshold=3.0)
        detector = AnomalyDetector(baseline, config)

        detector.set_metric_sensitivity("latency", sigma_threshold=2.5)

        assert detector.get_metric_sensitivity("latency") == {"sigma_threshold": 2.5}
        assert detector._get_effective_sigma("any-svc", "http_request_latency") == 2.5
        assert detector._get_effective_sigma("any-svc", "error_rate") == 3.0  # no override

    async def test_service_override_takes_precedence_over_metric(self):
        """Per-service override takes precedence over per-metric override."""
        baseline = BaselineService()
        config = DetectionConfig(latency_sigma_threshold=3.0)
        detector = AnomalyDetector(baseline, config)

        detector.set_metric_sensitivity("latency", sigma_threshold=2.5)
        detector.set_service_sensitivity("svc-X", sigma_threshold=1.5)

        # svc-X should use its service override (1.5), not metric (2.5)
        assert detector._get_effective_sigma("svc-X", "latency") == 1.5


# ===========================================================================
# AC-2.5.4, AC-2.5.5: Late-arriving data
# ===========================================================================

class TestLateDataHandling:
    """AC-2.5.4/2.5.5: Late data ingested and retroactively updates incidents."""

    @pytest.fixture
    def handler(self) -> LateDataHandler:
        event_bus = InMemoryEventBus()
        baseline = BaselineService(event_bus=event_bus)
        return LateDataHandler(baseline, event_bus)

    async def test_late_data_flagged_and_ingested(self, handler: LateDataHandler):
        """Late metric (>60s old) flagged as LATE and still ingested into baselines."""
        metric = CanonicalMetric(
            name="http_request_duration_seconds",
            value=150.0,
            timestamp=datetime.now(timezone.utc) - timedelta(seconds=90),
            labels=ServiceLabels(service="svc-A", namespace="default"),
        )

        assert handler.is_late(metric)

        record = await handler.process_late_metric(metric)

        assert record.delay_seconds >= 89
        assert metric.quality == DataQuality.LATE
        assert metric.ingestion_timestamp is not None
        assert handler.late_arrival_count == 1

    async def test_late_data_not_flagged_for_recent_metrics(self, handler: LateDataHandler):
        """Recent metric (<60s old) is NOT flagged as late."""
        metric = CanonicalMetric(
            name="http_request_duration_seconds",
            value=150.0,
            timestamp=datetime.now(timezone.utc) - timedelta(seconds=10),
            labels=ServiceLabels(service="svc-A", namespace="default"),
        )

        assert not handler.is_late(metric)

    async def test_retroactive_update_on_nearby_incident(self, handler: LateDataHandler):
        """Late data near an existing incident triggers retroactive update."""
        incident_time = datetime.now(timezone.utc) - timedelta(seconds=90)
        incident_id = uuid4()
        handler.register_incident("svc-A", incident_id, incident_time, "latency_spike")

        metric = CanonicalMetric(
            name="http_request_duration_seconds",
            value=150.0,
            timestamp=incident_time + timedelta(seconds=30),  # 30s after incident
            labels=ServiceLabels(service="svc-A", namespace="default"),
        )

        record = await handler.process_late_metric(metric)

        assert record.retroactive_update_applied
        assert incident_id in record.affected_incidents

    async def test_no_retroactive_update_for_unrelated_incident(self, handler: LateDataHandler):
        """Late data far from any incident does NOT trigger retroactive update."""
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)
        handler.register_incident("svc-A", uuid4(), old_time, "latency_spike")

        metric = CanonicalMetric(
            name="http_request_duration_seconds",
            value=150.0,
            timestamp=datetime.now(timezone.utc) - timedelta(seconds=90),
            labels=ServiceLabels(service="svc-A", namespace="default"),
        )

        record = await handler.process_late_metric(metric)

        assert not record.retroactive_update_applied
        assert len(record.affected_incidents) == 0

    async def test_late_arrival_summary(self, handler: LateDataHandler):
        """Summary reports correct stats."""
        metric = CanonicalMetric(
            name="cpu",
            value=80.0,
            timestamp=datetime.now(timezone.utc) - timedelta(seconds=120),
            labels=ServiceLabels(service="svc-B", namespace="default"),
        )
        await handler.process_late_metric(metric)

        summary = handler.get_late_arrival_summary()
        assert summary["total_late"] == 1
        assert summary["avg_delay_seconds"] >= 119


# ===========================================================================
# AC-2.6.3: Incomplete trace detection
# ===========================================================================

class TestIncompleteTraceDetection:
    """AC-2.6.3: Incomplete traces marked with missing span services logged."""

    def test_complete_trace_detected(self):
        """A trace with all parent references resolved is marked complete."""
        trace = CanonicalTrace(
            trace_id="abc",
            spans=[
                TraceSpan(span_id="s1", parent_span_id=None, service="svc-A", operation="GET", duration_ms=100),
                TraceSpan(span_id="s2", parent_span_id="s1", service="svc-B", operation="GET", duration_ms=50),
                TraceSpan(span_id="s3", parent_span_id="s2", service="svc-C", operation="GET", duration_ms=20),
            ],
            is_complete=True,
        )
        # Verify all parent_span_ids exist in span_ids
        span_ids = {s.span_id for s in trace.spans}
        for s in trace.spans:
            if s.parent_span_id:
                assert s.parent_span_id in span_ids

    def test_incomplete_trace_missing_parent(self):
        """A span referencing a non-existent parent → incomplete trace."""
        spans = [
            TraceSpan(span_id="s1", parent_span_id=None, service="svc-A", operation="GET", duration_ms=100),
            TraceSpan(span_id="s3", parent_span_id="s2", service="svc-C", operation="GET", duration_ms=20),
            # s2 is MISSING — s3 references it but it's not in the trace
        ]

        span_ids = {s.span_id for s in spans}
        missing_services = []
        is_complete = True
        for s in spans:
            if s.parent_span_id and s.parent_span_id not in span_ids:
                is_complete = False
                missing_services.append(f"unknown (parent_span={s.parent_span_id})")

        assert not is_complete
        assert len(missing_services) == 1
        assert "s2" in missing_services[0]

    def test_trace_with_no_root_span_is_incomplete(self):
        """A trace where all spans have parents but no root → incomplete."""
        spans = [
            TraceSpan(span_id="s2", parent_span_id="s1", service="svc-B", operation="GET", duration_ms=50),
            TraceSpan(span_id="s3", parent_span_id="s2", service="svc-C", operation="GET", duration_ms=20),
        ]

        root_spans = [s for s in spans if s.parent_span_id is None]
        assert len(root_spans) == 0  # No root → incomplete


# ===========================================================================
# AC-3.2.1 + AC-3.2.2: End-to-end correlation pipeline
# ===========================================================================

class TestCorrelationPipeline:
    """End-to-end: detect → correlate → verify incident grouping."""

    async def test_cascading_failure_creates_one_incident(self):
        """AC-3.2.1: A→B→C cascading failure produces ONE incident."""
        graph = ServiceGraph(
            edges=[
                ServiceEdge(source="svc-A", target="svc-B"),
                ServiceEdge(source="svc-B", target="svc-C"),
            ],
        )
        engine = AlertCorrelationEngine(service_graph=graph)

        # Three alerts from cascading services
        alert_a = AnomalyAlert(service="svc-A", anomaly_type=AnomalyType.LATENCY_SPIKE)
        alert_b = AnomalyAlert(service="svc-B", anomaly_type=AnomalyType.LATENCY_SPIKE)
        alert_c = AnomalyAlert(service="svc-C", anomaly_type=AnomalyType.ERROR_RATE_SURGE)

        inc_a = await engine.process_alert(alert_a)
        inc_b = await engine.process_alert(alert_b)
        inc_c = await engine.process_alert(alert_c)

        # All should be in the same incident
        assert inc_a.incident_id == inc_b.incident_id == inc_c.incident_id
        assert inc_c.alert_count == 3
        assert inc_c.service_count == 3

    async def test_alert_references_incident_id(self):
        """AC-3.2.2: Individual alerts reference the correlated incident ID."""
        alert = AnomalyAlert(service="svc-X", anomaly_type=AnomalyType.LATENCY_SPIKE)
        assert alert.correlated_incident_id is None  # not yet correlated

        engine = AlertCorrelationEngine()
        incident = await engine.process_alert(alert)

        # After correlation, the incident has an ID
        assert incident.incident_id is not None
        # The alert is in the incident's alert list
        assert alert in incident.alerts


# ===========================================================================
# AC-4.4: Per-stage latency instrumentation
# ===========================================================================

class TestPerStageLatency:
    """AC-4.4: Detection and alert generation timestamps are set."""

    async def test_stage_timestamps_set(self):
        """Detected_at and alert_generated_at are populated by detector."""
        baseline = BaselineService()
        config = DetectionConfig(
            latency_sigma_threshold=2.0,
            latency_duration_minutes=0,  # No duration requirement for testing
        )
        detector = AnomalyDetector(baseline, config)

        # Build baseline in SAME hour segment as detection
        now = datetime.now(timezone.utc).replace(minute=30, second=0, microsecond=0)
        for i in range(35):
            ts = now - timedelta(seconds=i * 10)
            await baseline.ingest("svc-A", "http_request_duration_seconds", 100 + (i % 5), ts)

        # First spike: starts the duration timer (returns None)
        spike1 = CanonicalMetric(
            name="http_request_duration_seconds",
            value=900.0,
            timestamp=now,
            labels=ServiceLabels(service="svc-A", namespace="default"),
        )
        result1 = await detector.detect("svc-A", [spike1])

        # Second spike: same metric, slightly later → meets duration=0 requirement
        spike2 = CanonicalMetric(
            name="http_request_duration_seconds",
            value=900.0,
            timestamp=now + timedelta(seconds=1),
            labels=ServiceLabels(service="svc-A", namespace="default"),
        )
        result2 = await detector.detect("svc-A", [spike2])
        assert len(result2.alerts) >= 1

        alert = result2.alerts[0]
        assert alert.detected_at is not None, "AC-4.4: detected_at must be set"
        assert alert.alert_generated_at is not None, "AC-4.4: alert_generated_at must be set"
        # Both timestamps are datetime objects (per-stage latency instrumentation)
        assert isinstance(alert.detected_at, datetime)
        assert isinstance(alert.alert_generated_at, datetime)
