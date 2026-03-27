"""Operational phase gate evaluator."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PhaseMetrics:
    diagnostic_accuracy: float
    destructive_false_positives: int
    sev34_autonomous_resolution_rate: float
    remediation_integration_coverage: float
    soak_test_clean_days: int


class PhaseGate:
    """Evaluates whether graduation criteria are satisfied."""

    def evaluate_graduation(self, metrics: PhaseMetrics) -> tuple[bool, list[str]]:
        failures: list[str] = []

        if metrics.diagnostic_accuracy < 0.90:
            failures.append("diagnostic_accuracy_below_0.90")
        if metrics.destructive_false_positives > 0:
            failures.append("destructive_false_positives_non_zero")
        if metrics.sev34_autonomous_resolution_rate < 0.95:
            failures.append("sev34_autonomous_resolution_below_0.95")
        if metrics.remediation_integration_coverage < 0.30:
            failures.append("remediation_integration_coverage_below_0.30")
        if metrics.soak_test_clean_days < 7:
            failures.append("soak_test_days_below_7")

        return len(failures) == 0, failures
