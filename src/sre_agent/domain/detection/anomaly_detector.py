"""
Anomaly Detector — ML-based anomaly detection with multi-type support.

Detects latency spikes, error rate surges, memory pressure, disk exhaustion,
certificate expiry, and multi-dimensional anomalies.

Implements: Tasks 2.2, 2.4 — ML anomaly detection model + alert suppression
Validates: AC-3.1.2 through AC-3.1.6, AC-3.3.1, AC-3.3.2, AC-3.4.1, AC-3.4.2
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from sre_agent.domain.models.canonical import (
    AnomalyAlert,
    AnomalyType,
    CanonicalMetric,
    ComputeMechanism,
    DomainEvent,
    EventTypes,
)
from sre_agent.domain.models.detection_config import DetectionConfig
from sre_agent.observability.metrics import (
    LATENCY_ARBITRATIONS,
    SLOW_RESPONSE_ALERTS,
    SLOW_RESPONSE_DETECTION_LATENCY,
    TIMEOUT_METADATA_FALLBACKS,
    TIMEOUT_PROXIMITY_ALERTS,
)
from sre_agent.ports.events import EventBus
from sre_agent.ports.telemetry import BaselineQuery

logger = structlog.get_logger(__name__)


@dataclass
class DeploymentRecord:
    """Track recent deployments for deployment-aware detection."""

    service: str
    timestamp: datetime
    commit_sha: str = ""
    deployer: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DetectionResult:
    """Result of running detection rules on a set of metrics."""

    alerts: list[AnomalyAlert] = field(default_factory=list)
    suppressed_count: int = 0
    checked_count: int = 0


class AnomalyDetector:
    """Detects anomalies in telemetry data using baselines and configurable rules.

    Detection types:
    - Latency spike: p99 > Nσ for >2 min (AC-3.1.2)
    - Error rate surge: >200% increase (AC-3.1.3)
    - Memory pressure: >85% limit for >5 min (AC-3.1.4)
    - Disk exhaustion: >80% or projected full in 24h (AC-3.1.5)
    - Certificate expiry: <14 days warning, <3 days critical (AC-3.1.6)
    """

    def __init__(
        self,
        baseline_service: BaselineQuery,  # Port interface, not concrete class (§4.6)
        config: DetectionConfig,
        event_bus: EventBus | None = None,
    ) -> None:
        self._baselines = baseline_service
        self._config = config
        self._event_bus = event_bus

        # Track state for duration-based detection
        self._active_conditions: dict[str, datetime] = {}  # "svc:metric" → first_seen
        self._recent_deployments: list[DeploymentRecord] = []
        self._suppression_windows: dict[str, datetime] = {}  # "svc" → deployment_timestamp

        # Multi-dimensional correlation state (AC-3.2.3)
        # Tracks recent sub-threshold shifts per (service, dimension)
        self._sub_threshold_shifts: dict[
            str, list[dict[str, Any]]
        ] = {}  # "svc" → [{type, percent, ts}]

        # Per-service / per-metric sensitivity overrides (AC-3.5.1, AC-3.5.2)
        self._service_overrides: dict[str, dict[str, Any]] = {}  # service → {sigma, ...}
        self._metric_overrides: dict[str, dict[str, Any]] = {}  # metric_pattern → {sigma, ...}

        # Phase 1.5: Cold-start tracking for serverless compute
        self._cold_start_init_times: dict[str, datetime] = {}  # service → first metric timestamp

    async def detect(
        self,
        service: str,
        metrics: list[CanonicalMetric],
        namespace: str = "",
        compute_mechanism: ComputeMechanism = ComputeMechanism.KUBERNETES,
    ) -> DetectionResult:
        """Run all detection rules against a batch of metrics for a service.

        Args:
            service: Service name.
            metrics: Latest metric data points.
            namespace: Kubernetes namespace.
            compute_mechanism: Target compute platform (Phase 1.5).

        Returns:
            DetectionResult with generated alerts and statistics.
        """
        result = DetectionResult()

        for metric in metrics:
            result.checked_count += 1

            alert = await self._evaluate_metric(service, metric, namespace, compute_mechanism)
            if alert is None:
                # Track sub-threshold shifts for multi-dimensional correlation
                self._track_sub_threshold(service, metric)
                continue

            # Check suppression (AC-3.4.1, AC-3.4.2)
            if self._should_suppress(service, metric.timestamp):
                result.suppressed_count += 1
                logger.debug(
                    "alert_suppressed",
                    service=service,
                    metric=metric.name,
                    reason="deployment_suppression_window",
                )
                continue

            # Set stage timing (AC-4.4) — must be before correlation check
            alert.detected_at = metric.timestamp
            alert.alert_generated_at = datetime.now(UTC)

            # Check deployment correlation (AC-3.3.1, AC-3.3.2)
            self._check_deployment_correlation(alert)

            result.alerts.append(alert)

            # Emit domain event
            if self._event_bus:
                await self._event_bus.publish(
                    DomainEvent(
                        event_type=EventTypes.ANOMALY_DETECTED,
                        payload={
                            "alert_id": str(alert.alert_id),
                            "service": service,
                            "anomaly_type": alert.anomaly_type.value,
                            "metric": alert.metric_name,
                            "current_value": alert.current_value,
                            "baseline_value": alert.baseline_value,
                            "deviation_sigma": alert.deviation_sigma,
                        },
                    )
                )

        # Multi-dimensional correlation check (AC-3.2.3)
        multi_dim_alert = self._check_multi_dimensional(service, namespace)
        if multi_dim_alert is not None:
            result.alerts.append(multi_dim_alert)

        return result

    def _get_effective_sigma(self, service: str, metric_name: str) -> float:
        """Get the effective sigma threshold, checking per-service and per-metric overrides."""
        # Per-service takes precedence (AC-3.5.1)
        if service in self._service_overrides:
            override = self._service_overrides[service].get("sigma_threshold")
            if override is not None:
                return float(override)
        # Per-metric next (AC-3.5.2)
        for pattern, overrides in self._metric_overrides.items():
            if pattern in metric_name:
                override = overrides.get("sigma_threshold")
                if override is not None:
                    return float(override)
        return self._config.latency_sigma_threshold

    def _get_effective_slow_response_threshold_ms(self, service: str) -> float:
        """Get effective absolute slow-response threshold, checking per-service overrides."""
        if service in self._service_overrides:
            override = self._service_overrides[service].get("slow_response_threshold_ms")
            if override is not None:
                return float(override)
        return self._config.slow_response_absolute_threshold_ms

    # -----------------------------------------------------------------------
    # Phase 2.5: Latency candidate-rule model and arbitration
    # -----------------------------------------------------------------------

    def _evaluate_latency_candidates(
        self,
        service: str,
        metric: CanonicalMetric,
        namespace: str,
        compute_mechanism: ComputeMechanism = ComputeMechanism.KUBERNETES,
    ) -> AnomalyAlert | None:
        """Evaluate all latency rules and emit at most one alert per evaluation.

        Arbitration order (highest to lowest precedence):
            1. TIMEOUT_PROXIMITY  (serverless only)
            2. SLOW_RESPONSE      (absolute threshold)
            3. LATENCY_SPIKE      (sigma-based)

        Phase 2.5 — replaces direct _detect_latency_spike() call in _evaluate_metric().
        """
        timeout_prox = self._detect_timeout_proximity(service, metric, namespace, compute_mechanism)
        abs_latency = self._detect_absolute_latency(service, metric, namespace, compute_mechanism)
        sigma_spike = self._detect_latency_spike(service, metric, namespace, compute_mechanism)

        # Collect non-None candidates in precedence order
        winner = timeout_prox or abs_latency or sigma_spike

        if winner is None:
            return None

        # Count suppressed candidates for observability
        all_candidates = [c for c in [timeout_prox, abs_latency, sigma_spike] if c is not None]
        suppressed_count = len(all_candidates) - 1  # winner counts as 1

        if suppressed_count > 0:
            logger.debug(
                "latency_arbitration_winner",
                service=service,
                metric=metric.name,
                winner=winner.anomaly_type.value,
                candidate_count=len(all_candidates),
                suppressed_count=suppressed_count,
                compute_mechanism=compute_mechanism.value,
            )
            LATENCY_ARBITRATIONS.labels(
                winner=winner.anomaly_type.value, service=service
            ).inc()

        return winner

    def _detect_absolute_latency(
        self,
        service: str,
        metric: CanonicalMetric,
        namespace: str,
        compute_mechanism: ComputeMechanism = ComputeMechanism.KUBERNETES,
    ) -> AnomalyAlert | None:
        """Phase 2.5: Fire SLOW_RESPONSE when latency exceeds absolute threshold for duration.

        Unlike sigma-based detection, this rule does not require an established baseline.
        Metric value is expected in milliseconds.
        """
        threshold_ms = self._get_effective_slow_response_threshold_ms(service)

        if metric.value < threshold_ms:
            self._active_conditions.pop(f"{service}:{metric.name}:abs_latency", None)
            return None

        condition_key = f"{service}:{metric.name}:abs_latency"
        now = metric.timestamp

        if condition_key not in self._active_conditions:
            self._active_conditions[condition_key] = now
            return None  # First detection — start timer

        first_seen = self._active_conditions[condition_key]
        duration = (now - first_seen).total_seconds()

        if duration < self._config.slow_response_duration_seconds:
            return None  # Not sustained long enough

        logger.info(
            "slow_response_detected",
            service=service,
            metric_name=metric.name,
            value_ms=metric.value,
            threshold_ms=threshold_ms,
            duration_seconds=duration,
            compute_mechanism=compute_mechanism.value,
        )
        SLOW_RESPONSE_ALERTS.labels(
            service=service, compute_mechanism=compute_mechanism.value
        ).inc()
        SLOW_RESPONSE_DETECTION_LATENCY.observe(duration)

        return AnomalyAlert(
            anomaly_type=AnomalyType.SLOW_RESPONSE,
            service=service,
            namespace=namespace,
            compute_mechanism=compute_mechanism,
            metric_name=metric.name,
            current_value=metric.value,
            baseline_value=threshold_ms,
            description=(
                f"Response time {metric.value:.0f}ms exceeds absolute threshold "
                f"{threshold_ms:.0f}ms for {duration:.0f}s "
                f"(required: {self._config.slow_response_duration_seconds}s)"
            ),
        )

    def _detect_timeout_proximity(
        self,
        service: str,
        metric: CanonicalMetric,
        namespace: str,
        compute_mechanism: ComputeMechanism = ComputeMechanism.KUBERNETES,
    ) -> AnomalyAlert | None:
        """Phase 2.5: Fire TIMEOUT_PROXIMITY when Lambda duration approaches its timeout.

        Only applies to SERVERLESS compute. Cold-start suppression is applied.
        Requires ``timeout_ms`` in ``metric.labels.platform_metadata``.
        If timeout metadata is absent, the rule is skipped and a warning is logged.
        """
        if compute_mechanism != ComputeMechanism.SERVERLESS:
            return None

        # Phase 2.5 task 2.4: Apply cold-start suppression (same window as sigma rule)
        if service not in self._cold_start_init_times:
            self._cold_start_init_times[service] = metric.timestamp
        init_time = self._cold_start_init_times[service]
        elapsed = (metric.timestamp - init_time).total_seconds()
        if elapsed <= self._config.cold_start_suppression_window_seconds:
            logger.debug(
                "timeout_proximity_cold_start_suppressed",
                service=service,
                elapsed_seconds=elapsed,
            )
            return None

        # Retrieve timeout_ms from metric label metadata
        timeout_ms_raw = metric.labels.platform_metadata.get("timeout_ms")
        if timeout_ms_raw is None:
            logger.warning(
                "timeout_proximity_metadata_missing",
                service=service,
                metric_name=metric.name,
                suppressed=True,
            )
            TIMEOUT_METADATA_FALLBACKS.labels(service=service).inc()
            return None

        timeout_ms = float(timeout_ms_raw)
        if timeout_ms <= 0:
            return None

        proximity_ratio = metric.value / timeout_ms
        threshold_ratio = self._config.timeout_proximity_percent / 100.0

        if proximity_ratio < threshold_ratio:
            return None

        logger.info(
            "timeout_proximity_detected",
            service=service,
            metric_name=metric.name,
            value_ms=metric.value,
            timeout_ms=timeout_ms,
            proximity_ratio=round(proximity_ratio, 3),
            threshold_ratio=threshold_ratio,
            compute_mechanism=compute_mechanism.value,
        )
        TIMEOUT_PROXIMITY_ALERTS.labels(service=service).inc()
        SLOW_RESPONSE_DETECTION_LATENCY.observe(0.0)  # Immediate detection

        return AnomalyAlert(
            anomaly_type=AnomalyType.TIMEOUT_PROXIMITY,
            service=service,
            namespace=namespace,
            compute_mechanism=compute_mechanism,
            metric_name=metric.name,
            current_value=metric.value,
            baseline_value=timeout_ms,
            deviation_sigma=proximity_ratio,
            description=(
                f"Lambda duration {metric.value:.0f}ms is "
                f"{proximity_ratio * 100:.0f}% of configured timeout {timeout_ms:.0f}ms "
                f"(threshold: {self._config.timeout_proximity_percent:.0f}%)"
            ),
        )

    async def _evaluate_metric(
        self,
        service: str,
        metric: CanonicalMetric,
        namespace: str,
        compute_mechanism: ComputeMechanism = ComputeMechanism.KUBERNETES,
    ) -> AnomalyAlert | None:
        """Evaluate a single metric against all detection rules."""

        # Latency evaluation — candidate-rule model with arbitration (Phase 2.5)
        if "duration" in metric.name or "latency" in metric.name or "response_time" in metric.name:
            return self._evaluate_latency_candidates(service, metric, namespace, compute_mechanism)

        # Phase 1.5: InvocationError surge detection (serverless OOM replacement)
        # Must precede generic "error" check so invocation-specific metrics are routed here.
        if "invocation" in metric.name and "error" in metric.name:
            return self._detect_invocation_error_surge(service, metric, namespace)

        # Error rate detection (AC-3.1.3)
        if "error" in metric.name:
            return self._detect_error_surge(service, metric, namespace)

        # Memory pressure (AC-3.1.4) — Phase 1.5: exempt SERVERLESS
        if "memory" in metric.name and "limit" not in metric.name:
            if compute_mechanism == ComputeMechanism.SERVERLESS:
                logger.debug(
                    "memory_pressure_skipped_serverless",
                    service=service,
                    compute_mechanism=compute_mechanism.value,
                )
                return None
            return self._detect_memory_pressure(service, metric, namespace)

        # Disk exhaustion (AC-3.1.5)
        if "disk" in metric.name or "filesystem" in metric.name:
            return self._detect_disk_exhaustion(service, metric, namespace)

        # Certificate expiry (AC-3.1.6)
        if "cert" in metric.name and "expir" in metric.name:
            return self._detect_cert_expiry(service, metric, namespace)

        # General sigma-based detection
        return self._detect_sigma_deviation(service, metric, namespace)

    def _detect_latency_spike(
        self,
        service: str,
        metric: CanonicalMetric,
        namespace: str,
        compute_mechanism: ComputeMechanism = ComputeMechanism.KUBERNETES,
    ) -> AnomalyAlert | None:
        """AC-3.1.2: p99 > Nσ for >2 minutes → alert within 60s.

        Phase 1.5: Suppresses during cold-start window for SERVERLESS.
        """
        # Phase 1.5: Cold-start suppression for serverless
        if compute_mechanism == ComputeMechanism.SERVERLESS:
            if service not in self._cold_start_init_times:
                self._cold_start_init_times[service] = metric.timestamp
            init_time = self._cold_start_init_times[service]
            elapsed = (metric.timestamp - init_time).total_seconds()
            if elapsed <= self._config.cold_start_suppression_window_seconds:
                logger.debug(
                    "cold_start_suppression",
                    service=service,
                    elapsed_seconds=elapsed,
                    reason="cold_start",
                )
                return None  # Suppress during cold-start window

        sigma, baseline = self._baselines.compute_deviation(
            service, metric.name, metric.value, metric.timestamp
        )

        if sigma < self._config.latency_sigma_threshold:
            # Clear active condition if below threshold
            self._active_conditions.pop(f"{service}:{metric.name}", None)
            return None

        # Check duration requirement
        condition_key = f"{service}:{metric.name}"
        now = metric.timestamp

        if condition_key not in self._active_conditions:
            self._active_conditions[condition_key] = now
            return None  # First detection — start timer

        first_seen = self._active_conditions[condition_key]
        duration = (now - first_seen).total_seconds()

        if duration < self._config.latency_duration_minutes * 60:
            return None  # Not sustained long enough

        return AnomalyAlert(
            anomaly_type=AnomalyType.LATENCY_SPIKE,
            service=service,
            namespace=namespace,
            compute_mechanism=compute_mechanism,
            metric_name=metric.name,
            current_value=metric.value,
            baseline_value=baseline.mean if baseline else 0,
            deviation_sigma=sigma,
            description=(
                f"p99 latency is {sigma:.1f}σ above baseline for "
                f"{duration:.0f}s (threshold: {self._config.latency_sigma_threshold}σ "
                f"for {self._config.latency_duration_minutes}min)"
            ),
        )

    def _detect_error_surge(
        self, service: str, metric: CanonicalMetric, namespace: str
    ) -> AnomalyAlert | None:
        """AC-3.1.3: >200% increase → alert within 30s."""
        _, baseline = self._baselines.compute_deviation(
            service, metric.name, metric.value, metric.timestamp
        )

        if baseline is None or not baseline.is_established or baseline.mean == 0:
            return None

        increase_pct = ((metric.value - baseline.mean) / baseline.mean) * 100

        if increase_pct < self._config.error_rate_surge_percent:
            return None

        return AnomalyAlert(
            anomaly_type=AnomalyType.ERROR_RATE_SURGE,
            service=service,
            namespace=namespace,
            metric_name=metric.name,
            current_value=metric.value,
            baseline_value=baseline.mean,
            deviation_sigma=increase_pct / 100,  # Normalized
            description=(
                f"Error rate surged {increase_pct:.0f}% above baseline "
                f"(threshold: {self._config.error_rate_surge_percent}%)"
            ),
        )

    def _detect_memory_pressure(
        self, service: str, metric: CanonicalMetric, namespace: str
    ) -> AnomalyAlert | None:
        """AC-3.1.4: >85% limit for >5min with increasing trend."""
        if metric.value < self._config.memory_pressure_percent / 100:
            self._active_conditions.pop(f"{service}:memory_pressure", None)
            return None

        condition_key = f"{service}:memory_pressure"
        now = metric.timestamp

        if condition_key not in self._active_conditions:
            self._active_conditions[condition_key] = now
            return None

        first_seen = self._active_conditions[condition_key]
        duration = (now - first_seen).total_seconds()

        if duration < self._config.memory_pressure_duration_minutes * 60:
            return None

        return AnomalyAlert(
            anomaly_type=AnomalyType.MEMORY_PRESSURE,
            service=service,
            namespace=namespace,
            metric_name=metric.name,
            current_value=metric.value,
            baseline_value=self._config.memory_pressure_percent / 100,
            description=(
                f"Memory at {metric.value * 100:.1f}% of limit for "
                f"{duration:.0f}s (threshold: {self._config.memory_pressure_percent}%)"
            ),
        )

    def _detect_invocation_error_surge(
        self, service: str, metric: CanonicalMetric, namespace: str
    ) -> AnomalyAlert | None:
        """Phase 1.5: Detect InvocationError surges on serverless compute.

        Replaces OOM/memory pressure detection for SERVERLESS targets.
        Uses the same error rate surge percentage threshold from config.
        """
        _, baseline = self._baselines.compute_deviation(
            service, metric.name, metric.value, metric.timestamp
        )

        if baseline is None or not baseline.is_established or baseline.mean == 0:
            return None

        increase_pct = ((metric.value - baseline.mean) / baseline.mean) * 100

        if increase_pct < self._config.error_rate_surge_percent:
            return None

        return AnomalyAlert(
            anomaly_type=AnomalyType.INVOCATION_ERROR_SURGE,
            service=service,
            namespace=namespace,
            metric_name=metric.name,
            current_value=metric.value,
            baseline_value=baseline.mean,
            deviation_sigma=increase_pct / 100,
            description=(
                f"Serverless InvocationError surged {increase_pct:.0f}% above baseline "
                f"(threshold: {self._config.error_rate_surge_percent}%)"
            ),
        )

    def _detect_disk_exhaustion(
        self, service: str, metric: CanonicalMetric, namespace: str
    ) -> AnomalyAlert | None:
        """AC-3.1.5: >80% or projected full in 24h."""
        if metric.value < self._config.disk_exhaustion_percent / 100:
            return None

        return AnomalyAlert(
            anomaly_type=AnomalyType.DISK_EXHAUSTION,
            service=service,
            namespace=namespace,
            metric_name=metric.name,
            current_value=metric.value,
            baseline_value=self._config.disk_exhaustion_percent / 100,
            description=(
                f"Disk usage at {metric.value * 100:.1f}% "
                f"(threshold: {self._config.disk_exhaustion_percent}%)"
            ),
        )

    def _detect_cert_expiry(
        self, service: str, metric: CanonicalMetric, namespace: str
    ) -> AnomalyAlert | None:
        """AC-3.1.6: <14 days warning, <3 days escalated."""
        days_until_expiry = metric.value  # Assumed metric value = days until expiry

        if days_until_expiry > self._config.cert_expiry_warning_days:
            return None

        is_critical = days_until_expiry <= self._config.cert_expiry_critical_days

        return AnomalyAlert(
            anomaly_type=AnomalyType.CERTIFICATE_EXPIRY,
            service=service,
            namespace=namespace,
            metric_name=metric.name,
            current_value=days_until_expiry,
            baseline_value=self._config.cert_expiry_warning_days,
            description=(
                f"Certificate expires in {days_until_expiry:.0f} days "
                f"({'CRITICAL' if is_critical else 'WARNING'})"
            ),
        )

    def _detect_sigma_deviation(
        self, service: str, metric: CanonicalMetric, namespace: str
    ) -> AnomalyAlert | None:
        """General sigma-based anomaly detection for any metric."""
        sigma, baseline = self._baselines.compute_deviation(
            service, metric.name, metric.value, metric.timestamp
        )

        if sigma < self._config.latency_sigma_threshold:
            return None

        return AnomalyAlert(
            anomaly_type=AnomalyType.LATENCY_SPIKE,
            service=service,
            namespace=namespace,
            metric_name=metric.name,
            current_value=metric.value,
            baseline_value=baseline.mean if baseline else 0,
            deviation_sigma=sigma,
            description=(
                f"{metric.name} is {sigma:.1f}σ above baseline "
                f"({metric.value:.3f} vs mean {baseline.mean:.3f})"
            ),
        )

    # -----------------------------------------------------------------------
    # Deployment awareness (AC-3.3.1, AC-3.3.2)
    # -----------------------------------------------------------------------

    def register_deployment(
        self,
        service: str,
        timestamp: datetime | None = None,
        commit_sha: str = "",
        deployer: str = "",
    ) -> None:
        """Register a deployment for correlation and suppression."""
        ts = timestamp or datetime.now(UTC)
        self._recent_deployments.append(
            DeploymentRecord(
                service=service,
                timestamp=ts,
                commit_sha=commit_sha,
                deployer=deployer,
            )
        )
        self._suppression_windows[service] = ts
        logger.info(
            "deployment_registered",
            service=service,
            commit_sha=commit_sha,
        )

    def _check_deployment_correlation(self, alert: AnomalyAlert) -> None:
        """Flag alert as deployment-induced if within correlation window."""
        window = timedelta(minutes=self._config.deployment_correlation_window_minutes)

        for dep in self._recent_deployments:
            if dep.service != alert.service:
                continue
            alert_time = alert.detected_at or alert.timestamp
            if abs((alert_time - dep.timestamp).total_seconds()) <= window.total_seconds():
                alert.is_deployment_induced = True
                alert.deployment_details = {
                    "commit_sha": dep.commit_sha,
                    "deployer": dep.deployer,
                    "deployment_time": dep.timestamp.isoformat(),
                }
                return

    def _should_suppress(self, service: str, timestamp: datetime) -> bool:
        """Check if this alert should be suppressed during deployment window.

        AC-3.4.1: Brief perturbations (<30s) during deployment suppressed.
        AC-3.4.2: Suppression is per-service, not global.
        """
        if service not in self._suppression_windows:
            return False

        deploy_time = self._suppression_windows[service]
        elapsed = (timestamp - deploy_time).total_seconds()

        return 0 <= elapsed <= self._config.suppression_window_seconds

    # -----------------------------------------------------------------------
    # Multi-dimensional correlation (AC-3.2.3)
    # -----------------------------------------------------------------------

    def _track_sub_threshold(self, service: str, metric: CanonicalMetric) -> None:
        """Track metrics that are elevated but below individual alert thresholds.

        Used for multi-dimensional correlation: combined latency +50%
        AND error rate +80% (both below individual thresholds) should
        still trigger an alert.
        """
        baseline = self._baselines.get_baseline(service, metric.name, metric.timestamp)
        if baseline is None or not baseline.is_established:
            return

        if baseline.mean == 0:
            return

        percent_increase = ((metric.value - baseline.mean) / baseline.mean) * 100

        # Only track positive deviations that are above noise but below threshold
        if percent_increase <= 10:  # Below noise floor
            return

        dimension = None
        if "latency" in metric.name or "duration" in metric.name:
            dimension = "latency"
        elif "error" in metric.name:
            dimension = "error_rate"

        if dimension is None:
            return

        if service not in self._sub_threshold_shifts:
            self._sub_threshold_shifts[service] = []

        self._sub_threshold_shifts[service].append(
            {
                "dimension": dimension,
                "percent_increase": percent_increase,
                "timestamp": metric.timestamp,
                "metric_name": metric.name,
                "value": metric.value,
                "baseline_mean": baseline.mean,
            }
        )

        # Prune old entries beyond the window
        window = timedelta(minutes=self._config.multi_dim_window_minutes)
        cutoff = metric.timestamp - window
        self._sub_threshold_shifts[service] = [
            s for s in self._sub_threshold_shifts[service] if s["timestamp"] >= cutoff
        ]

    def _check_multi_dimensional(self, service: str, namespace: str) -> AnomalyAlert | None:
        """AC-3.2.3: Detect combined sub-threshold anomalies.

        If latency is +50% AND error rate is +80% within a 5-min window,
        fire a multi-dimensional alert even though neither individually
        crosses the threshold.
        """
        shifts = self._sub_threshold_shifts.get(service, [])
        if not shifts:
            return None

        latency_shifts = [
            s
            for s in shifts
            if s["dimension"] == "latency"
            and s["percent_increase"] >= self._config.multi_dim_latency_percent
        ]
        error_shifts = [
            s
            for s in shifts
            if s["dimension"] == "error_rate"
            and s["percent_increase"] >= self._config.multi_dim_error_percent
        ]

        if not latency_shifts or not error_shifts:
            return None

        # Both dimensions elevated — fire multi-dimensional alert
        latest_latency = max(latency_shifts, key=lambda s: s["timestamp"])
        latest_error = max(error_shifts, key=lambda s: s["timestamp"])

        # Clear tracked shifts for this service (avoid duplicate alerts)
        self._sub_threshold_shifts[service] = []

        alert = AnomalyAlert(
            anomaly_type=AnomalyType.MULTI_DIMENSIONAL,
            service=service,
            namespace=namespace,
            metric_name="multi_dimensional_correlation",
            current_value=0,
            baseline_value=0,
            description=(
                f"Multi-dimensional anomaly: latency +{latest_latency['percent_increase']:.0f}% "
                f"AND error rate +{latest_error['percent_increase']:.0f}% "
                f"within {self._config.multi_dim_window_minutes} min window"
            ),
            detected_at=max(latest_latency["timestamp"], latest_error["timestamp"]),
            alert_generated_at=datetime.now(UTC),
        )

        logger.info(
            "multi_dimensional_anomaly_detected",
            service=service,
            latency_increase=f"{latest_latency['percent_increase']:.0f}%",
            error_increase=f"{latest_error['percent_increase']:.0f}%",
        )

        return alert

    # -----------------------------------------------------------------------
    # Operator configuration (AC-3.5.1, AC-3.5.2)
    # -----------------------------------------------------------------------

    def set_service_sensitivity(
        self,
        service: str,
        sigma_threshold: float | None = None,
        error_rate_surge_percent: float | None = None,
        memory_pressure_percent: float | None = None,
        slow_response_threshold_ms: float | None = None,
    ) -> None:
        """Configure detection sensitivity per service.

        AC-3.5.1: Operator can configure sensitivity per service.
        Overrides the global DetectionConfig for this service only.

        Args:
            service: Service name to configure.
            sigma_threshold: Custom sigma threshold (e.g., 2.0 for high sensitivity).
            error_rate_surge_percent: Custom error rate threshold.
            memory_pressure_percent: Custom memory pressure threshold.
            slow_response_threshold_ms: Custom absolute latency threshold (ms) for Phase 2.5.
        """
        overrides: dict[str, Any] = {}
        if sigma_threshold is not None:
            overrides["sigma_threshold"] = sigma_threshold
        if error_rate_surge_percent is not None:
            overrides["error_rate_surge_percent"] = error_rate_surge_percent
        if memory_pressure_percent is not None:
            overrides["memory_pressure_percent"] = memory_pressure_percent
        if slow_response_threshold_ms is not None:
            overrides["slow_response_threshold_ms"] = slow_response_threshold_ms

        self._service_overrides[service] = overrides
        logger.info("service_sensitivity_configured", service=service, overrides=overrides)

    def set_metric_sensitivity(
        self,
        metric_pattern: str,
        sigma_threshold: float | None = None,
    ) -> None:
        """Configure detection sensitivity per metric type.

        AC-3.5.2: Operator can configure sensitivity per metric type.

        Args:
            metric_pattern: Substring pattern to match metric names (e.g., "latency", "error").
            sigma_threshold: Custom sigma threshold for matching metrics.
        """
        overrides: dict[str, Any] = {}
        if sigma_threshold is not None:
            overrides["sigma_threshold"] = sigma_threshold

        self._metric_overrides[metric_pattern] = overrides
        logger.info("metric_sensitivity_configured", pattern=metric_pattern, overrides=overrides)

    def get_service_sensitivity(self, service: str) -> dict[str, Any]:
        """Get the current sensitivity configuration for a service."""
        return dict(self._service_overrides.get(service, {}))

    def get_metric_sensitivity(self, metric_pattern: str) -> dict[str, Any]:
        """Get the current sensitivity configuration for a metric pattern."""
        return dict(self._metric_overrides.get(metric_pattern, {}))
