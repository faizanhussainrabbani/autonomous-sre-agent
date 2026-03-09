"""
Severity Classifier — deterministic incident severity assignment.

Combines multi-dimensional impact scoring with hard rules and service
tier metadata to assign Sev 1-4 classifications.

Phase 2: Intelligence Layer — Sprint 3 (Severity & Safety Classification)
"""

from __future__ import annotations

import structlog

from sre_agent.domain.models.canonical import AnomalyAlert, AnomalyType, Severity
from sre_agent.domain.models.diagnosis import (
    ImpactDimensions,
    ServiceTier,
)

logger = structlog.get_logger(__name__)

# Anomaly types that always escalate to Sev 1
_CRITICAL_ANOMALY_TYPES = frozenset({
    "data_loss",
    "security_breach",
    "data_corruption",
})

# Keywords in alert descriptions that indicate critical incidents
_CRITICAL_KEYWORDS = frozenset({
    "data loss",
    "security",
    "breach",
    "unauthorized",
    "corruption",
})


class SeverityClassifier:
    """Deterministic severity classification engine.

    Combines:
    1. Hard rules (data loss / security -> always Sev 1)
    2. Service tier metadata (missing tier defaults to Tier 1 = fail-safe)
    3. Multi-dimensional impact scoring (weighted formula)
    4. Deployment correlation elevation
    """

    def __init__(
        self,
        service_tiers: dict[str, ServiceTier] | None = None,
        default_tier: ServiceTier = ServiceTier.TIER_1,
    ) -> None:
        """Initialize the severity classifier.

        Args:
            service_tiers: Mapping of service names to their criticality tier.
            default_tier: Default tier when a service is not found in the map.
                         Defaults to TIER_1 (fail-safe: treat unknown as critical).
        """
        self._service_tiers = service_tiers or {}
        self._default_tier = default_tier

    def classify(
        self,
        alert: AnomalyAlert,
        llm_confidence: float = 0.0,
        blast_radius_ratio: float = 0.0,
        user_count_affected: int = 0,
        max_user_count: int = 10000,
        is_data_loss: bool = False,
        is_security_incident: bool = False,
    ) -> tuple[Severity, ImpactDimensions]:
        """Classify an alert into a severity level.

        Args:
            alert: The anomaly alert to classify.
            llm_confidence: LLM diagnostic confidence for context.
            blast_radius_ratio: Ratio of affected downstream services [0, 1].
            user_count_affected: Estimated number of affected users.
            max_user_count: Maximum expected user count for normalization.
            is_data_loss: Whether the incident involves data loss.
            is_security_incident: Whether the incident is security-related.

        Returns:
            Tuple of (Severity, ImpactDimensions) used for classification.
        """
        # Hard rules: data loss or security always escalate to Sev 1
        if is_data_loss or is_security_incident:
            logger.info(
                "severity_hard_rule_triggered",
                service=alert.service,
                data_loss=is_data_loss,
                security=is_security_incident,
            )
            impact = ImpactDimensions(
                user_impact=1.0,
                service_tier_score=1.0,
                blast_radius=1.0,
                financial_impact=1.0,
                reversibility=0.0,
            )
            return Severity.SEV1, impact

        # Check alert description for critical keywords
        desc_lower = alert.description.lower()
        for keyword in _CRITICAL_KEYWORDS:
            if keyword in desc_lower:
                impact = ImpactDimensions(
                    user_impact=1.0,
                    service_tier_score=1.0,
                    blast_radius=1.0,
                    financial_impact=1.0,
                    reversibility=0.0,
                )
                return Severity.SEV1, impact

        # Resolve service tier (missing defaults to Tier 1 per AC)
        tier = self._service_tiers.get(alert.service, self._default_tier)
        tier_score = 1.0 - ((tier - 1) / 3.0)  # Tier 1 -> 1.0, Tier 4 -> 0.0

        # Compute user impact
        safe_max = max(max_user_count, 1)
        user_impact = min(user_count_affected / safe_max, 1.0)

        # Compute financial impact based on tier and deviation
        deviation_normalized = min(abs(alert.deviation_sigma) / 10.0, 1.0)
        financial_impact = tier_score * deviation_normalized

        # Reversibility: deployment-induced issues are more reversible
        reversibility = 0.8 if alert.is_deployment_induced else 0.4

        impact = ImpactDimensions(
            user_impact=user_impact,
            service_tier_score=tier_score,
            blast_radius=blast_radius_ratio,
            financial_impact=financial_impact,
            reversibility=reversibility,
        )

        severity = impact.to_severity()

        # Deployment correlation: elevate by one level if deployment-induced
        if alert.is_deployment_induced and severity.value < 4:
            elevated = Severity(severity.value - 1) if severity.value > 1 else Severity.SEV1
            logger.info(
                "severity_deployment_elevation",
                service=alert.service,
                original=severity.name,
                elevated=elevated.name,
            )
            severity = elevated

        # Certificate expiry: dynamically floor severity based on hours remaining
        if alert.anomaly_type == AnomalyType.CERTIFICATE_EXPIRY:
            hours_remaining = alert.current_value
            if hours_remaining < 2.0:
                cert_floor: Severity | None = Severity.SEV1
            elif hours_remaining < 6.0:
                cert_floor = Severity.SEV2
            elif hours_remaining < 24.0:
                cert_floor = Severity.SEV3
            else:
                cert_floor = None
            if cert_floor is not None and severity.value > cert_floor.value:
                logger.info(
                    "severity_certificate_expiry_floor",
                    service=alert.service,
                    hours_remaining=hours_remaining,
                    original=severity.name,
                    floor=cert_floor.name,
                )
                severity = cert_floor

        logger.info(
            "severity_classified",
            service=alert.service,
            severity=severity.name,
            score=impact.compute_severity_score(),
            tier=tier,
        )

        return severity, impact

    def get_service_tier(self, service: str) -> "ServiceTier":
        """Resolve the tier for a given service name.

        Returns the configured tier for the service, or the default tier
        when the service is not found in the configured mapping.

        Args:
            service: The service name to look up.

        Returns:
            The ServiceTier for the service.
        """
        from sre_agent.domain.models.diagnosis import ServiceTier  # local to avoid circular
        raw = self._service_tiers.get(service, self._default_tier)
        # _service_tiers values are already ServiceTier instances
        return raw
