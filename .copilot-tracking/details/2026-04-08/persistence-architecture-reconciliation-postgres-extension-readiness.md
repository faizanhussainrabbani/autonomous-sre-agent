<!-- markdownlint-disable-file -->
# Readiness Plan: PostgreSQL Extension Compatibility

## Objective

Define objective validation criteria for TimescaleDB and pgvector support across target deployment environments before persistence implementation starts.

## Decision Constraints

* C-02 is binding: pgvector is production standard, Chroma remains development-only.
* WI-01 is a P0 gate: no migration phase may begin until readiness checks pass in staging and production.

## Minimum Version Requirements

| Extension | Minimum Version | Why It Matters |
|---|---|---|
| TimescaleDB | 2.13.0 | Stable continuous-aggregate and compression behavior used by persistence design |
| pgvector | 0.5.0 | Required for production-grade HNSW indexing and expected query performance |

## Target Environments

* Local development containerized PostgreSQL
* Staging managed PostgreSQL
* Production managed PostgreSQL

## Validation Matrix

| Environment | Owner | Target Date | TimescaleDB Install | pgvector Install | Backup/Restore Verified | Pass/Fail |
|---|---|---|---|---|---|---|
| Local | Platform Engineering | 2026-04-12 | pending | pending | pending | pending |
| Staging | Platform Engineering | 2026-04-15 | pending | pending | pending | pending |
| Production | Platform Engineering | 2026-04-18 | pending | pending | pending | pending |

## Required Checks

* Extension availability check:
  * SELECT extname FROM pg_extension WHERE extname IN ('timescaledb', 'vector');
* Permission and version check:
  * SELECT extname, extversion FROM pg_extension WHERE extname IN ('timescaledb', 'vector');
* Version gate check:
  * Confirm timescaledb extversion >= 2.13.0
  * Confirm vector extversion >= 0.5.0
* Table and index compatibility check for vector and hypertable schemas.
* Backup and restore trial with extension-backed objects.

## Backup and Restore Procedure

1. Create readiness test objects:
   * one hypertable-like metrics table with TimescaleDB policy objects
   * one pgvector-backed embeddings table with HNSW index
2. Run backup in target environment using platform-standard backup mechanism.
3. Restore into an isolated verification instance.
4. Validate restored objects:
   * extension catalog entries exist
   * test tables and indexes exist
   * sample query on vector index succeeds
   * sample aggregate query succeeds
5. Record evidence links and execution timestamps in this document.

## Exit Criteria

* All target environments show both extensions available and usable.
* Backup and restore validation passes for extension-backed tables and indexes.
* Staging and production pass minimum version gates.
* Risks and fallback options are documented for any environment failing checks.

## Fallback Strategy

* Local development only:
  * If pgvector unavailable locally, Chroma may be used for non-production developer workflows.
* Staging and production:
  * If pgvector or TimescaleDB is unavailable or below minimum version, mark readiness as failed and block migration rollout.
* If TimescaleDB fails in managed platform evaluation:
  * Pause migration and execute platform remediation or architecture exception review.
* Re-run readiness checks after platform changes.
