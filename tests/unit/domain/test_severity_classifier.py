"""
Unit tests for SeverityClassifier.

Tests hard rules, tier defaults, deployment correlation, weighted scoring.
"""

from __future__ import annotations

import pytest

from sre_agent.domain.diagnostics.severity import SeverityClassifier
from sre_agent.domain.models.canonical import AnomalyAlert, AnomalyType, Severity
from sre_agent.domain.models.diagnosis import ServiceTier


def _make_alert(**kwargs) -> AnomalyAlert:
    """Helper to create an AnomalyAlert with defaults."""
    defaults = {
        "service": "checkout-service",
        "description": "Latency spike detected",
        "anomaly_type": AnomalyType.LATENCY_SPIKE,
        "metric_name": "http_request_duration_seconds",
        "current_value": 2.5,
        "baseline_value": 0.5,
        "deviation_sigma": 3.0,
    }
    defaults.update(kwargs)
    return AnomalyAlert(**defaults)


class TestSeverityClassifier:
    """Tests for deterministic severity classification."""

    def test_data_loss_always_sev1(self):
        classifier = SeverityClassifier()
        alert = _make_alert()
        severity, impact = classifier.classify(alert, is_data_loss=True)
        assert severity == Severity.SEV1
        assert impact.compute_severity_score() == pytest.approx(1.0)

    def test_security_incident_always_sev1(self):
        classifier = SeverityClassifier()
        alert = _make_alert()
        severity, _ = classifier.classify(alert, is_security_incident=True)
        assert severity == Severity.SEV1

    def test_critical_keyword_in_description(self):
        classifier = SeverityClassifier()
        alert = _make_alert(description="Unauthorized access detected on payment gateway")
        severity, _ = classifier.classify(alert)
        assert severity == Severity.SEV1

    def test_missing_tier_defaults_to_tier1(self):
        """AC: Missing k8s service-tier label correctly defaults to Tier 1."""
        classifier = SeverityClassifier(service_tiers={})  # Empty map
        alert = _make_alert(service="unknown-service")
        severity, impact = classifier.classify(
            alert, user_count_affected=5000, max_user_count=10000,
        )
        # Tier 1 (default) gives highest tier_score, likely Sev 1 or 2
        assert impact.service_tier_score == pytest.approx(1.0)

    def test_tier4_low_severity(self):
        tiers = {"batch-job": ServiceTier.TIER_4}
        classifier = SeverityClassifier(service_tiers=tiers)
        alert = _make_alert(service="batch-job", deviation_sigma=1.0)
        severity, impact = classifier.classify(
            alert, user_count_affected=0,
        )
        assert impact.service_tier_score == pytest.approx(0.0)
        assert severity in (Severity.SEV3, Severity.SEV4)

    def test_deployment_correlation_elevation(self):
        """Deployment-induced issues should elevate severity by one level."""
        tiers = {"frontend": ServiceTier.TIER_3}
        classifier = SeverityClassifier(service_tiers=tiers)
        alert = _make_alert(
            service="frontend",
            is_deployment_induced=True,
            deviation_sigma=2.0,
        )
        severity_deployed, _ = classifier.classify(alert)

        alert_no_deploy = _make_alert(
            service="frontend",
            is_deployment_induced=False,
            deviation_sigma=2.0,
        )
        severity_normal, _ = classifier.classify(alert_no_deploy)

        # Deployed should be same or higher severity (lower number)
        assert severity_deployed.value <= severity_normal.value

    def test_high_user_count_increases_severity(self):
        tiers = {"api-gw": ServiceTier.TIER_2}
        classifier = SeverityClassifier(service_tiers=tiers)
        alert = _make_alert(service="api-gw", deviation_sigma=4.0)

        sev_low, _ = classifier.classify(alert, user_count_affected=10)
        sev_high, _ = classifier.classify(alert, user_count_affected=9000)

        assert sev_high.value <= sev_low.value

    def test_blast_radius_impact(self):
        classifier = SeverityClassifier()
        alert = _make_alert(deviation_sigma=4.0)

        sev_narrow, _ = classifier.classify(alert, blast_radius_ratio=0.05)
        sev_wide, _ = classifier.classify(alert, blast_radius_ratio=0.95)

        assert sev_wide.value <= sev_narrow.value

    def test_sev3_classification(self):
        tiers = {"internal-tool": ServiceTier.TIER_3}
        classifier = SeverityClassifier(service_tiers=tiers)
        alert = _make_alert(service="internal-tool", deviation_sigma=2.0)
        severity, _ = classifier.classify(
            alert,
            user_count_affected=100,
            max_user_count=10000,
            blast_radius_ratio=0.1,
        )
        assert severity in (Severity.SEV3, Severity.SEV4)
