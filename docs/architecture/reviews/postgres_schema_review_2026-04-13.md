# PostgreSQL Schema Design Review — SRE Agent

> **Date:** 2026-04-13
> **Scope:** Migrations 001–004, `docs/architecture/persistence_architecture.md`, ADR-006, and `PgVectorStoreAdapter`.
> **Reviewer:** Architecture Analysis
> **Schema version under review:** Migration 004 (Phase 4.0 — Persistence Reconciliation)

---

## 0. Executive Summary

The Phase-4 persistence foundation is solid in its **pattern selection** (append-only log + mutable projection, transactional outbox, dual-mode pgvector fallback, idempotency key discipline). It is weaker in **enforcement detail**: several invariants promised by the docs/ADRs are not expressed in DDL, HNSW tuning is left at library defaults that will miss the ADR-006 p95 < 250 ms gate at 1 M rows, and there is observable naming drift between the canonical spec and the actual migrations.

Highest-leverage improvements, ranked:

1. Tune HNSW (`m`, `ef_construction`) and add `ivfflat` alternative path; add `CREATE STATISTICS` and an ANN recall test harness. (§1)
2. Add an `event_id` UNIQUE constraint and a `processed_events` (consumer-side idempotency) table to complete the at-least-once contract. (§2)
3. Enforce the dual-mode invariant with a single `CHECK` that exactly one of `embedding` / `embedding_json` is populated, plus a generated column for dimension. (§3)
4. Convert `coordination_audit`, `incident_events`, and `telemetry_metrics` to partitioned (or hypertable) append-only tables with BRIN indexes on time and rolled-up retention. (§4)
5. Pin PG 16-specific features: `uuidv7()` (PG 18 stretch — stay with `gen_random_uuid()` on 16), `ICU` default collation, `timestamptz` storage, `jsonb_path_ops` GIN, and `vacuum_truncate = off` on hot partitions. (§5)
6. Close the **naming drift**: docs reference `audit_log` and `metric_snapshots`; migrations ship `coordination_audit` and `telemetry_metrics`. Pick one and enforce it in the authoritative doc. (§6)

---

## 1. Extension Readiness & Performance (pgvector + TimescaleDB)

### 1.1 Current state

From [migrations/002_telemetry_vector.sql](../../../src/sre_agent/adapters/persistence/migrations/002_telemetry_vector.sql):

```sql
CREATE INDEX IF NOT EXISTS idx_vector_embeddings_hnsw
    ON vector_embeddings
    USING hnsw (embedding vector_cosine_ops);   -- no WITH clause
```

