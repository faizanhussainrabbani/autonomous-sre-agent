<!-- markdownlint-disable-file -->
# Rollback Strategy: Persistence Architecture Reconciliation Migration

## Purpose

Define deterministic rollback behavior for each migration phase so deployment can be reversed without loss of incident continuity or auditability.

## Rollback Triggers

* Any critical production incident caused by migration change set.
* Any data-integrity failure in incident projection parity checks.
* Outbox backlog sustained > 100,000 rows for 10 minutes with failed relay recovery.
* Lock/cooldown correctness failure that violates AGENTS coordination guarantees.
* Plan Validator or implementation validator critical finding discovered post-deploy.

## Rollback Control Plane

* Feature flags:
  * PERSISTENCE_POSTGRES_EVENT_STORE_ENABLED
  * PERSISTENCE_REDIS_STREAM_BUS_ENABLED
  * PERSISTENCE_REDIS_DIAGCACHE_ENABLED
  * PERSISTENCE_PGVECTOR_ENABLED
  * PERSISTENCE_TIMESCALE_BASELINE_ENABLED
* Operational controls:
  * Human override and global kill-switch remain authoritative during rollback.
* Change freeze:
  * No schema-destructive migration is permitted in a rollback window.

## Phase Rollback Matrix

| Phase | Forward Change | Rollback Action | Data Safety Notes |
|---|---|---|---|
| Phase 1 | Event store + outbox writes enabled | Disable POSTGRES_EVENT_STORE flag; re-enable in-memory event store path; keep tables for replay | Do not drop incident_events/outbox tables |
| Phase 2 | Incident/diagnosis/remediation persistence enabled | Disable persistence read/write flags for affected adapters and route API reads to previous in-memory path where applicable | Preserve inserted rows for forensic analysis |
| Phase 3 | Agent reasoning trace persistence enabled | Disable agent-run persistence writes while keeping core incident persistence active | Retain trace data for audit |
| Phase 4 | Redis DiagnosticCache enabled | Disable REDIS_DIAGCACHE flag and fall back to process-local cache | No destructive data operation needed |
| Phase 5 | pgvector enabled for production retrieval | Disable PGVECTOR flag; revert to previously approved non-production fallback only in local/staging; production rollback requires release halt | No production Chroma fallback allowed |
| Phase 6 | TimescaleDB baseline persistence enabled | Disable TIMESCALE_BASELINE flag and route baseline query to previous logic path for emergency continuity | Keep hypertable data for replay |

## Data Rollback and Recovery Rules

* Schema rollback:
  * Avoid immediate down migrations during incident response unless data corruption requires it.
  * Prefer application-level rollback via feature flags first.
* Projection recovery:
  * Rebuild incidents projection from incident_events if projection parity is lost.
* Event delivery recovery:
  * Resume outbox relay from pending rows; do not delete pending or failed rows before root-cause review.
* Audit preservation:
  * Never truncate audit or incident event history during rollback.

## Verification Checklist After Rollback

* API health endpoints are stable and error rate returns to baseline.
* Incident write path remains available.
* Lock/cooldown semantics match AGENTS policy.
* Outbox pending growth is bounded and visible.
* Post-rollback status and evidence logged in operational report.

## Ownership

* Primary owner: Platform Reliability Team
* Approver: Incident Commander on duty
* Audit reviewer: Architecture Working Group
