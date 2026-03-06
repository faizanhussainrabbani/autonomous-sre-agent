"""
Severity Override Service — human supremacy endpoint for severity adjustments.

Allows human operators to override auto-classified severities and halt
pipeline execution when critical severity overrides are applied.

Phase 2: Intelligence Layer — Sprint 3 (Severity & Safety Classification)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

import structlog

from sre_agent.domain.models.canonical import Severity

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class SeverityOverride:
    """Record of a human severity override."""

    alert_id: UUID
    original_severity: Severity
    override_severity: Severity
    operator: str
    reason: str
    applied_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    halts_pipeline: bool = False


class SeverityOverrideService:
    """Service for applying and querying human severity overrides.

    When a human overrides severity to Sev 1 or Sev 2, pipeline execution
    is immediately halted to ensure human review.
    """

    def __init__(self) -> None:
        self._overrides: dict[UUID, SeverityOverride] = {}

    def apply_override(
        self,
        alert_id: UUID,
        original_severity: Severity,
        override_severity: Severity,
        operator: str,
        reason: str = "",
    ) -> SeverityOverride:
        """Apply a human severity override.

        If the override severity is Sev 1 or Sev 2, the pipeline is halted.

        Args:
            alert_id: The alert to override.
            original_severity: The auto-classified severity.
            override_severity: The human-chosen severity.
            operator: Identifier of the human operator.
            reason: Justification for the override.

        Returns:
            The created SeverityOverride record.
        """
        halts = override_severity in (Severity.SEV1, Severity.SEV2)

        override = SeverityOverride(
            alert_id=alert_id,
            original_severity=original_severity,
            override_severity=override_severity,
            operator=operator,
            reason=reason,
            halts_pipeline=halts,
        )

        self._overrides[alert_id] = override

        logger.info(
            "severity_override_applied",
            alert_id=str(alert_id),
            original=original_severity.name,
            override=override_severity.name,
            operator=operator,
            halts_pipeline=halts,
        )

        return override

    def get_override(self, alert_id: UUID) -> SeverityOverride | None:
        """Look up an existing override for an alert.

        Args:
            alert_id: The alert ID to look up.

        Returns:
            The SeverityOverride if one exists, otherwise None.
        """
        return self._overrides.get(alert_id)

    def has_active_override(self, alert_id: UUID) -> bool:
        """Check whether an alert has an active override."""
        return alert_id in self._overrides

    def revoke_override(self, alert_id: UUID) -> bool:
        """Revoke an active severity override, restoring auto-classification.

        Args:
            alert_id: The alert whose override should be removed.

        Returns:
            True if an override existed and was removed; False otherwise.
        """
        if alert_id not in self._overrides:
            return False
        removed = self._overrides.pop(alert_id)
        logger.info(
            "severity_override_revoked",
            alert_id=str(alert_id),
            override_severity=removed.override_severity.name,
        )
        return True