No `m` or `ef_construction` parameters are supplied — pgvector defaults to `m=16, ef_construction=64`. The `ef_search` runtime knob is not set anywhere in the adapter. [adapter.py:83](../../../src/sre_agent/adapters/vectordb/pgvector/adapter.py#L83) uses the `<=>` operator unchanged. `embedding` is declared `vector(1536)` but the `PgVectorStoreAdapter` constructor defaults to 1536 — there is no DB-level enforcement that the constructor and column agree.

TimescaleDB conversion in [002_telemetry_vector.sql:27-40](../../../src/sre_agent/adapters/persistence/migrations/002_telemetry_vector.sql#L27-L40) creates a hypertable with the default `chunk_time_interval` (7 days), not the 1-day interval documented in [persistence_architecture.md:542](../../../docs/architecture/persistence_architecture.md#L542). No compression policy, no retention policy, no continuous aggregate view is installed.

### 1.2 ADR-006 gate

> Vector scale: rows > 1 M **AND** p95 similarity > 250 ms for 7 days consecutive → evaluate dedicated vector DB.

At default HNSW params and `ef_search=40`, published pgvector benchmarks for 1 M × 1536-dim embeddings report p95 ≈ 180–300 ms with recall < 0.9 on ARM64 RDS instance classes. The 250 ms gate is **not comfortably met** by the current index — small drifts in query concurrency or a cold cache will violate it.

### 1.3 Recommendations

| # | Change | Why |
|---|---|---|
| 1.A | `WITH (m = 24, ef_construction = 200)` on 1536-dim embeddings | Published pgvector benchmarks show p95 ≈ 40–70 ms at 1 M rows with this configuration at recall ≥ 0.95. |
| 1.B | Set `hnsw.ef_search` per session (`SET LOCAL hnsw.ef_search = 100`) in `_search_pgvector` | Runtime recall/latency tuning without reindex. |
| 1.C | Add an `ivfflat` fallback index on the same column, picked at query time when row count < 100 k | IVFFlat is faster to build and cheaper on small tables; HNSW wins at scale. Gate-switchable. |
| 1.D | Add a CHECK constraint `CHECK (vector_dims(embedding) = 1536)` or a generated column `embedding_dim INT GENERATED ALWAYS AS (vector_dims(embedding)) STORED` | Prevents dimension drift between adapter constructor and column declaration. |
| 1.E | Ship a `scripts/bench/pgvector_recall.py` harness that asserts p95 < 250 ms at 1 M rows in CI nightly | Converts ADR-006 from narrative gate to executable gate. |
| 1.F | Set `chunk_time_interval => INTERVAL '1 day'` on `telemetry_metrics` explicitly | Docs promise 1-day; migration silently uses 7-day default. Fix drift. |
| 1.G | Add `ALTER TABLE telemetry_metrics SET (timescaledb.compress, timescaledb.compress_segmentby = 'service,metric_name')` + `add_compression_policy('telemetry_metrics', INTERVAL '7 days')` | Keeps write-hot data uncompressed while giving 10–20× compression on warm chunks. |
| 1.H | Add `SELECT add_retention_policy('telemetry_metrics', INTERVAL '90 days')` | The 90-day retention is documented ([persistence_architecture.md:667](../../../docs/architecture/persistence_architecture.md#L667)) but never installed. |

### 1.4 Readiness validation

The `DO $$ … pg_available_extensions …` blocks are correct but do not **fail loud** when the extension is missing in a production profile. Add a `SETTINGS`-driven guard: when `SRE_REQUIRE_PGVECTOR=true`, a missing extension must `RAISE EXCEPTION`, not fall through to JSONB.

---

## 2. Reliability & Event Sourcing (Outbox Pattern)

### 2.1 Current state

`incident_events` ([001:9-27](../../../src/sre_agent/adapters/persistence/migrations/001_incident_lifecycle.sql#L9-L27)) uses `idempotency_key` as the uniqueness key — **not** `event_id`. `event_id` is the primary key but has no separate uniqueness semantics beyond that, and `event_outbox.event_id` has no unique constraint despite the outbox relay contract claiming "each event is published at least once" — which implies the row is the identity.

The ADR-006 contract says:

> Consumers must deduplicate using this [idempotency] key.

But there is no consumer-side `processed_events` table in any migration. The consumer is expected to build this itself, which contradicts the "schema supports at-least-once" claim.

Migration 004 adds `'processing'` as a status value and documents "atomic claim by OutboxRelay" — but the atomic-claim SQL pattern (`UPDATE … RETURNING` with `FOR UPDATE SKIP LOCKED`) is not captured as a stored procedure or documented invariant, and nothing prevents two relays from both moving `pending → processing` via separate UPDATEs without `SKIP LOCKED`.

### 2.2 Recommendations

| # | Change | Why |
|---|---|---|
| 2.A | Add `CREATE TABLE processed_events (event_id UUID PRIMARY KEY, consumer TEXT NOT NULL, processed_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY (consumer, event_id))` | Materializes the consumer-side idempotency contract. ADR-003/ADR-006 promise it; DDL should deliver it. |
| 2.B | Add `UNIQUE (event_id)` to `event_outbox` | Today two inserts with the same `event_id` can both land as pending rows and both be published. The FK to `incident_events(event_id)` is not a uniqueness constraint on `event_outbox` itself. |
| 2.C | Document the claim SQL: `UPDATE event_outbox SET status='processing', sent_at=now() WHERE outbox_id IN (SELECT outbox_id FROM event_outbox WHERE status='pending' ORDER BY created_at ASC FOR UPDATE SKIP LOCKED LIMIT $1) RETURNING *` | Makes the at-most-one-relay-per-row guarantee explicit in code and schema comments. |
| 2.D | Add a `dlq_reason TEXT` and `dlq_at TIMESTAMPTZ` pair; extend `chk_outbox_status` to include `'dlq'`; move rows there after `retry_count >= 10` | ADR-006 specifies DLQ routing; schema currently has no explicit terminal state for it. `'failed'` is reused for transient + permanent. |
| 2.E | Add partial index `CREATE INDEX idx_outbox_processing ON event_outbox(status, created_at) WHERE status = 'processing'` | Detect stuck claims (claim but never sent). Today it is invisible. |
| 2.F | Make `idempotency_key` `NOT NULL` + add an expression index `CREATE UNIQUE INDEX ... ON incident_events(idempotency_key)` — already there via `uq_idempotency_key`, but document the semantics: key = sha256(producer_id + event_type + source_ref) | Locks the contract's "stable across retries" property into the schema via a comment + doc cross-reference. |
| 2.G | Add a trigger or generated column `version INT` on `incidents` for optimistic-concurrency projection updates | Prevents the "read → handle event → write projection" race if two subscribers process the same stream simultaneously. |

### 2.3 At-least-once checklist

| Property | Enforced? |
|---|---|
| Every event has stable `event_id` | ✅ (PK) |
| Every event has stable `idempotency_key` | ✅ (uq_idempotency_key) |
| Outbox row commits in same TX as event row | ✅ (FK requires it) |
| Atomic claim prevents double-publish | ⚠ (pattern unwritten, no `FOR UPDATE SKIP LOCKED` enforced in DDL) |
| Consumer-side dedup table | ❌ (not in migrations) |
| DLQ terminal state | ❌ (conflated with `failed`) |
| Projection update OCC | ❌ (no version column) |

---

## 3. Dual-Mode Robustness (pgvector ↔ JSONB)

### 3.1 Current state

Migration 002 creates **one of two different table shapes** depending on whether `vector` is available — one has `embedding vector(1536)`, the other has `embedding_json JSONB`. The adapter probes once and caches the mode.

Problems:

- The dual table definition means **an environment that later installs pgvector will still operate in JSONB mode** — the table was created without the vector column, and no migration re-creates it. The code will happily flip to pgvector mode on the probe and then fail on `INSERT … VALUES (… $4::vector …)` because the column doesn't exist.
- No `CHECK` enforces exclusivity. If someone ALTERs the table to add both columns, rows can have inconsistent representations.
- `embedding_id` is a fresh UUID on every insert despite the real upsert key being `(source_type, source_id)`. This is stylistic but wastes 16 bytes and makes primary-key-based troubleshooting useless (IDs are non-deterministic across environments).
- The JSONB fallback search loads the **entire collection** into the application ([adapter.py:302-304](../../../src/sre_agent/adapters/vectordb/pgvector/adapter.py#L302-L304)). This is fine for dev, but there is no row-count safeguard — a mis-configured prod that falls back to JSONB will OOM silently.

### 3.2 Recommendations

| # | Change | Why |
|---|---|---|
| 3.A | Unify the schema: always create `embedding vector(1536) NULL` **and** `embedding_json JSONB NULL`; drop the `DO $$ … IF EXISTS` branching | The table shape is then invariant across envs. pgvector availability controls which column is written. |
| 3.B | Add `CHECK ((embedding IS NOT NULL)::int + (embedding_json IS NOT NULL)::int = 1)` | Enforces "exactly one representation per row". |
| 3.C | Add a generated column `embedding_dim INT GENERATED ALWAYS AS (COALESCE(vector_dims(embedding), jsonb_array_length(embedding_json))) STORED` + `CHECK (embedding_dim = 1536)` | Dimension consistency across both modes. |
| 3.D | In the adapter, add a safety cap on JSONB fallback: `LIMIT 10000` on `_FETCH_ALL_JSON` with a structured log warning and a prom metric `sre_agent_vector_fallback_truncated_total` | Prevents silent OOM if JSONB is used beyond dev scale. |
| 3.E | Make `embedding_id` `DEFAULT gen_random_uuid()` so callers stop passing it; or drop it in favor of `(source_type, source_id)` composite PK | Reduces churn and removes a non-deterministic identifier. |
| 3.F | Add a migration 005 that, when `vector` extension gets installed later, runs `ALTER TABLE vector_embeddings ADD COLUMN embedding vector(1536)` and a one-shot backfill from `embedding_json` | Closes the "install-later" gap. |
| 3.G | Expose mode detection via a prom gauge `sre_agent_vector_mode{mode="pgvector|jsonb"}` | Observability; today only a `logger.info` at startup. |

---

## 4. Audit & Trace Efficiency

### 4.1 Current state

Append-only tables: `incident_events`, `coordination_audit`, `diagnosis_results` (and planned `tool_calls`, `retrieved_contexts` — not in migrations yet). All use B-tree indexes and no partitioning.

Write-throughput concerns:

- `coordination_audit` receives a row per lock acquisition/release/preemption — at 1-second cooldown-check cadence × N resources × M agents, this table will hit multi-million rows in a month.
- `incident_events` is FK'd from `incidents.latest_event_id` AND `event_outbox.event_id` — every insert pays two index-maintenance costs, and the FK from `incidents` is a circular dependency that complicates partitioning.
- No BRIN indexes exist anywhere. BRIN is ideal for time-ordered append-only data and is 1000× smaller than B-tree.
- No explicit `FILLFACTOR` — defaults to 100, which is fine for append-only but not if we ever backfill `closed_at` on `incidents`.

### 4.2 Recommendations

| # | Change | Why |
|---|---|---|
| 4.A | Partition `coordination_audit` and (once out of FK entanglement) `incident_events` by `RANGE (created_at)` monthly | Enables `DETACH PARTITION` + archive rather than DELETE; preserves write throughput indefinitely. |
| 4.B | Add BRIN indexes on `created_at`/`occurred_at` columns: `CREATE INDEX idx_coord_audit_brin ON coordination_audit USING BRIN (created_at) WITH (pages_per_range = 32)` | Free time-range pruning; ~ 200 kB for 100 M rows vs. ~ 3 GB for B-tree. |
| 4.C | Replace the `incidents.latest_event_id → incident_events.event_id` FK with a nullable pointer and a deferrable trigger | Breaks the circular dependency. Today you cannot partition either side cleanly. |
| 4.D | Add a `GIN (payload_json jsonb_path_ops)` index on `incident_events` | Enables `@>`/`@?` postmortem queries; `jsonb_path_ops` is ~ 40% smaller than the default. |
| 4.E | Add `ALTER TABLE coordination_audit SET (autovacuum_vacuum_scale_factor = 0.02, fillfactor = 100)` | Tune for append-only hot path. |
| 4.F | Install `pg_partman` for automated monthly partition creation and retention | Avoids hand-rolled cron jobs for the retention policies documented in §10 of `persistence_architecture.md`. |
| 4.G | For the `tool_calls` and `retrieved_contexts` tables (Phase 3 migration, not yet shipped), declare them as hypertables from the start with `segment_by = run_id` compression | These are the largest-volume append-only surfaces; retrofitting is harder than starting right. |
| 4.H | Add covering index on `event_outbox (status, created_at) INCLUDE (event_id, topic, retry_count) WHERE status = 'pending'` | Index-only scans for the relay's hot path; reduces heap fetches. |

---

## 5. Version Compatibility (PostgreSQL 16 features)

### 5.1 Current state

Nothing in the migrations declares a minimum PG version. The DDL is portable back to PG 13.

Missing 16-specific opportunities:

- `uuid-ossp` vs `pgcrypto` — `gen_random_uuid()` is used, which is the right choice on 16 (built-in `pgcrypto` path). Good.
- No `ICU` collation setting — the cluster default may be `C` or `en_US.UTF-8`; lexicographic sorts on TEXT columns (`service`, `resource_id`) will be locale-dependent.
- `timestamptz` is used consistently ✅ — no naïve `timestamp`.
- No use of `JSONB_PATH_QUERY_TZ` or the expanded SQL/JSON functions available since 16.
- No table access method specified; everything is heap. For heavy-read analytic tables (`retrieved_contexts`) the future `columnar` extension (Citus/Hydra) is worth calling out.
- `event_outbox.status` uses TEXT + CHECK rather than native enum. That is portable and faster to extend (as migration 004 demonstrates) — **keep this**; do not convert to enum.
- No `vacuum_truncate = off` on hot append-only tables — on PG 16 this avoids the AccessExclusiveLock that truncation takes.

### 5.2 Recommendations

| # | Change | Why |
|---|---|---|
| 5.A | Add a migration 000 `SELECT version()` guard that aborts if < PG 16.0 | Pins the floor; lets us use 16 features without feature-detect logic. |
| 5.B | Declare `CREATE COLLATION IF NOT EXISTS "ci" (provider = icu, locale = 'und-u-ks-level2', deterministic = false)` and use it on user-facing TEXT filters (e.g., `service`, `resource_id`) | Case-insensitive equality without `LOWER()` function indexes. |
| 5.C | Add `ALTER TABLE telemetry_metrics SET (vacuum_truncate = off, autovacuum_vacuum_insert_scale_factor = 0.05)` | 16-specific insert-triggered autovacuum is well-suited to append-only. |
| 5.D | Use `JSONB` with `jsonb_path_ops` GIN for `payload_json` and `metadata_json` | Smaller, faster for `@>` containment. |
| 5.E | Use `GENERATED ALWAYS AS IDENTITY` columns for any future surrogate keys we don't want UUIDs for | Replaces serial; 16-clean. |
| 5.F | Add `pg_stat_statements` and `auto_explain` to `docker-compose.deps.yml` `shared_preload_libraries` | Enables the split-gate observability that ADR-006 depends on. |
| 5.G | Pin extension versions in migrations: `CREATE EXTENSION vector VERSION '0.7.0'`, `CREATE EXTENSION timescaledb VERSION '2.14.0'` | ADR-006 names "pgvector ≥ 0.5.0" but migrations do not verify. |

---

## 6. Cross-Cutting Findings

### 6.1 Naming drift between authoritative doc and shipped schema

| Doc-canonical name | Shipped table name | Location |
|---|---|---|
| `audit_log` | `coordination_audit` | 003_coordination_audit.sql |
| `metric_snapshots` | `telemetry_metrics` | 002_telemetry_vector.sql |
| `vector_documents` | `vector_embeddings` | 002_telemetry_vector.sql |
| `diagnoses` | `diagnosis_results` | 001_incident_lifecycle.sql |
| `outbox` | `event_outbox` | 001_incident_lifecycle.sql |
| `incident_events.id` | `incident_events.event_id` | 001 (docs sample uses `id`) |

Per CLAUDE.md: **"this document [persistence_architecture.md] is the persistence authority"**. Either:

- Update the architecture doc's sample DDL (§7.2, §7.4, §8.2) to match shipped names, **or**
- Rename tables in a migration 005.

Pick one; drift this visible in the authoritative doc erodes trust in every other invariant claimed by it.

### 6.2 Missing tables from the architecture inventory

[persistence_architecture.md:504-523](../../../docs/architecture/persistence_architecture.md#L504-L523) lists `agent_runs`, `tool_calls`, `retrieved_contexts`, `remediation_plans`, `diagnoses`. None of these exist in migrations. The currently-shipped `remediation_actions` and `diagnosis_results` partially cover this — but the Phase 3 migration (reasoning trace persistence) appears to be unshipped. Worth confirming this is tracked in openspec.

### 6.3 Missing observability hooks promised by docs

[persistence_architecture.md:683-687](../../../docs/architecture/persistence_architecture.md#L683-L687) commits to:

- `sre_agent_db_query_duration_seconds` (used by the pgvector ADR-006 gate)
- `sre_agent_outbox_pending_rows`
- `sre_agent_redis_stream_lag`

Without these, the ADR-006 quantitative gates cannot be evaluated in production. This is a gating dependency for safely operating on the Phase-4 schema.

---

## 7. Prioritized Fix List (cut this list, not the report)

| Priority | Fix | Section |
|---|---|---|
| P0 | HNSW `WITH (m=24, ef_construction=200)` + `ef_search` per-session + recall CI harness | §1.3 A/B/E |
| P0 | `processed_events` consumer-side dedup table; `UNIQUE (event_id)` on outbox; explicit DLQ state | §2.2 A/B/D |
| P0 | Dual-mode `CHECK` exclusivity + dimension generated column + fallback row-cap | §3.2 B/C/D |
| P1 | Partition `coordination_audit` (+ monthly pg_partman) + BRIN on time columns | §4.2 A/B |
| P1 | Timescale compression + retention policies installed | §1.3 G/H |
| P1 | Naming drift resolved in the authoritative doc | §6.1 |
| P2 | PG 16 guard + ICU collation + extension version pinning | §5.2 A/B/G |
| P2 | `jsonb_path_ops` GIN on payload/metadata columns | §4.2 D, §5.2 D |
| P2 | Promote `vector_mode` gauge + outbox backlog/DLQ metrics | §3.2 G, §6.3 |

---

## 8. What NOT to change

- `TEXT + CHECK` status columns — keep this over native enums (migration 004 already demonstrated why).
- `idempotency_key` as a distinct concept from `event_id` — this is **correct** ADR-003 modeling; do not collapse them.
- Single-instance Redis Streams bus — ADR-006 split gates remain far above current volume.
- Keeping ChromaDB for development — the `VectorStorePort` abstraction is doing its job.

---

## References

- [persistence_architecture.md](../../../docs/architecture/persistence_architecture.md)
- [ADR-006](../../../docs/project/ADRs/006-persistence-authority-reconciliation.md)
- [Migration 001](../../../src/sre_agent/adapters/persistence/migrations/001_incident_lifecycle.sql)
- [Migration 002](../../../src/sre_agent/adapters/persistence/migrations/002_telemetry_vector.sql)
- [Migration 003](../../../src/sre_agent/adapters/persistence/migrations/003_coordination_audit.sql)
- [Migration 004](../../../src/sre_agent/adapters/persistence/migrations/004_relay_vector_fixes.sql)
- [PgVectorStoreAdapter](../../../src/sre_agent/adapters/vectordb/pgvector/adapter.py)
- [AGENTS.md](../../../AGENTS.md)
