<!-- markdownlint-disable-file -->
# PostgreSQL Schema Reconciliation Research (2026-04-13)

## Scope
- Implement comprehensive recommendations from [docs/architecture/reviews/postgres_schema_review_2026-04-13.md](docs/architecture/reviews/postgres_schema_review_2026-04-13.md).
- Reconcile migrations 001-004 with ADR-006 and persistence architecture guarantees.

## Explicit User Requests
1. Create migration 005 for HNSW tuning and dual-mode vector schema enforcement.
2. Add processed-events reliability model and DLQ-capable outbox updates.
3. Update pgvector adapter + outbox/relay runtime behavior.
4. Configure Timescale chunk/compression/retention and coordination partitioning + BRIN.
5. Resolve naming drift in persistence architecture documentation.
6. Add benchmark harness for p95 < 250ms gate at 1M rows.

## Evidence Log
- Current vector schema is bifurcated by extension check in migration 002; adapter probes extension and assumes matching shape.
- HNSW index currently uses defaults (no WITH tuning params).
- Outbox currently has statuses pending/processing/sent/failed and no DLQ columns.
- No `processed_events` table exists.
- Outbox claim path already uses `UPDATE ... WHERE ... FOR UPDATE SKIP LOCKED RETURNING` in `postgres_outbox.py`.
- `coordination_audit` is a plain table with btree indexes; no partitions or BRIN.
- Docs still reference legacy names such as `audit_log`, `metric_snapshots`, `vector_documents`, and `outbox`.

## Constraints and Compatibility Notes
- Existing data may already have `vector_embeddings` with either vector or jsonb column only.
- pgvector may be absent in some environments; migration must remain safe and idempotent.
- TimescaleDB may be absent; policies must be conditional.
- Existing tests rely on current OutboxPort shape and will need synchronized updates.

## Selected Approach
- Deliver a single idempotent migration 005 that:
  - normalizes schema shape for vector dual-mode,
  - tunes HNSW,
  - introduces outbox and consumer-idempotency durability updates,
  - applies Timescale and partitioning enhancements conditionally.
- Update adapters with backward-safe behavior where possible (explicit claims, DLQ transitions, fallback limits, and session-level ef_search).
- Update tests and add a benchmark script that can be run in CI/nightly environments with configurable DSN and scale.

## Alternatives Considered
- Splitting into multiple migrations:
  - rejected for this user request because it explicitly asks for a migration 005 containing the P0/P1 reconciliation package.
- Runtime-only enforcement without DDL constraints:
  - rejected because request targets schema reconciliation and invariant enforcement.

## Success Criteria
- Migration 005 is idempotent and applies cleanly on top of 001-004.
- Adapters compile and tests updated for changed interfaces/semantics.
- Benchmark harness exists and fails when p95 >= 250ms.
- Persistence architecture doc naming aligns with shipped canonical table names.
