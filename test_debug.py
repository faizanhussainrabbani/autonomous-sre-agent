from sre_agent.domain.detection.anomaly_detector import *
from sre_agent.domain.models.detection_config import *
from sre_agent.domain.models.canonical import *
from sre_agent.domain.detection.baseline import BaselineService
from sre_agent.events.in_memory import InMemoryEventBus
import asyncio
from datetime import datetime, timedelta, timezone

async def run1():
    event_bus = InMemoryEventBus()
    baseline = BaselineService(event_bus=event_bus)
    config = DetectionConfig(
        latency_sigma_threshold=3.0,
        multi_dim_latency_percent=50.0,
        multi_dim_error_percent=80.0,
        multi_dim_window_minutes=5,
    )
    detector = AnomalyDetector(baseline, config, event_bus=event_bus)
    now = datetime.now(timezone.utc)
    for i in range(35):
        ts = now - timedelta(seconds=i * 10)
        await detector._baselines.ingest("svc-A", "http_request_duration_seconds", 100 + (i % 5), ts)
        await detector._baselines.ingest("svc-A", "http_errors_total", 5 + (i % 3), ts)

    latency_metric = CanonicalMetric(
        name="http_request_duration_seconds",
        value=160.0,  # ~57% above mean of ~102
        timestamp=datetime.now(timezone.utc),
        labels=ServiceLabels(service="svc-A", namespace="default"),
    )
    error_metric = CanonicalMetric(
        name="http_errors_total",
        value=11.0,  # ~83% above mean of ~6
        timestamp=datetime.now(timezone.utc),
        labels=ServiceLabels(service="svc-A", namespace="default"),
    )

    result = await detector.detect("svc-A", [latency_metric, error_metric])
    bl = detector._baselines.get_baseline("svc-A", "http_request_duration_seconds", latency_metric.timestamp)
    be = detector._baselines.get_baseline("svc-A", "http_errors_total", error_metric.timestamp)
    print("Test 1 baseline latency established:", bl.is_established if bl else None)
    print("Test 1 baseline latency mean:", bl.mean if bl else None)
    print("Test 1 baseline error established:", be.is_established if be else None)
    print("Test 1 baseline error mean:", be.mean if be else None)
    print("Test 1 alerts:", result.alerts)
    print("Test 1 shifts:", detector._sub_threshold_shifts)

async def run2():
    baseline = BaselineService()
    config = DetectionConfig(
        latency_sigma_threshold=2.0,
        latency_duration_minutes=0,  # No duration requirement for testing
    )
    detector = AnomalyDetector(baseline, config)

    # Build baseline in SAME hour segment as detection
    now = datetime.now(timezone.utc)
    for i in range(35):
        ts = now - timedelta(seconds=i * 10)
        await baseline.ingest("svc-A", "http_request_duration_seconds", 100 + (i % 5), ts)

    now2 = datetime.now(timezone.utc)

    # First spike: starts the duration timer (returns None)
    spike1 = CanonicalMetric(
        name="http_request_duration_seconds",
        value=900.0,
        timestamp=now2,
        labels=ServiceLabels(service="svc-A", namespace="default"),
    )
    result1 = await detector.detect("svc-A", [spike1])
    print("Test 2 result1 alerts:", result1.alerts)

    # Second spike: same metric, slightly later -> meets duration=0 requirement
    spike2 = CanonicalMetric(
        name="http_request_duration_seconds",
        value=900.0,
        timestamp=now2 + timedelta(seconds=1),
        labels=ServiceLabels(service="svc-A", namespace="default"),
    )
    result2 = await detector.detect("svc-A", [spike2])
    print("Test 2 result2 alerts:", result2.alerts)


asyncio.run(run1())
asyncio.run(run2())
