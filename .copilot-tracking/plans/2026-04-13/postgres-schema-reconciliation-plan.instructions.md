<!-- markdownlint-disable-file -->
# Implementation Plan: PostgreSQL Schema Reconciliation

## User Requests
1. Implement migration 005 with HNSW tuning, dual-mode vector unification, and embedding dimension invariant.
2. Add processed-events table, outbox event uniqueness, DLQ columns/state transitions.
3. Update vector adapter, Postgres event/outbox persistence behavior, and relay processing semantics.
4. Configure Timescale 1-day chunking, compression/retention policies, and partition coordination audit with BRIN.
5. Update persistence architecture docs to match canonical shipped names.
6. Add `scripts/bench/pgvector_recall.py` executable gate for ADR-006 p95 latency requirement.

## Overview
Deliver a complete persistence reconciliation package across DDL, adapters, tests, and docs while preserving existing contracts and idempotency behavior.

## Context Summary
- Primary architecture references:
  - AGENTS.md
  - CLAUDE.md
  - docs/architecture/persistence_architecture.md
  - docs/architecture/reviews/postgres_schema_review_2026-04-13.md
- No `.github/instructions` files were discovered in this repository.

## Dependencies
- asyncpg (adapter and benchmark interactions)
- PostgreSQL 16+
- Optional extensions: pgvector, timescaledb

## Checklist

### Phase A: Migration 005 DDL <!-- parallelizable: false -->
- [x] Create `005_postgres_schema_reconciliation.sql`.
- [x] Add `event_outbox` uniqueness + DLQ columns + status constraint update.
- [x] Add `processed_events` table with `(consumer, event_id)` primary key and FK.
- [x] Unify `vector_embeddings` shape and add exclusivity + dimension constraints.
- [x] Rebuild HNSW with `m=24`, `ef_construction=200` when pgvector available.
- [x] Apply Timescale chunk/compression/retention policies conditionally.
- [x] Partition `coordination_audit` monthly and add BRIN indexes on created_at.

### Phase B: Adapter and Port Updates <!-- parallelizable: false -->
- [x] Update pgvector adapter for unified schema and `SET LOCAL hnsw.ef_search=100`.
- [x] Add JSONB fallback safety cap (`LIMIT 10000`) + warning signal.
- [x] Update outbox store methods for DLQ transition API and processed-events operations.
- [x] Update relay logic to use new processed-events dedup flow and DLQ path.

### Phase C: Tests and Benchmark Harness <!-- parallelizable: true -->
- [x] Update impacted unit tests for outbox and pgvector behavior.
- [x] Add benchmark harness at `scripts/bench/pgvector_recall.py` with p95 assertion.
- [x] Add/adjust test helpers as required by new port methods.

### Phase D: Documentation Alignment <!-- parallelizable: true -->
- [x] Update naming drift in `docs/architecture/persistence_architecture.md` to canonical names.

### Phase E: Validation and Logs <!-- parallelizable: false -->
- [x] Run targeted unit tests for modified adapters.
- [x] Run lint/type checks where feasible.
- [x] Record results in changes log and review log.

## Success Criteria
- All explicit user requests are fulfilled with concrete code/docs changes.
- Targeted tests pass for modified components.
- Changes are documented in `.copilot-tracking` artifacts.
