# PostgreSQL Schema Analysis — Autonomous SRE Agent

> **Date:** 2026-04-17  
> **Scope:** Migrations 001–005, all persistence adapters, `persistence_architecture.md`, ADR-006, `AGENTS.md`  
> **Schema version under review:** Migration 005 (Schema Reconciliation)

---

## 0. Executive Summary

The schema has matured significantly from the initial 001–004 migration set through to the 005 reconciliation. The **pattern foundation is strong**: event-sourced incident lifecycle, transactional outbox with DLQ, dual-mode pgvector/JSONB, and monthly-partitioned coordination audit. Migration 005 closed the highest-priority gaps from the [prior schema review](file:///Users/faizanhussain/Documents/PersonalProjects/SREAgent/02Code/autonomous-sre-agent/docs/architecture/reviews/postgres_schema_review_2026-04-13.md).

**What's working well:**
- ✅ HNSW tuned with `m=24, ef_construction=200` and `SET LOCAL hnsw.ef_search = 100`
- ✅ `processed_events` consumer dedup table shipped
- ✅ `UNIQUE(event_id)` on `event_outbox` 
- ✅ DLQ terminal state with `dlq_at`/`dlq_reason` + CHECK constraint
- ✅ Dual-mode exclusivity CHECK + `embedding_dim` generated column
- ✅ `coordination_audit` monthly range partitioning with BRIN
- ✅ TimescaleDB compression + retention policies (90 days)
- ✅ JSONB fallback safety cap (10,000 rows) + Prometheus metric

**What still needs attention** (30 findings across 8 domains):

| Priority | Count | Domain |
|----------|-------|--------|
| P0 | 5 | Data integrity gaps |
| P0 | 3 | Performance bottlenecks |
| P1 | 5 | Missing tables from architecture |
| P1 | 4 | Observability gaps |
| P1 | 3 | Partitioning & retention |
| P2 | 4 | Naming drift |
| P2 | 3 | Security hardening |
| P2 | 3 | Operational tuning |

---

## 1. Current Schema Inventory

### 1.1 Shipped tables (9 tables across 5 migrations)

| Table | Migration | Type | Row Growth | Partitioned? |
|-------|-----------|------|------------|-------------|
| `incident_events` | 001 | Append-only log | Medium | ❌ No |
| `incidents` | 001 | Mutable projection | Low | N/A |
| `diagnosis_results` | 001 | Append-only | Low | ❌ No |
| `remediation_actions` | 001 | Mutable | Low | N/A |
| `event_outbox` | 001 | Transient (status-tracked) | Medium | ❌ No |
| `telemetry_metrics` | 002 | Append-only (hypertable) | **Very High** | ✅ TimescaleDB |
| `baseline_snapshots` | 002 | Derived | Low | ❌ No |
| `vector_embeddings` | 002 | Mutable (upsert) | Low | N/A |
| `coordination_audit` | 003→005 | Append-only | **High** | ✅ Monthly range |
| `processed_events` | 005 | Append-only dedup | Medium | ❌ No |

### 1.2 Tables promised by architecture but NOT shipped

| Table | Documented In | Purpose | Status |
|-------|--------------|---------|--------|
| `agent_runs` | [persistence_architecture.md:439](file:///Users/faizanhussain/Documents/PersonalProjects/SREAgent/02Code/autonomous-sre-agent/docs/architecture/persistence_architecture.md#L439) | Reasoning trace root | ❌ Missing |
| `tool_calls` | [persistence_architecture.md:450](file:///Users/faizanhussain/Documents/PersonalProjects/SREAgent/02Code/autonomous-sre-agent/docs/architecture/persistence_architecture.md#L450) | LLM/tool invocation log | ❌ Missing |
| `retrieved_contexts` | [persistence_architecture.md:462](file:///Users/faizanhussain/Documents/PersonalProjects/SREAgent/02Code/autonomous-sre-agent/docs/architecture/persistence_architecture.md#L462) | RAG evidence citations | ❌ Missing |
| `remediation_plans` | [persistence_architecture.md:515](file:///Users/faizanhussain/Documents/PersonalProjects/SREAgent/02Code/autonomous-sre-agent/docs/architecture/persistence_architecture.md#L515) | Plan aggregation | ❌ Missing (partially covered by `remediation_actions`) |
| `metric_baselines` (continuous aggregate) | [persistence_architecture.md:549](file:///Users/faizanhussain/Documents/PersonalProjects/SREAgent/02Code/autonomous-sre-agent/docs/architecture/persistence_architecture.md#L549) | Rolling baseline view | ❌ Missing |

---

## 2. Data Integrity Findings

### 2.1 `incidents` table — No optimistic concurrency control (P0)

[incidents table DDL](file:///Users/faizanhussain/Documents/PersonalProjects/SREAgent/02Code/autonomous-sre-agent/src/sre_agent/adapters/persistence/migrations/001_incident_lifecycle.sql#L39-L60)

The `incidents` projection has no `version` column. The [update_projection](file:///Users/faizanhussain/Documents/PersonalProjects/SREAgent/02Code/autonomous-sre-agent/src/sre_agent/adapters/persistence/incident_store.py#L289-L342) method performs a read-then-write without any concurrency guard:

```python
# incident_store.py:317-328 — classic TOCTOU race
existing = await conn.fetchrow(_SELECT_INCIDENT, incident_id)
# ... derive values from existing ...
await conn.execute(_UPSERT_PROJECTION, ...)
```

Two concurrent event handlers processing the same incident stream can interleave, causing a **lost update**. The `_UPSERT_PROJECTION` SQL uses `ON CONFLICT DO UPDATE` but doesn't verify that `latest_event_id` hasn't changed between the SELECT and the UPDATE.

> [!CAUTION]
> **Fix:** Add `version INTEGER NOT NULL DEFAULT 0` to `incidents`. Increment on every update with `WHERE version = $expected_version`. Return `RETURNING version` and raise `StaleProjectionError` on 0 affected rows.

### 2.2 `incident_events` — FK entanglement blocks future partitioning (P1)

```
incidents.latest_event_id → incident_events.event_id  (FK)
event_outbox.event_id → incident_events.event_id      (FK)
```

PostgreSQL cannot attach/detach partitions on a table that is the target of foreign keys from non-partitioned tables. If `incident_events` ever needs partitioning (documented as a goal in the prior review §4.A), these FKs must be converted to deferrable constraints or dropped in favor of application-level enforcement.

### 2.3 `remediation_actions` — Status mapping lossy (P1)

[remediation_store.py:40-52](file:///Users/faizanhussain/Documents/PersonalProjects/SREAgent/02Code/autonomous-sre-agent/src/sre_agent/adapters/persistence/remediation_store.py#L40-L52)

```python
_STATUS_TO_DB = {
    "cancelled": "failed",   # ← information loss
    "executing": "running",  # ← information loss
    "verifying": "running",  # ← information loss
}
```

Three domain statuses collapse into DB values. On read-back, the adapter returns the DB value (`failed`, `running`), not the original domain status. This makes it impossible to distinguish a genuinely failed remediation from a cancelled one in postmortem queries.

> [!IMPORTANT]
> **Fix:** Extend the DB CHECK constraint to include `'cancelled'`, `'executing'`, `'verifying'`. Update migration:
> ```sql
> ALTER TABLE remediation_actions DROP CONSTRAINT chk_action_status;
> ALTER TABLE remediation_actions ADD CONSTRAINT chk_action_status
>     CHECK (action_status IN ('planned','approved','running','executing',
>            'verifying','completed','failed','cancelled','rolled_back'));
> ```

### 2.4 `coordination_audit` — Partition composite PK loses audit_id uniqueness (P1)

[Migration 005:370](file:///Users/faizanhussain/Documents/PersonalProjects/SREAgent/02Code/autonomous-sre-agent/src/sre_agent/adapters/persistence/migrations/005_postgres_schema_reconciliation.sql#L370)

```sql
CONSTRAINT coordination_audit_partitioned_pkey PRIMARY KEY (audit_id, created_at)
```

Partitioning requires `created_at` in the PK (PostgreSQL constraint). This means `audit_id` alone is no longer globally unique at the DB level. Two rows with the same `audit_id` but different `created_at` values would be accepted. While UUIDs make collisions astronomically unlikely, the constraint is semantically weaker than the original.

> [!TIP]
> Add a unique index: `CREATE UNIQUE INDEX idx_coordination_audit_id ON coordination_audit (audit_id)`

### 2.5 `processed_events` — CASCADE delete risk (P0)

[Migration 005:112](file:///Users/faizanhussain/Documents/PersonalProjects/SREAgent/02Code/autonomous-sre-agent/src/sre_agent/adapters/persistence/migrations/005_postgres_schema_reconciliation.sql#L112)

```sql
FOREIGN KEY (event_id) REFERENCES incident_events (event_id) ON DELETE CASCADE
```

If an `incident_event` row is ever deleted (e.g., archival migration), all corresponding `processed_events` markers vanish silently. The next relay cycle would **re-publish** those events because the dedup marker is gone — violating at-most-once delivery.

> [!CAUTION]
> **Fix:** Change to `ON DELETE RESTRICT` or `ON DELETE SET NULL` with a nullable `event_id` + separate `original_event_id TEXT NOT NULL` column for the dedup check.

---

## 3. Performance Analysis

### 3.1 `store_batch` is N+1 (P0)

[adapter.py:345-351](file:///Users/faizanhussain/Documents/PersonalProjects/SREAgent/02Code/autonomous-sre-agent/src/sre_agent/adapters/vectordb/pgvector/adapter.py#L345-L351)

```python
async def store_batch(self, documents: list[VectorDocument]) -> int:
    for doc in documents:
        await self.store(doc)  # ← one round-trip per document
    return len(documents)
```

Each document triggers a separate `conn.acquire()` + SQL execution. For a 500-document batch, this is 500 network round-trips (~250ms at 0.5ms/trip). 

> [!IMPORTANT]
> **Fix:** Use `conn.executemany()` or `COPY ... FROM STDIN` with `conn.copy_records_to_table()` for bulk inserts. This would reduce 500 round-trips to 1.

### 3.2 Missing GIN index on JSONB columns (P1)

Neither `incident_events.payload_json` nor `vector_embeddings.metadata_json` have GIN indexes. Postmortem queries using `@>` containment operators will sequential-scan:

```sql
-- This query has no index support today:
SELECT * FROM incident_events WHERE payload_json @> '{"error_code": "OOMKilled"}'
```

> **Fix:** Add `jsonb_path_ops` GIN indexes:
> ```sql
> CREATE INDEX idx_incident_events_payload_gin ON incident_events 
>     USING GIN (payload_json jsonb_path_ops);
> CREATE INDEX idx_vector_metadata_gin ON vector_embeddings 
>     USING GIN (metadata_json jsonb_path_ops);
> ```

### 3.3 `event_outbox` covering index opportunity (P2)

The relay hot path queries `WHERE status = 'pending' ORDER BY created_at`. The current partial index filters correctly but still requires a heap fetch for `event_id`, `topic`, and `retry_count`.

> **Fix:** Covering index for index-only scans:
> ```sql
> CREATE INDEX idx_outbox_relay_covering ON event_outbox (status, created_at ASC)
>     INCLUDE (event_id, topic, retry_count) WHERE status = 'pending';
> ```

---

## 4. Partitioning & Retention Gaps

### 4.1 `incident_events` not partitioned (P1)

The prior review (§4.A) recommended partitioning, and the architecture doc specifies a 2-year retention policy. At current scale this table will grow indefinitely. No `DETACH PARTITION` + archive path exists.

### 4.2 `processed_events` has no retention (P1)

This table grows monotonically (one row per consumer per event). With no TTL or retention, it will become the largest table in the system. After the outbox row is `sent` and the event is older than the stream MAXLEN window, the dedup marker serves no purpose.

> **Fix:** Add a scheduled cleanup: `DELETE FROM processed_events WHERE processed_at < now() - INTERVAL '30 days'`

### 4.3 `baseline_snapshots` has no retention (P2)

Snapshots accumulate without cleanup. The architecture doc doesn't specify retention for this table.

---

## 5. Observability Gaps

### 5.1 Promised metrics status

| Metric | Status |
|--------|--------|
| `sre_agent_outbox_pending_rows` | ✅ Implemented |
| `sre_agent_outbox_dlq_rows` | ✅ Implemented |
| `sre_agent_vector_fallback_truncated_total` | ✅ Implemented |
| `sre_agent_db_query_duration_seconds` | ❌ **Not implemented** |
| `sre_agent_db_pool_active_connections` | ❌ **Not implemented** |
| `sre_agent_redis_stream_lag` | ❌ **Not implemented** |
| `sre_agent_vector_mode` gauge | ❌ **Not implemented** |

> [!WARNING]
> Without `sre_agent_db_query_duration_seconds`, the ADR-006 quantitative split gates (p95 insert > 120ms, p95 similarity > 250ms) **cannot be evaluated** in production. This is a gating dependency.

### 5.2 No `pg_stat_statements` in docker-compose (P2)

[docker-compose.deps.yml](file:///Users/faizanhussain/Documents/PersonalProjects/SREAgent/02Code/autonomous-sre-agent/docker-compose.deps.yml) does not configure `shared_preload_libraries`. Add:

```yaml
command:
  - "postgres"
  - "-c" 
  - "shared_preload_libraries=pg_stat_statements"
```

---

## 6. Naming Drift Audit

| Architecture Doc Name | Shipped Table Name | Verdict |
|----------------------|-------------------|---------|
| `audit_log` | `coordination_audit` | ⚠️ Drift |
| `metric_snapshots` | `telemetry_metrics` | ⚠️ Drift |
| `vector_documents` | `vector_embeddings` | ⚠️ Drift |
| `diagnoses` | `diagnosis_results` | ⚠️ Drift |
| `outbox` | `event_outbox` | ⚠️ Drift |
| `incident_events.id` | `incident_events.event_id` | ⚠️ Drift |

The [prior review](file:///Users/faizanhussain/Documents/PersonalProjects/SREAgent/02Code/autonomous-sre-agent/docs/architecture/reviews/postgres_schema_review_2026-04-13.md#L193-L209) flagged this. Migration 005 did not resolve it. The shipped names are more descriptive — **recommend updating the architecture doc** to match shipped DDL rather than renaming tables.

---

## 7. Security Hardening

### 7.1 No row-level security (RLS) (P2)

Multi-agent coordination means different agents write to shared tables. No RLS policies restrict which `agent_id` can write to which rows. While Redis locks provide coordination, a misconfigured agent could write audit entries impersonating another agent.

### 7.2 No schema isolation (P2)

All tables live in `public`. Consider a dedicated `sre` schema for application tables vs `audit` schema for compliance-critical tables (`coordination_audit`, `incident_events`).

### 7.3 Extension versions not pinned (P2)

Migrations use `CREATE EXTENSION IF NOT EXISTS vector` without version pinning. A major pgvector upgrade could change HNSW behavior silently.

> **Fix:** `CREATE EXTENSION IF NOT EXISTS vector VERSION '0.7.0'`

---

## 8. Adapter-Level Findings

### 8.1 `update_projection` read-then-write not in transaction (P0)

[incident_store.py:317-342](file:///Users/faizanhussain/Documents/PersonalProjects/SREAgent/02Code/autonomous-sre-agent/src/sre_agent/adapters/persistence/incident_store.py#L317-L342)

```python
async with self._pool.acquire() as conn:
    existing = await conn.fetchrow(_SELECT_INCIDENT, incident_id)  # read
    # ... compute values ...
    await conn.execute(_UPSERT_PROJECTION, ...)  # write
```

The SELECT and UPDATE are in the same connection but **not wrapped in an explicit transaction**. Under `autocommit` mode (asyncpg default), another connection can modify the row between the two statements.

> **Fix:** Wrap in `async with conn.transaction():`

### 8.2 Coordination store uses `datetime.now().astimezone()` (P1)

[coordination_store.py:91](file:///Users/faizanhussain/Documents/PersonalProjects/SREAgent/02Code/autonomous-sre-agent/src/sre_agent/adapters/persistence/coordination_store.py#L91)

```python
now = datetime.now().astimezone()  # ← depends on system timezone
```

Other adapters correctly use `datetime.now(tz=UTC)`. This inconsistency means coordination audit timestamps may be in a different timezone than incident events on the same machine.

### 8.3 `delete` method has two round-trips (P2)

[adapter.py:444-451](file:///Users/faizanhussain/Documents/PersonalProjects/SREAgent/02Code/autonomous-sre-agent/src/sre_agent/adapters/vectordb/pgvector/adapter.py#L444-L451)

```python
row = await conn.fetchrow(_GET_BY_SOURCE_ID, doc_id, self._collection)
if row is None:
    return False
deleted = await conn.fetch(_DELETE_BY_ID, row["embedding_id"])
```

This can be a single statement: `DELETE FROM vector_embeddings WHERE source_id = $1 AND source_type = $2 RETURNING embedding_id`

---

## 9. Prioritized Improvement Roadmap

### P0 — Must fix (data correctness / safety)

| # | Finding | Section |
|---|---------|---------|
| 1 | Add `version` column to `incidents` for OCC | §2.1 |
| 2 | Wrap `update_projection` in explicit transaction | §8.1 |
| 3 | Change `processed_events` FK from CASCADE to RESTRICT | §2.5 |
| 4 | Implement `store_batch` as bulk insert | §3.1 |
| 5 | Implement `sre_agent_db_query_duration_seconds` metric | §5.1 |

### P1 — Should fix (correctness, performance, completeness)

| # | Finding | Section |
|---|---------|---------|
| 6 | Extend `remediation_actions` CHECK to include domain statuses | §2.3 |
| 7 | Add unique index on `coordination_audit(audit_id)` | §2.4 |
| 8 | Add GIN indexes on JSONB columns | §3.2 |
| 9 | Add retention policy for `processed_events` | §4.2 |
| 10 | Ship `agent_runs`, `tool_calls`, `retrieved_contexts` tables | §1.2 |
| 11 | Ship `metric_baselines` continuous aggregate | §1.2 |
| 12 | Fix timezone inconsistency in coordination store | §8.2 |
| 13 | Plan `incident_events` partitioning (resolve FK entanglement first) | §2.2, §4.1 |
| 14 | Implement remaining Prometheus metrics | §5.1 |

### P2 — Nice to have (hardening, operational)

| # | Finding | Section |
|---|---------|---------|
| 15 | Add covering index on `event_outbox` for relay | §3.3 |
| 16 | Update architecture doc names to match shipped DDL | §6 |
| 17 | Pin extension versions in migrations | §7.3 |
| 18 | Add `pg_stat_statements` to docker-compose | §5.2 |
| 19 | Consolidate `delete` to single SQL statement | §8.3 |
| 20 | Add `baseline_snapshots` retention policy | §4.3 |
| 21 | Consider schema isolation (`sre` / `audit`) | §7.2 |
| 22 | Add RLS policies for multi-agent writes | §7.1 |

---

## 10. Enhanced Schema — Proposed DDL Changes

### 10.1 Incidents table with OCC

```diff
 CREATE TABLE IF NOT EXISTS incidents (
     incident_id         UUID            PRIMARY KEY,
     service             TEXT            NOT NULL,
     severity            TEXT            NOT NULL,
     status              TEXT            NOT NULL,
     opened_at           TIMESTAMPTZ     NOT NULL,
     updated_at          TIMESTAMPTZ     NOT NULL,
     closed_at           TIMESTAMPTZ,
     latest_event_id     UUID            NOT NULL,
     provider            TEXT            NOT NULL,
     compute_mechanism   TEXT            NOT NULL,
     resource_id         TEXT            NOT NULL,
+    version             INTEGER         NOT NULL DEFAULT 0,
 
     CONSTRAINT fk_latest_event
         FOREIGN KEY (latest_event_id) REFERENCES incident_events (event_id),
     CONSTRAINT chk_incident_status
         CHECK (status IN ('open', 'investigating', 'mitigating', 'resolved', 'closed')),
+    CONSTRAINT chk_version_non_negative
+        CHECK (version >= 0)
 );
```

### 10.2 Phase 3 tables (reasoning traces)

```sql
CREATE TABLE IF NOT EXISTS agent_runs (
    run_id      UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID            REFERENCES incidents(incident_id),
    agent_id    TEXT            NOT NULL,
    started_at  TIMESTAMPTZ     NOT NULL DEFAULT now(),
    ended_at    TIMESTAMPTZ,
    outcome     TEXT,
    metadata    JSONB,

    CONSTRAINT chk_agent_run_outcome
        CHECK (outcome IS NULL OR outcome IN ('success','failed','aborted_by_human','timeout'))
);

CREATE TABLE IF NOT EXISTS tool_calls (
    call_id     UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id      UUID            NOT NULL REFERENCES agent_runs(run_id),
    tool_name   TEXT            NOT NULL,
    input       JSONB           NOT NULL,
    output      JSONB,
    latency_ms  INTEGER,
    status      TEXT            NOT NULL,
    called_at   TIMESTAMPTZ     NOT NULL DEFAULT now(),

    CONSTRAINT chk_tool_call_status
        CHECK (status IN ('success','error','timeout'))
);

CREATE INDEX idx_tool_calls_run ON tool_calls (run_id, called_at ASC);

CREATE TABLE IF NOT EXISTS retrieved_contexts (
    context_id       UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id           UUID            NOT NULL REFERENCES agent_runs(run_id),
    doc_id           TEXT            NOT NULL,
    similarity_score DOUBLE PRECISION NOT NULL,
    content_snippet  TEXT,
    source           TEXT,
    retrieved_at     TIMESTAMPTZ     NOT NULL DEFAULT now(),

    CONSTRAINT chk_similarity_range
        CHECK (similarity_score >= 0 AND similarity_score <= 1)
);

CREATE INDEX idx_retrieved_contexts_run ON retrieved_contexts (run_id, retrieved_at ASC);
```

---

## 11. What NOT to Change

| Current Pattern | Reason to Keep |
|----------------|---------------|
| `TEXT + CHECK` for status columns | Migration 004 demonstrated extensibility; native enums require `ALTER TYPE` in a transaction which cannot run inside `DO $$ ... $$` blocks |
| `idempotency_key` as distinct from `event_id` | Correct ADR-003 modeling; key is derived from business context, ID is random |
| Dual-mode pgvector/JSONB with runtime detection | Supports dev/CI without pgvector; adapter handles it cleanly |
| `uuid4()` for `embedding_id` (synthetic PK) | Composite PK `(source_type, source_id)` would complicate the `delete` API; UNIQUE constraint already enforces business uniqueness |
| Single PostgreSQL instance for all workloads | ADR-006 split gates are not yet triggered; operational simplicity is worth preserving |

---

## References

- [persistence_architecture.md](file:///Users/faizanhussain/Documents/PersonalProjects/SREAgent/02Code/autonomous-sre-agent/docs/architecture/persistence_architecture.md)
- [ADR-006](file:///Users/faizanhussain/Documents/PersonalProjects/SREAgent/02Code/autonomous-sre-agent/docs/project/ADRs/006-persistence-authority-reconciliation.md)
- [Prior Schema Review (2026-04-13)](file:///Users/faizanhussain/Documents/PersonalProjects/SREAgent/02Code/autonomous-sre-agent/docs/architecture/reviews/postgres_schema_review_2026-04-13.md)
- [Migration 001](file:///Users/faizanhussain/Documents/PersonalProjects/SREAgent/02Code/autonomous-sre-agent/src/sre_agent/adapters/persistence/migrations/001_incident_lifecycle.sql)
- [Migration 002](file:///Users/faizanhussain/Documents/PersonalProjects/SREAgent/02Code/autonomous-sre-agent/src/sre_agent/adapters/persistence/migrations/002_telemetry_vector.sql)
- [Migration 003](file:///Users/faizanhussain/Documents/PersonalProjects/SREAgent/02Code/autonomous-sre-agent/src/sre_agent/adapters/persistence/migrations/003_coordination_audit.sql)
- [Migration 004](file:///Users/faizanhussain/Documents/PersonalProjects/SREAgent/02Code/autonomous-sre-agent/src/sre_agent/adapters/persistence/migrations/004_relay_vector_fixes.sql)
- [Migration 005](file:///Users/faizanhussain/Documents/PersonalProjects/SREAgent/02Code/autonomous-sre-agent/src/sre_agent/adapters/persistence/migrations/005_postgres_schema_reconciliation.sql)
- [PgVectorStoreAdapter](file:///Users/faizanhussain/Documents/PersonalProjects/SREAgent/02Code/autonomous-sre-agent/src/sre_agent/adapters/vectordb/pgvector/adapter.py)
- [PostgresIncidentStore](file:///Users/faizanhussain/Documents/PersonalProjects/SREAgent/02Code/autonomous-sre-agent/src/sre_agent/adapters/persistence/incident_store.py)
- [PostgresOutboxStore](file:///Users/faizanhussain/Documents/PersonalProjects/SREAgent/02Code/autonomous-sre-agent/src/sre_agent/adapters/persistence/postgres_outbox.py)
- [OutboxRelay](file:///Users/faizanhussain/Documents/PersonalProjects/SREAgent/02Code/autonomous-sre-agent/src/sre_agent/adapters/persistence/outbox_relay.py)
- [AGENTS.md](file:///Users/faizanhussain/Documents/PersonalProjects/SREAgent/02Code/autonomous-sre-agent/AGENTS.md)
