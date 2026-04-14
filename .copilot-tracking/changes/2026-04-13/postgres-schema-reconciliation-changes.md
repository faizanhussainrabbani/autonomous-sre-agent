<!-- markdownlint-disable-file -->
# Changes Log: PostgreSQL Schema Reconciliation

## Related Plan
- `.copilot-tracking/plans/2026-04-13/postgres-schema-reconciliation-plan.instructions.md`

## Implementation Date
- 2026-04-13

## Summary
Implemented a comprehensive persistence reconciliation package across schema migration, runtime adapters, tests, benchmark tooling, and architecture docs.

## Added
- `src/sre_agent/adapters/persistence/migrations/005_postgres_schema_reconciliation.sql`
- `scripts/bench/pgvector_recall.py`
- `.copilot-tracking/research/2026-04-13/postgres-schema-reconciliation-research.md`
- `.copilot-tracking/plans/2026-04-13/postgres-schema-reconciliation-plan.instructions.md`
- `.copilot-tracking/details/2026-04-13/postgres-schema-reconciliation-details.md`
- `.copilot-tracking/plans/logs/2026-04-13/postgres-schema-reconciliation-log.md`

## Modified
- `src/sre_agent/ports/persistence.py`
- `src/sre_agent/adapters/persistence/postgres_outbox.py`
- `src/sre_agent/adapters/persistence/outbox_relay.py`
- `src/sre_agent/adapters/vectordb/pgvector/adapter.py`
- `tests/unit/adapters/persistence/test_postgres_outbox.py`
- `tests/unit/adapters/persistence/test_outbox_relay.py`
- `tests/unit/adapters/vectordb/test_pgvector_adapter.py`
- `docs/architecture/persistence_architecture.md`

## Removed
- None

## Additional / Deviations
- `coordination_audit` partition conversion in migration 005 uses unique constraint names (`coordination_audit_partitioned_pkey`, etc.) to avoid name collisions during table swap.
- JSONB-only environments (without pgvector extension installed) enforce fallback safety and dimension checks, but full dual-column exclusivity is applied when vector column exists.

## Validation Summary
- Targeted unit tests:
  - `tests/unit/adapters/persistence/test_postgres_outbox.py`
  - `tests/unit/adapters/persistence/test_outbox_relay.py`
  - `tests/unit/adapters/vectordb/test_pgvector_adapter.py`
  - Result: `65 passed`
- Lint checks (`ruff`) on all changed Python files: passed.
- Migration dry-run in transaction against local PostgreSQL: passed after constraint-name fix.

## Release Summary
- P0 schema and reliability recommendations implemented via migration and adapter updates.
- P1 Timescale policy and coordination partitioning implemented conditionally and idempotently.
- ADR-006 latency gate now executable through `scripts/bench/pgvector_recall.py`.
- Persistence architecture naming drift reconciled to shipped schema names.
