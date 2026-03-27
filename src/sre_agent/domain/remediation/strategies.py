"""Remediation strategy selection rules."""

from __future__ import annotations

from sre_agent.domain.models.canonical import AnomalyType
from sre_agent.domain.remediation.models import RemediationStrategy

ANOMALY_STRATEGY_MAP: dict[AnomalyType, RemediationStrategy] = {
    AnomalyType.MEMORY_PRESSURE: RemediationStrategy.RESTART,
    AnomalyType.LATENCY_SPIKE: RemediationStrategy.SCALE_UP,
    AnomalyType.TRAFFIC_ANOMALY: RemediationStrategy.SCALE_UP,
    AnomalyType.DEPLOYMENT_INDUCED: RemediationStrategy.GITOPS_REVERT,
    AnomalyType.ERROR_RATE_SURGE: RemediationStrategy.GITOPS_REVERT,
    AnomalyType.CERTIFICATE_EXPIRY: RemediationStrategy.CERTIFICATE_ROTATION,
    AnomalyType.DISK_EXHAUSTION: RemediationStrategy.LOG_TRUNCATION,
    AnomalyType.INVOCATION_ERROR_SURGE: RemediationStrategy.SCALE_DOWN,
}


def select_strategy(
    anomaly_type: AnomalyType,
    root_cause: str,
) -> RemediationStrategy | None:
    """Select remediation strategy from anomaly type and root cause cues."""
    normalized = root_cause.lower().strip()

    if "out of memory" in normalized or "oom" in normalized:
        return RemediationStrategy.RESTART
    if "certificate" in normalized or "tls" in normalized or "x509" in normalized:
        return RemediationStrategy.CERTIFICATE_ROTATION
    if "deployment" in normalized or "regression" in normalized:
        return RemediationStrategy.GITOPS_REVERT
    if "traffic" in normalized or "saturation" in normalized:
        return RemediationStrategy.SCALE_UP
    if "disk" in normalized or "log growth" in normalized or "inode" in normalized:
        return RemediationStrategy.LOG_TRUNCATION

    return ANOMALY_STRATEGY_MAP.get(anomaly_type)
