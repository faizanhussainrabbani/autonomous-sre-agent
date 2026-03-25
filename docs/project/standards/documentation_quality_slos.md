---
title: Documentation Quality SLOs
description: Measurable documentation service-level objectives for link integrity, safety-review cadence, runbook completeness, and ADR traceability.
ms.date: 2026-03-19
ms.topic: reference
author: SRE Agent Engineering Team
status: APPROVED
---

## Objective

Define measurable quality expectations for documentation as a reliability dependency.

## SLO targets

| SLO | Target | Measurement |
|---|---|---|
| Internal link integrity | 0 broken internal links on default branch | Automated link validation on changed docs |
| Safety-critical review freshness | 100 percent reviewed within 30 days | Review date check for runbooks, guardrails, and permission docs |
| Runbook rollback completeness | 100 percent of runbooks include rollback or recovery path | Runbook checklist verification |
| Decision traceability | 100 percent of long-term architecture decisions mapped to ADR | Quarterly ADR coverage review |

## Safety-critical document set

Includes:

* `docs/operations/runbooks/`
* `docs/security/`
* `docs/architecture/permissions-and-rbac.md`
* `docs/architecture/multi-agent-coordination.md`

## Reporting cadence

* Monthly SLO summary in `docs/reports/`
* Quarterly policy and ADR traceability audit
