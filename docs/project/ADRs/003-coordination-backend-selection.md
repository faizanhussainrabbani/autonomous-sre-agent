---
title: ADR-003 Coordination Backend Selection
description: Decision record for distributed lock backend choice supporting multi-agent coordination and fencing semantics.
ms.date: 2026-03-19
ms.topic: reference
author: SRE Agent Engineering Team
status: ACCEPTED
---

## Context

The platform requires deterministic multi-agent lock behavior, preemption handling, cooldown enforcement, and fencing token support for stale-write protection.

## Decision

Adopt a distributed key-value coordination backend that supports TTL-based locks, pub/sub revocation signaling, and monotonic fencing token semantics.

Current operational preference remains Redis-compatible lock management with implementation compatibility for etcd-backed environments.

## Consequences

### Positive

* Deterministic lock ownership and preemption behavior
* Supports cooldown and lock-expiration safeguards
* Enables conflict-safe operation among SRE, SecOps, and FinOps agents

### Negative

* Additional operational dependency for coordination control plane
* Requires strict key schema governance across agents

### Risks

* Misconfigured TTL or token generation can produce false lock behavior

## Alternatives considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| In-process locking | Simple local behavior | No cross-agent safety | Rejected |
| Database row-level locking | Existing infra | Higher latency and complex preemption semantics | Rejected |
| Distributed lock backend with fencing | Deterministic, scalable, preemption-safe | Requires operational backend | Selected |

## References

* [Multi-agent coordination](../../architecture/multi-agent-coordination.md)
* [AGENTS policy](../../../AGENTS.md)
