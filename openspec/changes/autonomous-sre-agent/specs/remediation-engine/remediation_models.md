# Remediation Engine — Domain Model Specification

**Status:** APPROVED  
**Version:** 1.0.0  
**Last Updated:** 2026-03-26  
**Traces To:** `remediation-engine/spec.md`, `data_model.md`, `canonical.py`

---

## 1. RemediationStrategy (Enum)

Defines the type of remediation action the engine can execute.

| Value | Description | Mapped AnomalyType(s) | Reversible |
|---|---|---|---|
| `RESTART` | Restart compute unit (pod, ECS task, App Service) | `MEMORY_PRESSURE` | ✅ Yes (self-healing) |
| `SCALE_UP` | Increase replica/instance count | `LATENCY_SPIKE`, `TRAFFIC_ANOMALY` | ✅ Yes (scale down after cooldown) |
| `SCALE_DOWN` | Decrease replica/instance count (throttle) | `INVOCATION_ERROR_SURGE` | ✅ Yes (restore concurrency) |
| `GITOPS_REVERT` | Create Git revert commit via ArgoCD | `DEPLOYMENT_INDUCED`, `ERROR_RATE_SURGE` | ✅ Yes (re-apply reverted commit) |
| `CONFIG_CHANGE` | Modify runtime configuration (HPA limits, resource requests) | `LATENCY_SPIKE` | ✅ Yes (restore prior config) |
| `CERTIFICATE_ROTATION` | Trigger cert renewal via cert-manager | `CERTIFICATE_EXPIRY` | ⚠️ Partial (new cert replaces old) |
| `LOG_TRUNCATION` | Truncate designated log paths on volume | `DISK_EXHAUSTION` | ❌ No (data loss — logged) |

```python
class RemediationStrategy(Enum):
    RESTART = "restart"
    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    GITOPS_REVERT = "gitops_revert"
    CONFIG_CHANGE = "config_change"
    CERTIFICATE_ROTATION = "certificate_rotation"
    LOG_TRUNCATION = "log_truncation"
```

---

## 2. RemediationPlan (Entity)

A concrete, sequenced plan linking a `Diagnosis` to one or more `RemediationAction`s.

| Field | Type | Description |
|---|---|---|
| `plan_id` | `UUID` | Unique identifier |
| `diagnosis_id` | `UUID` | FK → parent `Diagnosis` |
| `incident_id` | `UUID` | FK → parent incident aggregate |
| `strategy` | `RemediationStrategy` | Selected remediation approach |
| `target_resource` | `str` | Kubernetes resource URI, ARN, or Azure resource ID |
| `compute_mechanism` | `ComputeMechanism` | Target compute platform |
| `provider` | `str` | Cloud provider (`kubernetes`, `aws`, `azure`) |
| `approval_state` | `ApprovalState` | Current approval status |
| `safety_constraints` | `SafetyConstraints` | Blast radius, canary config, max replicas |
| `actions` | `list[RemediationAction]` | Ordered sequence of actions to execute |
| `created_at` | `datetime` | Plan creation timestamp |
| `approved_at` | `datetime | None` | When approval was granted (HITL or auto) |
| `approved_by` | `str` | `"autonomous"` or human identity |

```python
class ApprovalState(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"        # HITL approval timed out
```

---

## 3. RemediationAction (Entity — Enhanced)

Extends the `data_model.md` definition with execution context fields.

| Field | Type | Description |
|---|---|---|
| `id` | `UUID` | Unique identifier |
| `action_type` | `RemediationStrategy` | Action type (mirrors plan strategy) |
| `status` | `ActionStatus` | Lifecycle status |
| `target_resource` | `str` | Resource URI/ARN |
| `compute_mechanism` | `ComputeMechanism` | Target compute platform |
| `provider` | `str` | Cloud provider |
| `rollback_path` | `str` | How to reverse this action |
| `blast_radius_estimate` | `BlastRadiusEstimate` | Pre-execution impact estimate |
| `batch_index` | `int` | Which canary batch (0 = canary, 1+ = rollout) |
| `executed_at` | `datetime | None` | When execution started |
| `verified_at` | `datetime | None` | When post-action verification completed |
| `rollback_executed_at` | `datetime | None` | When rollback was triggered (if applicable) |
| `execution_duration_ms` | `int | None` | Execution wall-clock time in milliseconds |
| `lock_fencing_token` | `int | None` | Distributed lock fencing token at execution time |

```python
class ActionStatus(Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    CANCELLED = "cancelled"      # Kill switch or preemption
```

