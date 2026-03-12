# Phase 1: Data Foundation — Overview

**Duration:** ~3 months | **Work Streams:** 3 | **Tasks:** 19 | **Spec Scenarios to Pass:** 35

---

## Scope

Phase 1 builds the data pipeline that every later phase depends on. At the end of this phase, the system can **detect incidents, correlate signals, and produce well-structured alerts** — without any human intervention on the detection side.

### What's IN Scope

| Work Stream | Tasks | Deliverable |
|---|---|---|
| Provider Abstraction Layer | 13.1–13.8 | Canonical data model + OTel/New Relic adapters |
| Telemetry Ingestion Pipeline | 1.1–1.6 | Signal collection, correlation, dependency graph |
| Anomaly Detection Engine | 2.1–2.5 | ML-based detection on live metrics |

### What's NOT in Scope

| Capability | Phase |
|---|---|
| Root cause diagnosis (RAG) | Phase 2 |
| Severity classification | Phase 2 |
| Remediation actions | Phase 3 |
| Safety guardrails | Phase 3 |
| Notifications | Phase 5 |
| Operator dashboard | Phase 5 |

## Phase Completion Definition

Phase 1 is **complete** when:
1. All 19 tasks are marked done in `tasks.md`
2. All 35 spec scenarios pass in `acceptance_criteria.md`
3. System runs 7 consecutive days in shadow mode with zero crashes or data loss
4. Dependency graph validated by team as matching actual service topology

## Files

- [acceptance_criteria.md](./acceptance_criteria.md) — Testable checklist linked to spec scenarios
- [overview.md](./overview.md) — This file
