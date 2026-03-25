---
title: Multi-Agent Coordination
description: Coordination model for SRE, SecOps, and FinOps agents including lock protocol, priority preemption, cooldown behavior, and conflict handling.
ms.date: 2026-03-19
ms.topic: reference
author: SRE Agent Engineering Team
status: APPROVED
---

## Canonical authority

`AGENTS.md` is the policy authority for multi-agent ecosystem definitions. This document is the architecture-facing operational reference that maps policy to implementation behavior.

## Agent roles and priorities

Priority order:

1. SecOps (priority 1, override)
2. SRE (priority 2)
3. FinOps (priority 3)

Policy behavior:

* Higher-priority lock requests can preempt lower-priority requests
* Lower-priority optimization actions are blocked during active SRE incidents
* Human operators can override all agent locks

## Lock protocol

Each lock request must include a structured payload with identity, resource scope, provider attributes, priority, TTL, and fencing token.

Required lock fields:

* `agent_id`
* `resource_type`
* `resource_name`
* `namespace` (empty for non-Kubernetes targets)
* `compute_mechanism`
* `resource_id`
* `provider`
* `priority_level`
* `acquired_at`
* `ttl_seconds`
* `fencing_token`

## Preemption rules

Preemption is deterministic by `priority_level`.

* If higher priority requests same resource, lock manager grants higher-priority lock
* Lock manager emits revocation event to lower-priority holder
* Revoked agent must abort in-progress action and queue retry based on policy

## Cooldown and anti-oscillation behavior

After action completion, agent writes cooldown key for the affected resource.

Cooldown effects:

* Blocks immediate repeated action on same resource
* Allows only higher-priority override while cooldown is active
* Reduces oscillation loops in scale and restart behaviors

## Fencing token and TTL behavior

Fencing token guarantees order safety.

* Each lock acquisition receives a monotonic token
* Action execution must carry lock token context
* Stale token operations are rejected by lock-aware executors
* TTL expiration invalidates lock ownership without relying on process liveness

## Conflict handling scenarios

### Scenario A: SRE versus FinOps

* SRE lock active for incident remediation
* FinOps downscale request arrives
* Lock manager denies FinOps request until incident lock and cooldown conditions allow action

### Scenario B: SecOps preemption

* SRE lock active for service recovery
* SecOps requests same resource for quarantine
* Lock manager preempts SRE, grants SecOps lock, and emits revocation

### Scenario C: Human override

* Human operator performs manual intervention
* Agent locks are suspended or superseded
* Autonomous operations back off until manual release policy restores agent control

## Related documents

* [AGENTS policy](../../AGENTS.md)
* [Orchestration layer](layers/orchestration_layer.md)
* [Incident response runbook](../operations/runbooks/incident_response.md)
