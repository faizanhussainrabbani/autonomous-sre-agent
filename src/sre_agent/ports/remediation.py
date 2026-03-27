"""Remediation Port — provider-agnostic remediation workflow interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from sre_agent.domain.models.canonical import AnomalyAlert
from sre_agent.domain.models.diagnosis import Diagnosis
from sre_agent.domain.remediation.models import (
    RemediationAction,
    RemediationPlan,
    RemediationResult,
    VerificationStatus,
)


class RemediationPort(ABC):
    """Abstract contract for remediation planning and execution."""

    @abstractmethod
    async def create_plan(self, diagnosis: Diagnosis, alert: AnomalyAlert) -> RemediationPlan:
        """Create an actionable remediation plan from diagnosis and alert context."""
        ...

    @abstractmethod
    async def execute_action(self, action: RemediationAction) -> RemediationResult:
        """Execute a remediation action against a target resource."""
        ...

    @abstractmethod
    async def verify_outcome(self, action: RemediationAction) -> VerificationStatus:
        """Verify post-action metrics to determine remediation effectiveness."""
        ...

    @abstractmethod
    async def rollback_action(self, action: RemediationAction) -> RemediationResult:
        """Attempt rollback for a previously executed remediation action."""
        ...
