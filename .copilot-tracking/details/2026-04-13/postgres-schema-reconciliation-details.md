<!-- markdownlint-disable-file -->
# Implementation Details: PostgreSQL Schema Reconciliation

## Context References
- Plan: `.copilot-tracking/plans/2026-04-13/postgres-schema-reconciliation-plan.instructions.md`
- Research: `.copilot-tracking/research/2026-04-13/postgres-schema-reconciliation-research.md`
- Review input: `docs/architecture/reviews/postgres_schema_review_2026-04-13.md`

## Phase A: Migration 005 DDL
1. Create idempotent migration file under persistence migrations.
2. Implement outbox hardening (unique event_id, DLQ fields, status set).
3. Add consumer dedup table (`processed_events`).
4. Normalize vector table to dual columns + checks and rebuild tuned HNSW.
5. Apply Timescale chunk/compression/retention if extension is available.
6. Migrate coordination audit into monthly range partitions and add BRIN index.

## Phase B: Adapter and Port Updates
1. pgvector adapter:
   - use unified schema writes,
   - set local ef_search in pgvector search,
   - cap JSONB fallback rows to 10k.
2. Outbox port + postgres implementation:
   - support processed-event checks/marks,
   - support DLQ transition.
3. Relay:
   - skip publishing already processed events for the configured consumer,
   - mark processed after successful publish and sent transition,
   - use DLQ transition when max retries reached.

## Phase C: Tests and Harness
1. Update fake outbox and unit tests for new methods.
2. Add pgvector adapter tests for ef_search and JSONB cap.
3. Add benchmark script for ADR-006 p95 executable gate.

## Phase D: Docs
1. Replace legacy names in persistence architecture doc with shipped canonical names.

## Phase E: Validation
1. Execute targeted unit tests for outbox and pgvector adapters.
2. Run a lint check for changed files if available.
3. Address regressions and rerun.
