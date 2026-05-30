"""
Phase 2.5 Slow Response E2E Tests.

Covers:
- K8s sigma + absolute latency path
- Lambda timeout proximity with cold-start suppression
- ECS deployment-induced slow-response flag
- Detection-to-alert latency SLO assertion (<= 60s)

Phase 2.5A scope (K8s + AWS). Azure scenarios deferred to Phase 2.5B.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from sre_agent.domain.detection.anomaly_detector import AnomalyDetector
from sre_agent.domain.detection.baseline import BaselineService
from sre_agent.domain.models.canonical import (
    AnomalyType,
    CanonicalMetric,
    ComputeMechanism,
    ServiceLabels,
)
from sre_agent.domain.models.detection_config import DetectionConfig


def _make_k8s_metric(
    value: float,
    ts: datetime,
    service: str = "checkout",
    name: str = "http_request_duration_p99",
) -> CanonicalMetric:
    return CanonicalMetric(
        name=name,
        value=value,
        timestamp=ts,
        labels=ServiceLabels(
            service=service,
            namespace="prod",
            compute_mechanism=ComputeMechanism.KUBERNETES,
        ),
    )


def _make_lambda_metric(
    value: float,
    ts: datetime,
    service: str = "payment-handler",
    timeout_ms: float | None = None,
) -> CanonicalMetric:
    meta = {"timeout_ms": timeout_ms} if timeout_ms is not None else {}
    return CanonicalMetric(
        name="lambda_duration_ms",
        value=value,
        timestamp=ts,
        labels=ServiceLabels(
            service=service,
            compute_mechanism=ComputeMechanism.SERVERLESS,
            platform_metadata=meta,
        ),
    )


def _make_ecs_metric(
    value: float,
    ts: datetime,
    service: str = "order-svc",
) -> CanonicalMetric:
    return CanonicalMetric(
        name="ecs_response_time_ms",
        value=value,
        timestamp=ts,
        labels=ServiceLabels(
            service=service,
            namespace="prod",
            compute_mechanism=ComputeMechanism.CONTAINER_INSTANCE,
        ),
    )


@pytest.mark.e2e
class TestSlowResponseE2E:
    """End-to-end coverage for Phase 2.5A slow-response detection paths."""

    @pytest.mark.asyncio
    async def test_k8s_absolute_latency_path(self):
        """K8s: Absolute threshold fires after sustained duration; sigma rule works alongside."""
        baseline_svc = BaselineService()
        config = DetectionConfig(
            slow_response_absolute_threshold_ms=1000.0,
            slow_response_duration_seconds=0,  # Disable for test speed
            latency_sigma_threshold=3.0,
            latency_duration_minutes=0,
        )
        detector = AnomalyDetector(baseline_svc, config)

        base_ts = datetime(2024, 6, 1, 10, 0, tzinfo=UTC)

        # Prime baseline with normal latency values
        for i in range(35):
            await baseline_svc.ingest(
                "checkout", "http_request_duration_p99", 200.0 + i % 10, base_ts
            )

        # Spike above absolute threshold — first detection starts abs timer
        ts1 = base_ts + timedelta(minutes=5)
        r1 = await detector.detect(
            "checkout", [_make_k8s_metric(2000.0, ts1)], namespace="prod"
        )
        assert len(r1.alerts) == 0  # Timer started, no alert yet

        # Second detection — absolute threshold sustained, alert fires
        ts2 = ts1 + timedelta(seconds=1)
        import time as _time
        t_start = _time.monotonic()
        r2 = await detector.detect(
            "checkout", [_make_k8s_metric(2000.0, ts2)], namespace="prod"
        )
        t_elapsed = _time.monotonic() - t_start
        assert len(r2.alerts) == 1
        assert r2.alerts[0].anomaly_type == AnomalyType.SLOW_RESPONSE

        # SLO: detection-to-alert latency (wall-clock processing time) <= 60s
        assert t_elapsed <= 60, f"Detection-to-alert latency {t_elapsed:.3f}s exceeded 60s SLO"

    @pytest.mark.asyncio
    async def test_lambda_timeout_proximity_with_cold_start_suppression(self):
        """Lambda: Timeout proximity fires after cold-start window; suppressed during window."""
        baseline_svc = BaselineService()
        config = DetectionConfig(
            timeout_proximity_percent=80.0,
            cold_start_suppression_window_seconds=15,
            slow_response_absolute_threshold_ms=100000.0,  # Not applicable
        )
        detector = AnomalyDetector(baseline_svc, config)

        base_ts = datetime(2024, 6, 1, 10, 0, tzinfo=UTC)
        timeout_ms = 10000.0  # 10s timeout

        # Cold-start window: suppressed (elapsed=0 <= 15s window)
        ts_cold = base_ts  # t=0
        r_cold = await detector.detect(
            "payment-handler",
            [_make_lambda_metric(9500.0, ts_cold, timeout_ms=timeout_ms)],
            compute_mechanism=ComputeMechanism.SERVERLESS,
        )
        timeout_alerts = [a for a in r_cold.alerts if a.anomaly_type == AnomalyType.TIMEOUT_PROXIMITY]
        assert len(timeout_alerts) == 0, "Should be suppressed during cold-start window"

        # After cold-start window: should fire
        ts_warm = base_ts + timedelta(seconds=20)
        r_warm = await detector.detect(
            "payment-handler",
            [_make_lambda_metric(9500.0, ts_warm, timeout_ms=timeout_ms)],
            compute_mechanism=ComputeMechanism.SERVERLESS,
        )
        timeout_alerts_warm = [a for a in r_warm.alerts if a.anomaly_type == AnomalyType.TIMEOUT_PROXIMITY]
        assert len(timeout_alerts_warm) == 1

        # SLO: wall-clock processing time for detector.detect() <= 60s
        import time as _time
        t_start = _time.monotonic()
        await detector.detect(
            "payment-handler",
            [_make_lambda_metric(9500.0, ts_warm + timedelta(seconds=5), timeout_ms=timeout_ms)],
            compute_mechanism=ComputeMechanism.SERVERLESS,
        )
        assert _time.monotonic() - t_start <= 60

    @pytest.mark.asyncio
    async def test_ecs_deployment_induced_slow_response(self):
        """ECS: SLOW_RESPONSE alert is flagged as deployment-induced when within window."""
        baseline_svc = BaselineService()
        config = DetectionConfig(
            slow_response_absolute_threshold_ms=500.0,
            slow_response_duration_seconds=0,
            suppression_window_seconds=0,  # Allow alert (not suppress — only flag as induced)
            deployment_correlation_window_minutes=30,
        )
        detector = AnomalyDetector(baseline_svc, config)

        deploy_ts = datetime(2024, 6, 1, 10, 0, tzinfo=UTC)
        detector.register_deployment("order-svc", deploy_ts, commit_sha="abc123")

        # Prime abs timer
        ts1 = deploy_ts + timedelta(seconds=35)  # Outside suppression window (0s)
        await detector.detect(
            "order-svc",
            [_make_ecs_metric(1000.0, ts1)],
            namespace="prod",
        )

        ts2 = ts1 + timedelta(seconds=5)
        result = await detector.detect(
            "order-svc",
            [_make_ecs_metric(1000.0, ts2)],
            namespace="prod",
        )

        slow_alerts = [a for a in result.alerts if a.anomaly_type == AnomalyType.SLOW_RESPONSE]
        assert len(slow_alerts) == 1
        assert slow_alerts[0].is_deployment_induced

    @pytest.mark.asyncio
    async def test_no_false_positive_below_threshold(self):
        """Regression: No SLOW_RESPONSE or TIMEOUT_PROXIMITY below respective thresholds."""
        baseline_svc = BaselineService()
        config = DetectionConfig(
            slow_response_absolute_threshold_ms=3000.0,
            timeout_proximity_percent=90.0,
            cold_start_suppression_window_seconds=0,
        )
        detector = AnomalyDetector(baseline_svc, config)

        ts = datetime(2024, 6, 1, 10, 0, tzinfo=UTC)

        # K8s below absolute threshold
        r_k8s = await detector.detect(
            "checkout",
            [_make_k8s_metric(1500.0, ts)],
            namespace="prod",
        )
        assert not any(
            a.anomaly_type in (AnomalyType.SLOW_RESPONSE, AnomalyType.TIMEOUT_PROXIMITY)
            for a in r_k8s.alerts
        )

        # Lambda below timeout proximity threshold (5s of 10s = 50% < 90%)
        r_lambda = await detector.detect(
            "payment-handler",
            [_make_lambda_metric(5000.0, ts, timeout_ms=10000.0)],
            compute_mechanism=ComputeMechanism.SERVERLESS,
        )
        assert not any(
            a.anomaly_type == AnomalyType.TIMEOUT_PROXIMITY for a in r_lambda.alerts
        )

    @pytest.mark.asyncio
    async def test_existing_latency_spike_not_regressed(self):
        """Regression: LATENCY_SPIKE (sigma) still fires normally after Phase 2.5 refactor."""
        baseline_svc = BaselineService()
        config = DetectionConfig(
            latency_sigma_threshold=3.0,
            latency_duration_minutes=0,
            slow_response_absolute_threshold_ms=100000.0,  # Disable abs rule
        )
        detector = AnomalyDetector(baseline_svc, config)

        base_ts = datetime(2024, 6, 1, 10, 0, tzinfo=UTC)
        # Build strong baseline around 100ms
        for i in range(35):
            await baseline_svc.ingest(
                "checkout", "http_request_duration_p99", 100.0 + (i % 5), base_ts
            )

        # First detection above sigma — starts timer
        ts1 = base_ts + timedelta(minutes=5)
        r1 = await detector.detect(
            "checkout", [_make_k8s_metric(5000.0, ts1)], namespace="prod"
        )
        # May or may not have alert depending on sigma; starts timer at minimum
        ts2 = ts1 + timedelta(seconds=1)
        r2 = await detector.detect(
            "checkout", [_make_k8s_metric(5000.0, ts2)], namespace="prod"
        )

        # Should have at least one alert (LATENCY_SPIKE expected; SLOW_RESPONSE disabled)
        latency_alerts = [
            a for a in r2.alerts if a.anomaly_type == AnomalyType.LATENCY_SPIKE
        ]
        assert len(latency_alerts) == 1
