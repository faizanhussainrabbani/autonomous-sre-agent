"""Remediation domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from sre_agent.domain.models.canonical import ComputeMechanism


class RemediationStrategy(Enum):
    RESTART = "restart"
    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    GITOPS_REVERT = "gitops_revert"
    CONFIG_CHANGE = "config_change"
    CERTIFICATE_ROTATION = "certificate_rotation"
    LOG_TRUNCATION = "log_truncation"


class ApprovalState(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ActionStatus(Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    CANCELLED = "cancelled"


class VerificationStatus(Enum):
    PENDING = "pending"
    METRICS_NORMALIZED = "metrics_normalized"
    METRICS_DEGRADED = "metrics_degraded"
    VERIFICATION_TIMEOUT = "verification_timeout"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class SafetyConstraints:
    max_blast_radius_percentage: float = 20.0
    canary_percentage: float = 5.0
    canary_validation_window_seconds: int = 60
    max_replicas: int | None = None
    cooldown_ttl_seconds: int = 900
    requires_human_approval: bool = True


@dataclass(frozen=True)
class BlastRadiusEstimate:
    affected_pods_count: int = 0
    affected_pods_percentage: float = 0.0
    dependent_services: list[str] = field(default_factory=list)
    estimated_user_impact: float = 0.0


@dataclass
class RemediationAction:
    id: UUID = field(default_factory=uuid4)
    action_type: RemediationStrategy = RemediationStrategy.RESTART
    status: ActionStatus = ActionStatus.PROPOSED
    target_resource: str = ""
    compute_mechanism: ComputeMechanism = ComputeMechanism.KUBERNETES
    provider: str = "kubernetes"
    rollback_path: str = ""
    blast_radius_estimate: BlastRadiusEstimate = field(default_factory=BlastRadiusEstimate)
    batch_index: int = 0
    total_targets: int = 1
    desired_count: int | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    executed_at: datetime | None = None
    verified_at: datetime | None = None
    rollback_executed_at: datetime | None = None
    execution_duration_ms: int | None = None
    lock_fencing_token: int | None = None


@dataclass
class RemediationPlan:
    plan_id: UUID = field(default_factory=uuid4)
    diagnosis_id: UUID | None = None
    incident_id: UUID | None = None
    strategy: RemediationStrategy = RemediationStrategy.RESTART
    target_resource: str = ""
    compute_mechanism: ComputeMechanism = ComputeMechanism.KUBERNETES
    provider: str = "kubernetes"
    approval_state: ApprovalState = ApprovalState.PENDING
    safety_constraints: SafetyConstraints = field(default_factory=SafetyConstraints)
    blast_radius_estimate: BlastRadiusEstimate = field(default_factory=BlastRadiusEstimate)
    actions: list[RemediationAction] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    approved_at: datetime | None = None
    approved_by: str = ""


@dataclass(frozen=True)
class RemediationResult:
    success: bool
    metrics_before: dict[str, float] = field(default_factory=dict)
    metrics_after: dict[str, float] = field(default_factory=dict)
    verification_status: VerificationStatus = VerificationStatus.PENDING
    rollback_triggered: bool = False
    error_message: str | None = None
    execution_duration_ms: int = 0
