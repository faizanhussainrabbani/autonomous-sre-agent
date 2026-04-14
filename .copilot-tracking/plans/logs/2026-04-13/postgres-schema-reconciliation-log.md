<!-- markdownlint-disable-file -->
# Planning Log: PostgreSQL Schema Reconciliation

## Selected Path
- Single migration 005 for major reconciliation package, with conditional extension-aware DDL and idempotent guards.
- Adapter updates aligned to new schema contract and reliability semantics.

## Alternatives Considered
- Split migration set by domain area (vector/outbox/timescale/partitioning): not selected due explicit request for migration 005 package.
- Relay-only dedup without schema table: not selected because schema-level consumer idempotency is a hard requirement.

## Potential Risks
- Existing data with malformed JSON vector dimensions could fail new dimension constraint validation.
- Timescale policy statements may fail if table is not hypertable in some environments.
- Partition conversion for `coordination_audit` requires careful data copy and atomic rename.

## Mitigations
- Use `NOT VALID` then `VALIDATE CONSTRAINT` only where safe; use conditional blocks and fallback notices.
- Guard Timescale operations with extension and hypertable checks.
- Perform partition migration inside transaction-safe rename/copy sequence.

## Implementation Deviations
- During migration dry-run, partition conversion failed due existing `coordination_audit_pkey` name collision.
- Resolved by renaming replacement-table constraints (`coordination_audit_partitioned_pkey`, etc.) in migration 005.

## Validation Iterations
- Iteration 1:
	- `pytest` targeted suites: passed (`65 passed`).
	- `ruff check` changed Python files: passed.
	- Migration 005 transactional dry-run: failed once due PK name collision.
- Iteration 2:
	- Applied migration fix.
	- Re-ran transactional dry-run: passed.
