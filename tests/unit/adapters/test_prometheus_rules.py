"""
Unit tests — Phase 2.1 OBS-008: Prometheus alert rules YAML.

Acceptance criteria verified:
  AC-6.1  sre_agent_slo.yaml is valid YAML (parseable by PyYAML).
  AC-6.2  All 8 alert rules are present with correct severity labels.
  AC-6.3  Recording rule sre_agent:diagnosis_latency:p99 is defined.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


RULES_FILE = (
    Path(__file__).parent.parent.parent.parent
    / "infra" / "prometheus" / "rules" / "sre_agent_slo.yaml"
)

EXPECTED_ALERT_NAMES = {
    "DiagnosisLatencySLOBreach",
    "LLMAPIErrors",
    "LLMParseFailureSpike",
    "ThrottleQueueSaturation",
    "EvidenceQualityDrop",
    "LLMTokenRateTooHigh",
    "EmbeddingColdStartHigh",
    "CircuitBreakerOpen",
}


@pytest.fixture(scope="module")
def rules_doc():
    """Parse the YAML rules file once for all tests in this module."""
    assert RULES_FILE.exists(), f"Rules file not found: {RULES_FILE}"
    with RULES_FILE.open() as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# AC-6.1 — Valid YAML
# ---------------------------------------------------------------------------

def test_rules_yaml_is_valid(rules_doc):
    """The rules file must be non-empty valid YAML."""
    assert rules_doc is not None
    assert isinstance(rules_doc, dict)


def test_rules_has_groups(rules_doc):
    """Top-level 'groups' key must be present."""
    assert "groups" in rules_doc
    assert len(rules_doc["groups"]) >= 1


# ---------------------------------------------------------------------------
# AC-6.3 — Recording rule present
# ---------------------------------------------------------------------------

def test_recording_rule_present(rules_doc):
    """Recording rule sre_agent:diagnosis_latency:p99 must be defined."""
    all_records = [
        rule.get("record")
        for group in rules_doc["groups"]
        for rule in group.get("rules", [])
        if "record" in rule
    ]
    assert "sre_agent:diagnosis_latency:p99" in all_records, (
        f"Recording rule not found. Found: {all_records}"
    )


# ---------------------------------------------------------------------------
# AC-6.2 — All 8 alert rules present with severity labels
# ---------------------------------------------------------------------------

def test_all_8_alert_rules_present(rules_doc):
    """All 8 named alert rules must be defined in the rules file."""
    all_alerts = {
        rule.get("alert")
        for group in rules_doc["groups"]
        for rule in group.get("rules", [])
        if "alert" in rule
    }
    missing = EXPECTED_ALERT_NAMES - all_alerts
    assert not missing, f"Missing alert rules: {missing}"


def test_all_alerts_have_severity_label(rules_doc):
    """Every alert rule must have a 'severity' label (critical|warning|info)."""
    valid_severities = {"critical", "warning", "info"}
    for group in rules_doc["groups"]:
        for rule in group.get("rules", []):
            if "alert" not in rule:
                continue
            labels = rule.get("labels", {})
            assert "severity" in labels, (
                f"Alert '{rule['alert']}' is missing a 'severity' label."
            )
            assert labels["severity"] in valid_severities, (
                f"Alert '{rule['alert']}' has invalid severity '{labels['severity']}'."
            )


def test_all_alerts_have_summary_annotation(rules_doc):
    """Every alert rule must have a 'summary' annotation."""
    for group in rules_doc["groups"]:
        for rule in group.get("rules", []):
            if "alert" not in rule:
                continue
            annotations = rule.get("annotations", {})
            assert "summary" in annotations, (
                f"Alert '{rule['alert']}' is missing a 'summary' annotation."
            )


def test_all_alerts_have_runbook_url(rules_doc):
    """Every alert rule should reference a runbook_url annotation."""
    for group in rules_doc["groups"]:
        for rule in group.get("rules", []):
            if "alert" not in rule:
                continue
            annotations = rule.get("annotations", {})
            assert "runbook_url" in annotations, (
                f"Alert '{rule['alert']}' is missing a 'runbook_url' annotation."
            )