---

## 4. RemediationResult (Value Object)

Captures the outcome of a remediation action execution.

| Field | Type | Description |
|---|---|---|
| `success` | `bool` | Whether the action achieved its goal |
| `metrics_before` | `dict[str, float]` | Key metric snapshots before action |
| `metrics_after` | `dict[str, float]` | Key metric snapshots after verification |
| `verification_status` | `VerificationStatus` | Post-action verification outcome |
| `rollback_triggered` | `bool` | Whether auto-rollback was invoked |
| `error_message` | `str | None` | Error details if action failed |
| `execution_duration_ms` | `int` | Total execution time |

```python
class VerificationStatus(Enum):
    PENDING = "pending"
    METRICS_NORMALIZED = "metrics_normalized"
    METRICS_DEGRADED = "metrics_degraded"
    VERIFICATION_TIMEOUT = "verification_timeout"
    SKIPPED = "skipped"           # Manual resolution
```

---

## 5. SafetyConstraints (Value Object)

Pre-computed safety boundaries for a remediation plan.

| Field | Type | Description |
|---|---|---|
| `max_blast_radius_percentage` | `float` | Max % of fleet affected (default: 20.0) |
| `canary_percentage` | `float` | % of targets in canary batch (default: 5.0) |
| `canary_validation_window_seconds` | `int` | Time to wait for canary health (default: 60) |
| `max_replicas` | `int | None` | Cap on scaling actions |
| `cooldown_ttl_seconds` | `int` | Post-action cooldown (default: 900) |
| `requires_human_approval` | `bool` | Whether HITL gate is required |

---

## 6. BlastRadiusEstimate (Value Object)

Pre-execution analysis of the action's potential impact scope.

| Field | Type | Description |
|---|---|---|
| `affected_pods_count` | `int` | Number of pods/units directly affected |
| `affected_pods_percentage` | `float` | As % of total deployment replicas |
| `dependent_services` | `list[str]` | Downstream services from dependency graph |
| `estimated_user_impact` | `float` | Estimated user impact score [0.0, 1.0] |

---

## 7. EventTypes — Remediation Phase Constants

To be added to `canonical.py` `EventTypes` class:

```python
class EventTypes:
    # ... existing Phase 1 & 2 events ...

    # Phase 2 — Remediation layer
    REMEDIATION_PLANNED = "remediation.planned"
    REMEDIATION_APPROVED = "remediation.approved"
    REMEDIATION_STARTED = "remediation.started"
    REMEDIATION_COMPLETED = "remediation.completed"
    REMEDIATION_FAILED = "remediation.failed"
    REMEDIATION_ROLLED_BACK = "remediation.rolled_back"

    # Phase 2 — Safety layer
    KILL_SWITCH_ACTIVATED = "kill_switch.activated"
    KILL_SWITCH_DEACTIVATED = "kill_switch.deactivated"
    BLAST_RADIUS_EXCEEDED = "blast_radius.exceeded"
    COOLDOWN_ENFORCED = "cooldown.enforced"
    PHASE_GATE_EVALUATED = "phase_gate.evaluated"
```

---

## 8. Strategy Selection Matrix

| AnomalyType | Root Cause Pattern | Strategy | Severity Routing |
|---|---|---|---|
| `MEMORY_PRESSURE` | OOM kill, memory leak | `RESTART` | Sev 3-4: auto, Sev 1-2: HITL |
| `LATENCY_SPIKE` | Traffic saturation | `SCALE_UP` | Sev 3-4: auto, Sev 1-2: HITL |
| `TRAFFIC_ANOMALY` | Traffic saturation | `SCALE_UP` | Sev 3-4: auto, Sev 1-2: HITL |
| `ERROR_RATE_SURGE` | Deployment regression | `GITOPS_REVERT` | Sev 3-4: auto, Sev 1-2: HITL (PR) |
| `DEPLOYMENT_INDUCED` | Bad deploy | `GITOPS_REVERT` | Sev 3-4: auto, Sev 1-2: HITL (PR) |
| `CERTIFICATE_EXPIRY` | Cert approaching expiry | `CERTIFICATE_ROTATION` | Always: auto |
| `DISK_EXHAUSTION` | Log file growth | `LOG_TRUNCATION` | Sev 3-4: auto, Sev 1-2: HITL |
| `INVOCATION_ERROR_SURGE` | Serverless error storm | `SCALE_DOWN` | Sev 3-4: auto, Sev 1-2: HITL |
