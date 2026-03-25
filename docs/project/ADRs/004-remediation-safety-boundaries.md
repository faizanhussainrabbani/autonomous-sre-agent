---
title: ADR-004 Remediation Safety Boundaries
description: Decision record defining autonomous remediation limits, rollback obligations, and human override expectations.
ms.date: 2026-03-19
ms.topic: reference
author: SRE Agent Engineering Team
status: ACCEPTED
---

## Context

Autonomous remediation can reduce MTTR, but incorrect actions can increase outage severity. Safety boundaries are required to constrain blast radius and preserve human control.

## Decision

Adopt mandatory remediation boundary controls:

* Blast-radius constraints by resource type and environment
* Policy checks before action execution
* Kill-switch override with immediate automation backoff
* Post-action verification and rollback or recovery path requirements

## Consequences

### Positive

* Reduces probability of large-scale incorrect actions
* Improves operator trust and incident recoverability
* Enforces consistent safety gates across providers

### Negative

* Some valid remediations may be delayed by guardrail checks
* Requires continuous policy tuning to avoid false blocks

### Risks

* Overly strict policy can increase manual intervention load

## Alternatives considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Unrestricted autonomous actions | Fastest reaction | Unacceptable risk profile | Rejected |
| Fully manual remediation | Maximum operator control | Slower response and reduced automation value | Rejected |
| Guardrail-constrained autonomy | Balanced speed and safety | Needs governance upkeep | Selected |

## References

* [Permissions and RBAC](../../architecture/permissions-and-rbac.md)
* [Guardrails configuration](../../security/guardrails_configuration.md)
* [Kill switch runbook](../../operations/runbooks/kill_switch.md)
