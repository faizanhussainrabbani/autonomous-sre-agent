---
title: ADR-005 Multi-Agent Priority and Preemption
description: Decision record defining deterministic priority and preemption policy between SecOps, SRE, and FinOps agents.
ms.date: 2026-03-19
ms.topic: reference
author: SRE Agent Engineering Team
status: ACCEPTED
---

## Context

Multiple autonomous agents can issue conflicting actions on shared resources. A deterministic conflict policy is required to prevent unsafe oscillation and decision ambiguity.

## Decision

Adopt strict priority ordering and preemption policy:

* SecOps priority 1 (override)
* SRE priority 2
* FinOps priority 3

Conflict behavior is lock-manager enforced, with revocation events and retry behavior for preempted agents.

## Consequences

### Positive

* Deterministic conflict handling during concurrent incidents
* Reliability and security goals take precedence over optimization
* Enables safe autonomous coexistence across agent domains

### Negative

* Lower-priority optimization actions may be deferred during prolonged incidents
* Priority policy requires communication and governance alignment across teams

### Risks

* Misclassification of agent intent may route actions through incorrect priority behavior

## Alternatives considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Equal-priority agents | Simpler to describe | Non-deterministic conflict resolution | Rejected |
| Time-based tie-break only | Easy implementation | Ignores mission criticality | Rejected |
| Priority-based deterministic preemption | Safety-aware and deterministic | Requires policy maintenance | Selected |

## References

* [Multi-agent coordination](../../architecture/multi-agent-coordination.md)
* [AGENTS policy](../../../AGENTS.md)
