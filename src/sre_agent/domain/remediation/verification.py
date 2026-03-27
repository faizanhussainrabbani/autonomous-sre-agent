"""Post-remediation verification logic."""

from __future__ import annotations

from sre_agent.domain.remediation.models import VerificationStatus


class RemediationVerifier:
    """Evaluates remediation outcomes against baseline tolerance."""

    def verify_metrics(
        self,
        metrics_after: dict[str, float],
        baseline: dict[str, float],
        sigma_tolerance: float = 1.0,
    ) -> VerificationStatus:
        if not baseline:
            return VerificationStatus.SKIPPED

        keys = ["latency", "error_rate", "throughput"]
        for key in keys:
            if key not in baseline or key not in metrics_after:
                continue
            delta = abs(metrics_after[key] - baseline[key])
            if delta > sigma_tolerance:
                return VerificationStatus.METRICS_DEGRADED

        return VerificationStatus.METRICS_NORMALIZED
