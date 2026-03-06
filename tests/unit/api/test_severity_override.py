"""
Unit tests for SeverityOverrideService.

Tests Sev1/2 override halts pipeline, Sev3 no halt, override recording.
"""

from __future__ import annotations

import pytest
from uuid import uuid4

from sre_agent.api.severity_override import SeverityOverrideService
from sre_agent.domain.models.canonical import Severity


class TestSeverityOverrideService:
    """Tests for human severity override service."""

    def test_sev1_override_halts_pipeline(self):
        """AC: Sev 3 auto-classification halts if human overrides to Sev 1."""
        service = SeverityOverrideService()
        alert_id = uuid4()
        override = service.apply_override(
            alert_id=alert_id,
            original_severity=Severity.SEV3,
            override_severity=Severity.SEV1,
            operator="sre-engineer@example.com",
            reason="Impact wider than initially classified.",
        )
        assert override.halts_pipeline is True
        assert override.override_severity == Severity.SEV1

    def test_sev2_override_halts_pipeline(self):
        service = SeverityOverrideService()
        alert_id = uuid4()
        override = service.apply_override(
            alert_id=alert_id,
            original_severity=Severity.SEV4,
            override_severity=Severity.SEV2,
            operator="ops-lead",
        )
        assert override.halts_pipeline is True

    def test_sev3_override_does_not_halt(self):
        service = SeverityOverrideService()
        alert_id = uuid4()
        override = service.apply_override(
            alert_id=alert_id,
            original_severity=Severity.SEV4,
            override_severity=Severity.SEV3,
            operator="junior-ops",
        )
        assert override.halts_pipeline is False

    def test_override_is_recorded(self):
        service = SeverityOverrideService()
        alert_id = uuid4()
        service.apply_override(
            alert_id=alert_id,
            original_severity=Severity.SEV3,
            override_severity=Severity.SEV1,
            operator="ops-lead",
        )
        retrieved = service.get_override(alert_id)
        assert retrieved is not None
        assert retrieved.operator == "ops-lead"

    def test_no_override_returns_none(self):
        service = SeverityOverrideService()
        assert service.get_override(uuid4()) is None
