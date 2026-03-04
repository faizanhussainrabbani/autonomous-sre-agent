"""
Tests for the anomaly detection engine — baseline, detection, correlation.

Validates: AC-3.1.1 through AC-3.5.2
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from sre_agent.domain.detection.baseline import BaselineService, BaselineWindow
from sre_agent.domain.detection.anomaly_detector import AnomalyDetector
from sre_agent.domain.detection.alert_correlation import AlertCorrelationEngine, CorrelatedIncident
from sre_agent.domain.models.canonical import (
    AnomalyAlert,
    AnomalyType,
    CanonicalMetric,
    ServiceEdge,
    ServiceGraph,
    ServiceLabels,
    ServiceNode,
)
from sre_agent.config.settings import DetectionConfig
from sre_agent.events.in_memory import InMemoryEventBus


# ---------------------------------------------------------------------------
# Baseline Service Tests (Task 2.1, AC-3.1.1)
# ---------------------------------------------------------------------------

class TestBaselineService:

    @pytest.mark.asyncio
    async def test_ingest_creates_baseline(self):
        svc = BaselineService()
        now = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)  # Monday 10:00

        for i in range(30):
            await svc.ingest("api-gw", "latency", 0.1 + (i * 0.001), now)

        baseline = svc.get_baseline("api-gw", "latency", now)
        assert baseline is not None
        assert baseline.is_established
        assert baseline.count == 30
        assert 0.1 <= baseline.mean <= 0.13

    @pytest.mark.asyncio
    async def test_baseline_segments_by_hour_and_day(self):
        svc = BaselineService()
        mon_10am = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        mon_3pm = datetime(2024, 1, 15, 15, 0, tzinfo=timezone.utc)

        await svc.ingest("api-gw", "latency", 0.1, mon_10am)
        await svc.ingest("api-gw", "latency", 0.5, mon_3pm)

        assert svc.baseline_count == 2

    @pytest.mark.asyncio
    async def test_sigma_deviation(self):
        svc = BaselineService()
        now = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)

        # Build baseline: 30 values around 100 with std_dev ~5
        for i in range(30):
            await svc.ingest("api-gw", "latency", 100 + (i % 10) - 5, now)

        sigma, baseline = svc.compute_deviation("api-gw", "latency", 120.0, now)
        assert sigma > 3.0  # 120 is well above mean ~100

    @pytest.mark.asyncio
    async def test_no_deviation_without_established_baseline(self):
        svc = BaselineService()
        now = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)

        # Only 5 points — not enough for established baseline
        for i in range(5):
            await svc.ingest("api-gw", "latency", 0.1, now)

        sigma, baseline = svc.compute_deviation("api-gw", "latency", 999.0, now)
        assert sigma == 0.0  # Not established

    @pytest.mark.asyncio
    async def test_baseline_emits_established_event(self):
        bus = InMemoryEventBus()
        svc = BaselineService(event_bus=bus)
        now = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)

        for i in range(30):
            await svc.ingest("api-gw", "latency", 0.1, now)

        assert len(bus.published_events) == 1
        assert bus.published_events[0].event_type == "baseline.updated"


# ---------------------------------------------------------------------------
# Anomaly Detector Tests (Tasks 2.2+2.4)
# ---------------------------------------------------------------------------

class TestAnomalyDetector:

    def _make_metric(self, name: str, value: float, ts: datetime | None = None) -> CanonicalMetric:
        return CanonicalMetric(
            name=name,
            value=value,
            timestamp=ts or datetime.now(timezone.utc),
            labels=ServiceLabels(service="api-gw", namespace="prod"),
        )

    async def _build_baseline(self, detector: AnomalyDetector, metric_name: str, value: float):
        """Helper: build an established baseline."""
        ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        for i in range(35):
            await detector._baselines.ingest("api-gw", metric_name, value, ts)

    @pytest.mark.asyncio
    async def test_latency_spike_detection(self):
        """AC-3.1.2: p99 > 3σ for >2 minutes → alert."""
        bus = InMemoryEventBus()
        baseline_svc = BaselineService()
        config = DetectionConfig(
            latency_sigma_threshold=3.0,
            latency_duration_minutes=0,  # Disable duration for unit test
        )
        detector = AnomalyDetector(baseline_svc, config, event_bus=bus)

        # Build baseline with variation (values around 0.1 ± 0.01)
        ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        for i in range(35):
            await detector._baselines.ingest(
                "api-gw", "http_request_duration_seconds_p99",
                0.1 + (i % 5) * 0.005, ts
            )

        # First detection within duration window — starts timer
        ts1 = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        metrics = [self._make_metric("http_request_duration_seconds_p99", 100.0, ts1)]
        result = await detector.detect("api-gw", metrics, namespace="prod")

        # With duration=0, first detection starts the timer but no alert yet
        # Second detection should generate alert
        ts2 = ts1 + timedelta(seconds=1)
        metrics = [self._make_metric("http_request_duration_seconds_p99", 100.0, ts2)]
        result = await detector.detect("api-gw", metrics, namespace="prod")

        assert result.checked_count == 1
        assert len(result.alerts) == 1
        assert result.alerts[0].anomaly_type == AnomalyType.LATENCY_SPIKE
        assert result.alerts[0].deviation_sigma > 3.0

    @pytest.mark.asyncio
    async def test_error_rate_surge_detection(self):
        """AC-3.1.3: >200% increase → alert."""
        baseline_svc = BaselineService()
        config = DetectionConfig(error_rate_surge_percent=200.0)
        detector = AnomalyDetector(baseline_svc, config)

        # Build baseline with small variation around 1.0
        ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        for i in range(35):
            await detector._baselines.ingest(
                "api-gw", "error_rate", 1.0 + (i % 3) * 0.1, ts
            )

        metrics = [self._make_metric("error_rate", 4.0, ts)]  # 300% increase
        result = await detector.detect("api-gw", metrics)

        assert len(result.alerts) == 1
        assert result.alerts[0].anomaly_type == AnomalyType.ERROR_RATE_SURGE

    @pytest.mark.asyncio
    async def test_memory_pressure_detection(self):
        """AC-3.1.4: >85% for >5 min."""
        baseline_svc = BaselineService()
        config = DetectionConfig(
            memory_pressure_percent=85.0,
            memory_pressure_duration_minutes=0,  # Disable for unit test
        )
        detector = AnomalyDetector(baseline_svc, config)

        ts1 = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        ts2 = ts1 + timedelta(seconds=1)

        r1 = await detector.detect("api-gw", [self._make_metric("memory_usage", 0.90, ts1)])
        assert len(r1.alerts) == 0  # First detection — starts timer

        r2 = await detector.detect("api-gw", [self._make_metric("memory_usage", 0.92, ts2)])
        assert len(r2.alerts) == 1
        assert r2.alerts[0].anomaly_type == AnomalyType.MEMORY_PRESSURE

    @pytest.mark.asyncio
    async def test_disk_exhaustion_detection(self):
        """AC-3.1.5: >80%."""
        baseline_svc = BaselineService()
        config = DetectionConfig(disk_exhaustion_percent=80.0)
        detector = AnomalyDetector(baseline_svc, config)

        metrics = [self._make_metric("disk_usage", 0.85)]
        result = await detector.detect("api-gw", metrics)

        assert len(result.alerts) == 1
        assert result.alerts[0].anomaly_type == AnomalyType.DISK_EXHAUSTION

    @pytest.mark.asyncio
    async def test_cert_expiry_detection(self):
        """AC-3.1.6: <14 days warning."""
        baseline_svc = BaselineService()
        config = DetectionConfig(cert_expiry_warning_days=14, cert_expiry_critical_days=3)
        detector = AnomalyDetector(baseline_svc, config)

        metrics = [self._make_metric("cert_expiry_days", 10)]
        result = await detector.detect("api-gw", metrics)

        assert len(result.alerts) == 1
        assert result.alerts[0].anomaly_type == AnomalyType.CERTIFICATE_EXPIRY

    @pytest.mark.asyncio
    async def test_deployment_suppression(self):
        """AC-3.4.1: Suppress alerts during deployment window."""
        baseline_svc = BaselineService()
        config = DetectionConfig(
            disk_exhaustion_percent=80.0,
            suppression_window_seconds=30,
        )
        detector = AnomalyDetector(baseline_svc, config)

        deploy_time = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        detector.register_deployment("api-gw", deploy_time)

        # Alert within suppression window should be suppressed
        within = deploy_time + timedelta(seconds=10)
        metrics = [self._make_metric("disk_usage", 0.85, within)]
        result = await detector.detect("api-gw", metrics)

        assert len(result.alerts) == 0
        assert result.suppressed_count == 1

    @pytest.mark.asyncio
    async def test_deployment_correlation(self):
        """AC-3.3.1: Correlate anomaly with recent deployment."""
        baseline_svc = BaselineService()
        config = DetectionConfig(
            disk_exhaustion_percent=80.0,
            suppression_window_seconds=0,  # Disable suppression
            deployment_correlation_window_minutes=60,
        )
        detector = AnomalyDetector(baseline_svc, config)

        deploy_time = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        detector.register_deployment("api-gw", deploy_time, commit_sha="abc123")

        alert_time = deploy_time + timedelta(minutes=30)
        m = CanonicalMetric(
            name="disk_usage",
            value=0.85,
            timestamp=alert_time,
            labels=ServiceLabels(service="api-gw", namespace="prod"),
        )
        result = await detector.detect("api-gw", [m])

        assert len(result.alerts) == 1
        assert result.alerts[0].is_deployment_induced
        assert result.alerts[0].deployment_details["commit_sha"] == "abc123"


# ---------------------------------------------------------------------------
# Alert Correlation Engine Tests (Task 2.3)
# ---------------------------------------------------------------------------

class TestAlertCorrelationEngine:

    def _make_alert(self, service: str, ts: datetime | None = None) -> AnomalyAlert:
        return AnomalyAlert(
            anomaly_type=AnomalyType.LATENCY_SPIKE,
            service=service,
            metric_name="latency",
            current_value=1.0,
            baseline_value=0.1,
            timestamp=ts or datetime.now(timezone.utc),
        )

    def _make_graph(self) -> ServiceGraph:
        """A → B → C."""
        return ServiceGraph(
            nodes={
                "A": ServiceNode(service="A", namespace="ns"),
                "B": ServiceNode(service="B", namespace="ns"),
                "C": ServiceNode(service="C", namespace="ns"),
            },
            edges=[
                ServiceEdge(source="A", target="B"),
                ServiceEdge(source="B", target="C"),
            ],
        )

    @pytest.mark.asyncio
    async def test_new_alert_creates_incident(self):
        engine = AlertCorrelationEngine()
        alert = self._make_alert("api-gw")
        incident = await engine.process_alert(alert)

        assert incident.alert_count == 1
        assert "api-gw" in incident.services_affected
        assert incident.root_service == "api-gw"

    @pytest.mark.asyncio
    async def test_same_service_alerts_correlate(self):
        engine = AlertCorrelationEngine()
        a1 = self._make_alert("api-gw")
        a2 = self._make_alert("api-gw")

        inc1 = await engine.process_alert(a1)
        inc2 = await engine.process_alert(a2)

        assert inc1.incident_id == inc2.incident_id
        assert inc1.alert_count == 2

    @pytest.mark.asyncio
    async def test_related_services_correlate_via_graph(self):
        """AC-3.2.1: Group related anomalies using dependency graph."""
        graph = self._make_graph()
        engine = AlertCorrelationEngine(service_graph=graph)

        now = datetime.now(timezone.utc)
        a1 = self._make_alert("A", now)
        a2 = self._make_alert("B", now + timedelta(seconds=30))

        inc1 = await engine.process_alert(a1)
        inc2 = await engine.process_alert(a2)

        assert inc1.incident_id == inc2.incident_id
        assert inc1.service_count == 2
        assert inc1.is_cascade

    @pytest.mark.asyncio
    async def test_unrelated_services_dont_correlate(self):
        graph = self._make_graph()
        engine = AlertCorrelationEngine(service_graph=graph)

        now = datetime.now(timezone.utc)
        a1 = self._make_alert("A", now)
        a2 = self._make_alert("unrelated-service", now + timedelta(seconds=10))

        inc1 = await engine.process_alert(a1)
        inc2 = await engine.process_alert(a2)

        assert inc1.incident_id != inc2.incident_id

    @pytest.mark.asyncio
    async def test_prevents_alert_storm(self):
        """AC-3.2.2: One incident, not 50 alerts."""
        engine = AlertCorrelationEngine()
        now = datetime.now(timezone.utc)

        # 50 alerts from same service — should all go to one incident
        for i in range(50):
            await engine.process_alert(
                self._make_alert("api-gw", now + timedelta(seconds=i))
            )

        assert len(engine.active_incidents) == 1
        assert engine.active_incidents[0].alert_count == 50


# ---------------------------------------------------------------------------
# Pipeline Monitor Tests (Task 1.6)
# ---------------------------------------------------------------------------

class TestPipelineMonitor:

    @pytest.mark.asyncio
    async def test_heartbeat_tracking(self):
        from sre_agent.domain.detection.pipeline_monitor import PipelineHealthMonitor
        monitor = PipelineHealthMonitor()
        monitor.register_component("otel-collector-node1")

        await monitor.record_heartbeat("otel-collector-node1")
        summary = monitor.get_health_summary()
        assert summary["overall_status"] == "healthy"

    @pytest.mark.asyncio
    async def test_ebpf_failure_triggers_fallback(self):
        """AC-2.5.3: eBPF failure, graceful fallback."""
        from sre_agent.domain.detection.pipeline_monitor import PipelineHealthMonitor, PipelineComponentStatus
        bus = InMemoryEventBus()
        monitor = PipelineHealthMonitor(event_bus=bus)

        await monitor.record_ebpf_failure(
            node="node-1",
            kernel_version="4.14.0",
            error="BPF_PROG_LOAD failed: permission denied",
        )

        assert monitor.components["ebpf-node-1"].fallback_active
        assert "OTel-only" in (monitor.components["ebpf-node-1"].fallback_reason or "")
        assert len(bus.published_events) == 1

    @pytest.mark.asyncio
    async def test_degraded_service_flag(self):
        """AC-2.5.2: Affected services flagged."""
        from sre_agent.domain.detection.pipeline_monitor import PipelineHealthMonitor
        monitor = PipelineHealthMonitor()

        await monitor.flag_degraded_observability("payment-svc", "OTel collector down")
        assert monitor.is_service_degraded("payment-svc")
        assert not monitor.is_service_degraded("api-gw")

    @pytest.mark.asyncio
    async def test_check_heartbeats_degradatation_and_down(self):
        from sre_agent.domain.detection.pipeline_monitor import PipelineHealthMonitor, PipelineComponentStatus
        bus = InMemoryEventBus()
        # Set short timeout for testing
        monitor = PipelineHealthMonitor(event_bus=bus, heartbeat_timeout_seconds=0)
        monitor.register_component("otel-collector-node1")
        
        # Fast forward time inherently because elapsed is > 0s threshold
        failed = await monitor.check_heartbeats()
        assert "otel-collector-node1" in failed
        comp = monitor.components["otel-collector-node1"]
        assert comp.status == PipelineComponentStatus.DEGRADED
        assert comp.consecutive_misses == 1
        
        # Check event was emitted
        assert len(bus.published_events) == 1
        assert bus.published_events[0].event_type == "observability.degraded"

        # Check twice more to transition to DOWN
        await monitor.check_heartbeats()
        await monitor.check_heartbeats()
        
        comp = monitor.components["otel-collector-node1"]
        assert comp.status == PipelineComponentStatus.DOWN
        assert comp.consecutive_misses == 3

    @pytest.mark.asyncio
    async def test_heartbeat_recovers_degraded_services(self):
        from sre_agent.domain.detection.pipeline_monitor import PipelineHealthMonitor, PipelineComponentStatus
        monitor = PipelineHealthMonitor(heartbeat_timeout_seconds=0)
        
        # Manually set to degraded
        monitor.register_component("otel-col-1")
        await monitor.check_heartbeats()
        assert monitor.components["otel-col-1"].status == PipelineComponentStatus.DEGRADED
        
        # Flag a service as degraded due to this component
        await monitor.flag_degraded_observability("order-svc", "otel-col-1 is down")
        assert monitor.is_service_degraded("order-svc")
        
        # Record heartbeat
        await monitor.record_heartbeat("otel-col-1")
        
        # Comp is healthy
        assert monitor.components["otel-col-1"].status == PipelineComponentStatus.HEALTHY
        
        # Service degradation is cleared
        assert not monitor.is_service_degraded("order-svc")


# ---------------------------------------------------------------------------
# Dependency Graph Service Tests (Task 13.6)
# ---------------------------------------------------------------------------

class TestDependencyGraphService:

    @pytest.mark.asyncio
    async def test_refresh_updates_graph(self):
        from sre_agent.domain.detection.dependency_graph import DependencyGraphService
        from sre_agent.adapters.telemetry.otel.provider import OTelDependencyGraphAdapter

        adapter = OTelDependencyGraphAdapter()
        service = DependencyGraphService(dep_graph_query=adapter)

        assert service.is_stale
        await service.refresh()
        assert not service.is_stale

    @pytest.mark.asyncio
    async def test_blast_radius(self):
        from sre_agent.domain.detection.dependency_graph import DependencyGraphService
        from sre_agent.adapters.telemetry.otel.provider import OTelDependencyGraphAdapter

        adapter = OTelDependencyGraphAdapter()
        service = DependencyGraphService(dep_graph_query=adapter)

        # Manually set graph: A → B → C
        service._graph = ServiceGraph(
            nodes={
                "A": ServiceNode(service="A", namespace="ns"),
                "B": ServiceNode(service="B", namespace="ns"),
                "C": ServiceNode(service="C", namespace="ns"),
            },
            edges=[
                ServiceEdge(source="A", target="B"),
                ServiceEdge(source="B", target="C"),
            ],
        )
        service._last_refresh = datetime.now(timezone.utc)

        # Blast radius of C: A→B both depend on it transitively
        radius = await service.get_blast_radius("C")
        assert radius == {"A", "B"}


# ---------------------------------------------------------------------------
# Health Monitor Tests (Task 13.7)
# ---------------------------------------------------------------------------

class TestHealthMonitor:

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_after_threshold(self):
        from sre_agent.config.health_monitor import ProviderHealthMonitor, CircuitState
        bus = InMemoryEventBus()
        monitor = ProviderHealthMonitor(event_bus=bus, failure_threshold=3)
        monitor.register_component("prometheus")

        # 3 failures → circuit opens
        for i in range(3):
            await monitor.record_failure("prometheus", f"connection refused {i}")

        assert monitor.get_circuit_state("prometheus") == CircuitState.OPEN
        assert monitor.is_any_degraded
        assert len(bus.published_events) == 1  # Event on transition

    @pytest.mark.asyncio
    async def test_circuit_breaker_closes_on_success(self):
        from sre_agent.config.health_monitor import ProviderHealthMonitor, CircuitState
        monitor = ProviderHealthMonitor(failure_threshold=3)
        monitor.register_component("prometheus")

        for i in range(3):
            await monitor.record_failure("prometheus")
        assert monitor.get_circuit_state("prometheus") == CircuitState.OPEN

        await monitor.record_success("prometheus")
        assert monitor.get_circuit_state("prometheus") == CircuitState.CLOSED
        assert not monitor.is_any_degraded


# ---------------------------------------------------------------------------
# Plugin Interface Tests (Task 13.8)
# ---------------------------------------------------------------------------

class TestPluginInterface:

    def test_register_and_create_provider(self):
        from sre_agent.config.plugin import ProviderPlugin
        from sre_agent.config.settings import AgentConfig

        ProviderPlugin.clear()

        def dummy_factory(config: AgentConfig):
            class DummyProvider:
                name = "dummy"
            return DummyProvider()

        ProviderPlugin.register("dummy", dummy_factory)
        assert "dummy" in ProviderPlugin.available_providers()

        provider = ProviderPlugin.create_provider("dummy", AgentConfig())
        assert provider.name == "dummy"

        ProviderPlugin.clear()

    def test_create_unregistered_raises(self):
        from sre_agent.config.plugin import ProviderPlugin
        from sre_agent.config.settings import AgentConfig

        ProviderPlugin.clear()
        with pytest.raises(ValueError, match="not registered"):
            ProviderPlugin.create_provider("nonexistent", AgentConfig())
        ProviderPlugin.clear()
