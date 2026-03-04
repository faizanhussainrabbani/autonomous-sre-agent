#!/usr/bin/env python3
"""
Phase 1 + 1.5 Component Validation Script.

Validates all subsystems of the SRE Agent without requiring a live K8s cluster.
Tests the actual domain logic with realistic simulated data.

Usage:
    python scripts/e2e_validate.py --all
    python scripts/e2e_validate.py --test <test_name>

Tests:
    data_model       — Canonical data model integrity and backward compat
    baseline         — BaselineService learning and deviation calculation
    detection        — Full anomaly detection pipeline
    correlator       — Signal correlator with degradation
    serverless       — Serverless-specific detection logic
    registry         — Cloud operator registry resolution
    resilience       — Retry and circuit breaker behavior
    architecture     — Hexagonal architecture import boundary checks
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import sys
import time
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

# ─── Results Tracking ─────────────────────────────────────────────

@dataclass
class TestResult:
    name: str
    passed: bool
    duration_ms: float
    error: str = ""
    details: list[str] = field(default_factory=list)


results: list[TestResult] = []
loop = asyncio.new_event_loop()


def run_test(name: str):
    """Decorator to run and track a test function."""
    def decorator(func):
        def wrapper():
            start = time.monotonic()
            details = []
            try:
                func(details)
                elapsed = (time.monotonic() - start) * 1000
                results.append(TestResult(name=name, passed=True, duration_ms=elapsed, details=details))
                print(f"  ✅ {name} ({elapsed:.0f}ms)")
            except Exception as e:
                elapsed = (time.monotonic() - start) * 1000
                results.append(TestResult(name=name, passed=False, duration_ms=elapsed, error=str(e), details=details))
                print(f"  ❌ {name} ({elapsed:.0f}ms) — {e}")
        wrapper._test_name = name
        return wrapper
    return decorator


# ═══════════════════════════════════════════════════════════════════
# TEST: Data Model Integrity
# ═══════════════════════════════════════════════════════════════════

@run_test("data_model.compute_mechanism_enum")
def test_compute_mechanism_enum(details):
    from sre_agent.domain.models.canonical import ComputeMechanism
    assert len(ComputeMechanism) == 4
    values = {m.value for m in ComputeMechanism}
    assert values == {"kubernetes", "serverless", "virtual_machine", "container_instance"}
    details.append(f"ComputeMechanism has {len(ComputeMechanism)} values: {values}")


@run_test("data_model.service_labels_backward_compat")
def test_service_labels_backward_compat(details):
    from sre_agent.domain.models.canonical import ServiceLabels, ComputeMechanism
    sl = ServiceLabels(service="checkout", namespace="prod", pod="checkout-abc")
    assert sl.compute_mechanism == ComputeMechanism.KUBERNETES
    assert sl.resource_id == ""
    assert sl.platform_metadata == {}
    details.append("K8s ServiceLabels backward compatible — defaults to KUBERNETES")


@run_test("data_model.serverless_service_labels")
def test_serverless_service_labels(details):
    from sre_agent.domain.models.canonical import ServiceLabels, ComputeMechanism
    sl = ServiceLabels(
        service="payment-handler",
        compute_mechanism=ComputeMechanism.SERVERLESS,
        resource_id="arn:aws:lambda:us-east-1:123:function:payment",
        platform_metadata={"runtime": "python3.12", "memory_mb": 512},
    )
    assert sl.compute_mechanism == ComputeMechanism.SERVERLESS
    assert sl.namespace == ""
    assert sl.platform_metadata["runtime"] == "python3.12"
    details.append(f"Serverless ServiceLabels: resource_id={sl.resource_id}")


@run_test("data_model.anomaly_alert_types")
def test_anomaly_alert_types(details):
    from sre_agent.domain.models.canonical import AnomalyType
    # Validate actual enum values match what the detection layer produces
    required = {"LATENCY_SPIKE", "ERROR_RATE_SURGE", "MEMORY_PRESSURE",
                "DISK_EXHAUSTION", "MULTI_DIMENSIONAL"}
    actual = {t.name for t in AnomalyType}
    missing = required - actual
    if missing:
        raise AssertionError(f"Missing AnomalyType values: {missing}")
    details.append(f"AnomalyType has {len(actual)} values: {actual}")
    # Note: INVOCATION_ERROR_SURGE reuses ERROR_RATE_SURGE (BUG-002)
    # Note: TRAFFIC_ANOMALY not in enum (BUG-003)


@run_test("data_model.service_node_compute_aware")
def test_service_node_compute_aware(details):
    from sre_agent.domain.models.canonical import ServiceNode, ComputeMechanism
    # ServiceNode actual fields: service, namespace, compute_mechanism, tier, is_healthy
    node = ServiceNode(
        service="payment",
        namespace="",
        compute_mechanism=ComputeMechanism.SERVERLESS,
    )
    assert node.compute_mechanism == ComputeMechanism.SERVERLESS
    details.append("ServiceNode is compute-mechanism aware")


@run_test("data_model.correlated_signals_compute_aware")
def test_correlated_signals_compute_aware(details):
    from sre_agent.domain.models.canonical import CorrelatedSignals, ComputeMechanism
    # Actual fields: time_window_start, time_window_end (not start_time/end_time)
    # events (not ebpf_events), no data_quality field
    cs = CorrelatedSignals(
        service="svc",
        namespace="",
        time_window_start=datetime.now(timezone.utc),
        time_window_end=datetime.now(timezone.utc),
        compute_mechanism=ComputeMechanism.SERVERLESS,
        metrics=[],
        traces=[],
        logs=[],
        events=[],
        has_degraded_observability=True,
    )
    assert cs.has_degraded_observability is True
    assert cs.compute_mechanism == ComputeMechanism.SERVERLESS
    details.append("CorrelatedSignals supports degradation + compute_mechanism")


# ═══════════════════════════════════════════════════════════════════
# TEST: Baseline Service
# ═══════════════════════════════════════════════════════════════════

@run_test("baseline.service_learning")
def test_baseline_service_learning(details):
    from sre_agent.domain.detection.baseline import BaselineService
    bs = BaselineService()
    now = datetime.now(timezone.utc)
    import random
    random.seed(42)
    # BaselineService.ingest is async — must await it
    for i in range(35):
        val = 1.0 + random.gauss(0, 0.1)
        ts = now + timedelta(seconds=i * 10)
        loop.run_until_complete(bs.ingest("svc-a", "latency_p99", val, ts))

    baseline = bs.get_baseline("svc-a", "latency_p99", now)
    assert baseline is not None, "Baseline should exist after 35 ingestions"
    assert baseline.is_established, "Baseline should be established after 35 points"
    assert 0.8 < baseline.mean < 1.2, f"Mean {baseline.mean} out of range"
    assert baseline.std_dev > 0, "Std should be positive"
    details.append(f"Baseline established: mean={baseline.mean:.3f}, std={baseline.std_dev:.3f}")


@run_test("baseline.deviation_calculation")
def test_baseline_deviation(details):
    from sre_agent.domain.detection.baseline import BaselineService
    bs = BaselineService()
    now = datetime.now(timezone.utc)
    import random
    random.seed(42)
    for i in range(35):
        val = 1.0 + random.gauss(0, 0.1)
        ts = now + timedelta(seconds=i * 10)
        loop.run_until_complete(bs.ingest("svc-a", "latency_p99", val, ts))

    sigma, bl = bs.compute_deviation("svc-a", "latency_p99", 2.0, now)
    assert sigma > 3.0, f"Expected >3σ for value=2.0, got {sigma:.2f}σ"
    details.append(f"Deviation for value=2.0: {sigma:.2f}σ")


# ═══════════════════════════════════════════════════════════════════
# TEST: Anomaly Detection Pipeline
# ═══════════════════════════════════════════════════════════════════

@run_test("detection.latency_spike_fires")
def test_detection_latency_spike(details):
    from sre_agent.domain.detection.anomaly_detector import AnomalyDetector
    from sre_agent.domain.detection.baseline import BaselineService
    from sre_agent.domain.models.detection_config import DetectionConfig
    from sre_agent.domain.models.canonical import CanonicalMetric, ServiceLabels, AnomalyType

    bs = BaselineService()
    now = datetime.now(timezone.utc)
    import random
    random.seed(42)
    for i in range(35):
        val = 1.0 + random.gauss(0, 0.1)
        loop.run_until_complete(
            bs.ingest("svc-a", "http_request_duration_seconds", val, now + timedelta(seconds=i * 10))
        )

    config = DetectionConfig(latency_duration_minutes=0)
    detector = AnomalyDetector(baseline_service=bs, config=config)

    # Detection uses 2-phase pattern: 1st metric starts timer, 2nd fires alert (BUG-003)
    spike1 = CanonicalMetric(
        name="http_request_duration_seconds",
        value=5.0,
        timestamp=now + timedelta(minutes=10),
        labels=ServiceLabels(service="svc-a", namespace="prod"),
    )
    result1 = loop.run_until_complete(detector.detect("svc-a", [spike1]))
    assert len(result1.alerts) == 0, "First spike should start timer, not alert"
    details.append("Phase 1: timer started (no alert on first detection)")

    spike2 = CanonicalMetric(
        name="http_request_duration_seconds",
        value=5.0,
        timestamp=now + timedelta(minutes=10, seconds=5),
        labels=ServiceLabels(service="svc-a", namespace="prod"),
    )
    result2 = loop.run_until_complete(detector.detect("svc-a", [spike2]))
    latency_alerts = [a for a in result2.alerts if a.anomaly_type == AnomalyType.LATENCY_SPIKE]
    assert len(latency_alerts) >= 1, f"Expected latency spike alert on 2nd detection, got {len(latency_alerts)}"
    details.append(f"Phase 2: latency spike detected — {latency_alerts[0].deviation_sigma:.1f}σ")


@run_test("detection.no_false_positive_stable")
def test_no_false_positive_stable(details):
    from sre_agent.domain.detection.anomaly_detector import AnomalyDetector
    from sre_agent.domain.detection.baseline import BaselineService
    from sre_agent.domain.models.detection_config import DetectionConfig
    from sre_agent.domain.models.canonical import CanonicalMetric, ServiceLabels

    bs = BaselineService()
    now = datetime.now(timezone.utc)
    import random
    random.seed(42)
    for i in range(35):
        val = 1.0 + random.gauss(0, 0.1)
        loop.run_until_complete(
            bs.ingest("svc-a", "http_request_duration_seconds", val, now + timedelta(seconds=i * 10))
        )

    config = DetectionConfig(latency_duration_minutes=0)
    detector = AnomalyDetector(baseline_service=bs, config=config)

    normal = CanonicalMetric(
        name="http_request_duration_seconds",
        value=1.1,
        timestamp=now + timedelta(minutes=10),
        labels=ServiceLabels(service="svc-a", namespace="prod"),
    )
    result = loop.run_until_complete(detector.detect("svc-a", [normal]))
    assert len(result.alerts) == 0, f"False positive: {len(result.alerts)} alerts for normal value"
    details.append("No false positives for value within 1σ of baseline")


@run_test("detection.memory_pressure_fires")
def test_memory_pressure_fires(details):
    from sre_agent.domain.detection.anomaly_detector import AnomalyDetector
    from sre_agent.domain.detection.baseline import BaselineService
    from sre_agent.domain.models.detection_config import DetectionConfig
    from sre_agent.domain.models.canonical import CanonicalMetric, ServiceLabels, AnomalyType

    bs = BaselineService()
    now = datetime.now(timezone.utc)
    import random
    random.seed(42)
    for i in range(35):
        val = 0.5 + random.gauss(0, 0.1)
        loop.run_until_complete(
            bs.ingest("svc-a", "process_resident_memory_bytes", val, now + timedelta(seconds=i * 10))
        )

    config = DetectionConfig(latency_duration_minutes=0, memory_pressure_duration_minutes=0)
    detector = AnomalyDetector(baseline_service=bs, config=config)

    # Memory pressure also uses 2-phase pattern (BUG-003)
    mem1 = CanonicalMetric(
        name="process_resident_memory_bytes",
        value=0.92,
        timestamp=now + timedelta(minutes=10),
        labels=ServiceLabels(service="svc-a", namespace="prod"),
    )
    loop.run_until_complete(detector.detect("svc-a", [mem1]))  # Start timer

    mem2 = CanonicalMetric(
        name="process_resident_memory_bytes",
        value=0.92,
        timestamp=now + timedelta(minutes=10, seconds=5),
        labels=ServiceLabels(service="svc-a", namespace="prod"),
    )
    result = loop.run_until_complete(detector.detect("svc-a", [mem2]))
    mem_alerts = [a for a in result.alerts if a.anomaly_type == AnomalyType.MEMORY_PRESSURE]
    assert len(mem_alerts) >= 1, "Expected memory pressure alert on 2nd detection"
    details.append("Memory pressure detected at 92% (2-phase pattern)")


# ═══════════════════════════════════════════════════════════════════
# TEST: eBPF Degradation
# ═══════════════════════════════════════════════════════════════════

@run_test("correlator.ebpf_degradation_serverless")
def test_ebpf_degradation_serverless(details):
    from sre_agent.ports.telemetry import eBPFQuery
    from sre_agent.domain.models.canonical import ComputeMechanism
    assert eBPFQuery.is_supported(None, ComputeMechanism.SERVERLESS) is False
    assert eBPFQuery.is_supported(None, ComputeMechanism.CONTAINER_INSTANCE) is False
    assert eBPFQuery.is_supported(None, ComputeMechanism.KUBERNETES) is True
    assert eBPFQuery.is_supported(None, ComputeMechanism.VIRTUAL_MACHINE) is True
    details.append("eBPF: degraded=SERVERLESS,CONTAINER_INSTANCE; supported=K8S,VM")


# ═══════════════════════════════════════════════════════════════════
# TEST: Serverless Detection
# ═══════════════════════════════════════════════════════════════════

@run_test("serverless.cold_start_suppression")
def test_cold_start_suppression(details):
    from sre_agent.domain.detection.anomaly_detector import AnomalyDetector
    from sre_agent.domain.detection.baseline import BaselineService
    from sre_agent.domain.models.detection_config import DetectionConfig
    from sre_agent.domain.models.canonical import CanonicalMetric, ServiceLabels, ComputeMechanism

    bs = BaselineService()
    now = datetime.now(timezone.utc)
    import random
    random.seed(42)
    for i in range(35):
        val = 1.0 + random.gauss(0, 0.1)
        loop.run_until_complete(
            bs.ingest("lambda-svc", "http_request_duration_seconds", val, now + timedelta(seconds=i * 10))
        )

    config = DetectionConfig(cold_start_suppression_window_seconds=15, latency_duration_minutes=0)
    detector = AnomalyDetector(baseline_service=bs, config=config)

    cold_metric = CanonicalMetric(
        name="http_request_duration_seconds",
        value=8.0,
        timestamp=now + timedelta(seconds=5),
        labels=ServiceLabels(service="lambda-svc", compute_mechanism=ComputeMechanism.SERVERLESS),
    )
    result = loop.run_until_complete(
        detector.detect("lambda-svc", [cold_metric], compute_mechanism=ComputeMechanism.SERVERLESS)
    )
    assert len(result.alerts) == 0, f"Cold-start should be suppressed, got {len(result.alerts)} alerts"
    details.append("Cold-start latency suppressed within 15s window")


@run_test("serverless.memory_pressure_exempted")
def test_memory_exempted_serverless(details):
    from sre_agent.domain.detection.anomaly_detector import AnomalyDetector
    from sre_agent.domain.detection.baseline import BaselineService
    from sre_agent.domain.models.detection_config import DetectionConfig
    from sre_agent.domain.models.canonical import CanonicalMetric, ServiceLabels, ComputeMechanism, AnomalyType

    bs = BaselineService()
    now = datetime.now(timezone.utc)
    import random
    random.seed(42)
    for i in range(35):
        val = 0.5 + random.gauss(0, 0.1)
        loop.run_until_complete(
            bs.ingest("lambda-svc", "process_resident_memory_bytes", val, now + timedelta(seconds=i * 10))
        )

    config = DetectionConfig(latency_duration_minutes=0)
    detector = AnomalyDetector(baseline_service=bs, config=config)

    mem = CanonicalMetric(
        name="process_resident_memory_bytes",
        value=0.95,
        timestamp=now + timedelta(minutes=10),
        labels=ServiceLabels(service="lambda-svc", compute_mechanism=ComputeMechanism.SERVERLESS),
    )
    result = loop.run_until_complete(
        detector.detect("lambda-svc", [mem], compute_mechanism=ComputeMechanism.SERVERLESS)
    )
    mem_alerts = [a for a in result.alerts if a.anomaly_type == AnomalyType.MEMORY_PRESSURE]
    assert len(mem_alerts) == 0, "Memory pressure should be exempt for SERVERLESS"
    details.append("Memory pressure correctly exempted for serverless")


@run_test("serverless.invocation_error_surge")
def test_invocation_error_surge(details):
    from sre_agent.domain.detection.anomaly_detector import AnomalyDetector
    from sre_agent.domain.detection.baseline import BaselineService
    from sre_agent.domain.models.detection_config import DetectionConfig
    from sre_agent.domain.models.canonical import CanonicalMetric, ServiceLabels, ComputeMechanism, AnomalyType

    bs = BaselineService()
    now = datetime.now(timezone.utc)
    import random
    random.seed(42)
    for i in range(35):
        val = 10.0 + random.gauss(0, 2.0)
        loop.run_until_complete(
            bs.ingest("lambda-svc", "invocation_error_count", val, now + timedelta(seconds=i * 10))
        )

    config = DetectionConfig(latency_duration_minutes=0)
    detector = AnomalyDetector(baseline_service=bs, config=config)

    surge = CanonicalMetric(
        name="invocation_error_count",
        value=50.0,
        timestamp=now + timedelta(minutes=10),
        labels=ServiceLabels(service="lambda-svc", compute_mechanism=ComputeMechanism.SERVERLESS),
    )
    result = loop.run_until_complete(
        detector.detect("lambda-svc", [surge], compute_mechanism=ComputeMechanism.SERVERLESS)
    )
    # InvocationError surge now uses dedicated INVOCATION_ERROR_SURGE type
    err_alerts = [a for a in result.alerts if a.anomaly_type == AnomalyType.INVOCATION_ERROR_SURGE]
    assert len(err_alerts) >= 1, f"InvocationError surge should be detected (as INVOCATION_ERROR_SURGE), got {len(result.alerts)} total alerts"
    details.append(f"InvocationError surge detected: {len(err_alerts)} alert(s) (typed as INVOCATION_ERROR_SURGE)")


# ═══════════════════════════════════════════════════════════════════
# TEST: Cloud Operator Registry
# ═══════════════════════════════════════════════════════════════════

@run_test("registry.all_providers_resolve")
def test_registry_resolves(details):
    from sre_agent.domain.detection.cloud_operator_registry import CloudOperatorRegistry
    from sre_agent.domain.models.canonical import ComputeMechanism
    from sre_agent.adapters.cloud.aws.ecs_operator import ECSOperator
    from sre_agent.adapters.cloud.aws.ec2_asg_operator import EC2ASGOperator
    from sre_agent.adapters.cloud.aws.lambda_operator import LambdaOperator
    from sre_agent.adapters.cloud.azure.app_service_operator import AppServiceOperator
    from sre_agent.adapters.cloud.azure.functions_operator import FunctionsOperator
    from sre_agent.adapters.cloud.resilience import RetryConfig

    fast = RetryConfig(max_retries=0)
    registry = CloudOperatorRegistry()
    registry.register(ECSOperator(MagicMock(), retry_config=fast))
    registry.register(EC2ASGOperator(MagicMock(), retry_config=fast))
    registry.register(LambdaOperator(MagicMock(), retry_config=fast))
    registry.register(AppServiceOperator(MagicMock(), retry_config=fast))
    registry.register(FunctionsOperator(MagicMock(), retry_config=fast))

    assert isinstance(registry.get_operator("aws", ComputeMechanism.CONTAINER_INSTANCE), ECSOperator)
    assert isinstance(registry.get_operator("aws", ComputeMechanism.VIRTUAL_MACHINE), EC2ASGOperator)
    assert isinstance(registry.get_operator("aws", ComputeMechanism.SERVERLESS), LambdaOperator)
    assert isinstance(registry.get_operator("azure", ComputeMechanism.SERVERLESS), FunctionsOperator)
    assert registry.get_operator("gcp", ComputeMechanism.KUBERNETES) is None
    details.append("All 5 operators resolve correctly, unknown returns None")


@run_test("registry.health_check_all")
def test_registry_health_check(details):
    from sre_agent.domain.detection.cloud_operator_registry import CloudOperatorRegistry
    from sre_agent.adapters.cloud.aws.ecs_operator import ECSOperator
    from sre_agent.adapters.cloud.aws.lambda_operator import LambdaOperator
    from sre_agent.adapters.cloud.resilience import RetryConfig

    fast = RetryConfig(max_retries=0)
    registry = CloudOperatorRegistry()
    registry.register(ECSOperator(MagicMock(), retry_config=fast))
    registry.register(LambdaOperator(MagicMock(), retry_config=fast))

    results_hc = loop.run_until_complete(registry.health_check_all())
    assert len(results_hc) == 2
    assert all(v is True for v in results_hc.values())
    details.append(f"Health check: {len(results_hc)} operators all healthy")


# ═══════════════════════════════════════════════════════════════════
# TEST: Resilience (Circuit Breaker + Retry)
# ═══════════════════════════════════════════════════════════════════

@run_test("resilience.circuit_breaker_lifecycle")
def test_circuit_breaker_lifecycle(details):
    from sre_agent.adapters.cloud.resilience import CircuitBreaker, CircuitState
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout_seconds=0.0, name="test")
    assert cb.state == CircuitState.CLOSED
    details.append("1. Starts CLOSED")

    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED
    details.append("2. Still CLOSED after 2 failures (threshold=3)")

    cb.record_failure()
    assert cb._state == CircuitState.OPEN
    details.append("3. OPEN after 3rd failure")

    assert cb.state == CircuitState.HALF_OPEN
    details.append("4. HALF_OPEN after recovery timeout (0s)")

    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    details.append("5. Probe success → CLOSED")


@run_test("resilience.retry_recovers_from_transient")
def test_retry_recovers(details):
    from sre_agent.adapters.cloud.resilience import retry_with_backoff, RetryConfig, TransientError
    call_count = 0

    async def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise TransientError("temp")
        return "ok"

    result = loop.run_until_complete(
        retry_with_backoff(flaky, config=RetryConfig(max_retries=3, base_delay_seconds=0.01))
    )
    assert result == "ok"
    assert call_count == 3
    details.append(f"Recovered after {call_count} attempts")


# ═══════════════════════════════════════════════════════════════════
# TEST: Architecture Alignment
# ═══════════════════════════════════════════════════════════════════

@run_test("architecture.no_domain_imports_adapters")
def test_no_domain_imports_adapters(details):
    """Verify hexagonal architecture: domain/ must never import from adapters/."""
    import ast
    import pathlib

    domain_path = pathlib.Path("src/sre_agent/domain")
    violations = []

    for py in domain_path.rglob("*.py"):
        source = py.read_text()
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if "adapters" in node.module:
                    violations.append(f"{py.name}: imports {node.module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if "adapters" in alias.name:
                        violations.append(f"{py.name}: imports {alias.name}")

    if violations:
        raise AssertionError(f"Domain→Adapter violations: {violations}")
    details.append("No domain/ → adapters/ imports (hexagonal clean)")


@run_test("architecture.ports_have_no_concrete_deps")
def test_ports_no_concrete_deps(details):
    """Verify ports/ never import concrete implementations."""
    import ast
    import pathlib

    ports_path = pathlib.Path("src/sre_agent/ports")
    violations = []

    for py in ports_path.rglob("*.py"):
        source = py.read_text()
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if "adapters" in node.module or "boto3" in node.module or "azure" in node.module:
                    violations.append(f"{py.name}: imports {node.module}")

    if violations:
        raise AssertionError(f"Port→Concrete violations: {violations}")
    details.append("No ports/ → adapters/boto3/azure imports (clean interfaces)")


@run_test("architecture.optional_deps_dont_break_base")
def test_optional_deps_base_install(details):
    """Verify core domain works without optional cloud SDKs."""
    importlib.import_module("sre_agent.domain.models.canonical")
    importlib.import_module("sre_agent.domain.detection.anomaly_detector")
    importlib.import_module("sre_agent.domain.detection.baseline")
    importlib.import_module("sre_agent.ports.cloud_operator")
    importlib.import_module("sre_agent.ports.telemetry")
    details.append("Core domain imports succeed without cloud SDKs")


# ═══════════════════════════════════════════════════════════════════
# RUNNER
# ═══════════════════════════════════════════════════════════════════

ALL_TESTS = {
    "data_model": [
        test_compute_mechanism_enum,
        test_service_labels_backward_compat,
        test_serverless_service_labels,
        test_anomaly_alert_types,
        test_service_node_compute_aware,
        test_correlated_signals_compute_aware,
    ],
    "baseline": [
        test_baseline_service_learning,
        test_baseline_deviation,
    ],
    "detection": [
        test_detection_latency_spike,
        test_no_false_positive_stable,
        test_memory_pressure_fires,
    ],
    "correlator": [
        test_ebpf_degradation_serverless,
    ],
    "serverless": [
        test_cold_start_suppression,
        test_memory_exempted_serverless,
        test_invocation_error_surge,
    ],
    "registry": [
        test_registry_resolves,
        test_registry_health_check,
    ],
    "resilience": [
        test_circuit_breaker_lifecycle,
        test_retry_recovers,
    ],
    "architecture": [
        test_no_domain_imports_adapters,
        test_ports_no_concrete_deps,
        test_optional_deps_base_install,
    ],
}


def main():
    parser = argparse.ArgumentParser(description="Phase 1+1.5 Component Validation")
    parser.add_argument("--test", type=str, help="Run specific test group")
    parser.add_argument("--all", action="store_true", help="Run all tests")
    args = parser.parse_args()

    if not args.all and not args.test:
        args.all = True

    groups = list(ALL_TESTS.keys()) if args.all else [args.test]
    total_start = time.monotonic()

    print("=" * 70)
    print("  Phase 1 + 1.5 Component Validation")
    print("=" * 70)

    for group in groups:
        if group not in ALL_TESTS:
            print(f"\n❌ Unknown test group: {group}")
            print(f"   Available: {', '.join(ALL_TESTS.keys())}")
            continue

        print(f"\n── {group.upper()} ──")
        for test_fn in ALL_TESTS[group]:
            test_fn()

    elapsed = (time.monotonic() - total_start) * 1000
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)

    print(f"\n{'=' * 70}")
    print(f"  RESULTS: {passed} passed, {failed} failed ({elapsed:.0f}ms)")
    print(f"{'=' * 70}")

    if failed:
        print("\n── FAILURES ──")
        for r in results:
            if not r.passed:
                print(f"  ❌ {r.name}: {r.error}")
        sys.exit(1)
    else:
        print("\n✅ ALL COMPONENT VALIDATIONS PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
