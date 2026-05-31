# Deep Schema and WebSocket Research

**Date:** 2026-05-31
**Status:** Complete

---

## Research Questions

1. What does migration 009 create? Any accuracy/resolution metrics?
2. What columns does `coordination_audit` have (migration 003)?
3. Does the Python SRE Agent emit `pg_notify` / `NOTIFY` after writing incident events?
4. Do migrations 005, 006, 007 add columns to `incidents` or `incident_events`?
5. Is `drizzle-zod` already in `lib/db/package.json`?
6. Is the Express app in `artifacts/api-server/src/app.ts` the default export, or is an `http.Server` exposed?
7. What Drizzle ORM version and pg packages are in `lib/db/package.json`?

---

## Q1 — Migration 009: metric_baselines continuous aggregate

**File:** `src/sre_agent/adapters/persistence/migrations/009_metric_baselines_continuous_aggregate.sql`

### What it creates

- **Materialized view (TimescaleDB continuous aggregate):** `metric_baselines`
  - Aggregates from `telemetry_metrics` table
  - Bucket size: `5 minutes`
  - Columns: `service`, `metric_name`, `bucket` (time_bucket), `avg_value`, `p95_value`
  - Query: `avg(value)` and `percentile_cont(0.95)` within each bucket
- **Index:** `idx_metric_baselines_service_metric_bucket` on `(service, metric_name, bucket DESC)`
- **Policy:** `add_continuous_aggregate_policy` with `start_offset=1 day`, `end_offset=5 minutes`, `schedule_interval=5 minutes`

### Guard conditions
The migration skips silently if TimescaleDB is not installed or if `telemetry_metrics` does not exist.

### Accuracy / resolution rate metrics
**No.** There are no pre-computed accuracy or resolution rate metrics in this migration. It only provides rolling average and 95th-percentile metric baselines per service/metric.

---

## Q2 — Migration 003: coordination_audit table columns

**File:** `src/sre_agent/adapters/persistence/migrations/003_coordination_audit.sql`

### Table: `coordination_audit`

| Column | Type | Notes |
|---|---|---|
| `audit_id` | UUID | PRIMARY KEY |
| `actor_type` | TEXT NOT NULL | e.g. "agent", "human" |
| `actor_id` | TEXT NOT NULL | e.g. "sre-agent-prod-01" |
| `action` | TEXT NOT NULL | e.g. "lock_acquired", "lock_revoked", "cooldown_set", "preemption", "human_override" |
| `provider` | TEXT NOT NULL | CHECK IN ('kubernetes', 'aws', 'azure') |
| `compute_mechanism` | TEXT NOT NULL | CHECK IN ('KUBERNETES', 'SERVERLESS', 'VIRTUAL_MACHINE', 'CONTAINER_INSTANCE') |
| `resource_id` | TEXT NOT NULL | Canonical resource ID / ARN / K8s path |
| `lock_priority` | INTEGER | Nullable — agent priority level |
| `fencing_token` | BIGINT | Nullable — Redis fencing token |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | Timestamp of audit event |
| `details_json` | JSONB | Nullable — freeform extra detail |

### Indexes
- `idx_coordination_audit_resource` — `(resource_id, created_at DESC)`
- `idx_coordination_audit_actor` — `(actor_id, created_at DESC)`
- `idx_coordination_audit_action` — `(action, created_at DESC)`

### Suitability for dashboard audit log display
**Yes — excellent fit.** The table has timestamps, human-readable actor/action/resource fields, provider/mechanism context, priority level, and a JSONB detail column. It directly maps to an audit log table UI component.

---

## Q3 — pg_notify / NOTIFY in Python SRE Agent

**Files searched:**
- `src/sre_agent/adapters/persistence/event_store.py`
- `src/sre_agent/adapters/persistence/postgres_outbox.py`
- All `*.py` files under `src/sre_agent/`
- All `*.sql` files under `src/sre_agent/`

### Result: NO pg_notify calls exist anywhere

The Python SRE Agent does **not** emit any PostgreSQL `NOTIFY` or `pg_notify()` calls after writing incident events. Confirmed by exhaustive grep across the entire `src/sre_agent/` subtree (both Python and SQL files) with no matches.

### What event_store.py does instead
- Writes events to `incident_events` table using `ON CONFLICT (idempotency_key) DO NOTHING`
- Does NOT call `pg_notify`
- Events are surfaced to other consumers only via the outbox relay pattern (polling `event_outbox` table)

### What postgres_outbox.py does
- Implements polling-based outbox (SKIP LOCKED)
- Marks rows as `sent` / `failed` / `dlq`
- Does NOT call `pg_notify`

### Implication for real-time dashboard
If WebSocket push via PostgreSQL `LISTEN/NOTIFY` is required, the SRE Agent must be **modified** to add `pg_notify` calls (or a DB trigger must be added to `incident_events`). There is no existing notification channel name or payload format to reuse — this is net-new work.

---

## Q4 — Additional columns added to `incidents` / `incident_events` by migrations 005–007

### Migration 005 (`005_postgres_schema_reconciliation.sql`)
- **`event_outbox`** — adds `dlq_at TIMESTAMPTZ` and `dlq_reason TEXT`; expands `status` CHECK to include `'dlq'`; adds `uq_outbox_event_id` UNIQUE constraint; adds BRIN + processing indexes
- **`processed_events`** — NEW table: `(consumer TEXT, event_id UUID, processed_at TIMESTAMPTZ)`
- **`vector_embeddings`** — adds `embedding vector(1536)`, `embedding_dim INTEGER GENERATED`, `embedding_json JSONB`, `metadata_json JSONB`, `created_at TIMESTAMPTZ`; HNSW index
- **`incidents`** — NO new columns
- **`incident_events`** — NO new columns

### Migration 006 (`006_schema_improvements.sql`)
- **`incidents`** — adds `version INTEGER NOT NULL DEFAULT 0` (OCC support), with constraint `chk_incidents_version_non_negative`
- **`incident_events`** — adds GIN index `idx_incident_events_payload_gin` on `payload_json` but NO new columns
- NEW tables: `agent_runs`, `tool_calls`, `retrieved_contexts`
- **`processed_events`** — FK changed from CASCADE to RESTRICT

### Migration 007 (`007_partition_readiness_and_status_fidelity.sql`)
- **`incidents`** — FK `fk_latest_event` made `DEFERRABLE INITIALLY DEFERRED`; NO new columns
- **`incident_events`** — BRIN index `idx_incident_events_occurred_at_brin` added; NO new columns
- NEW: `incident_events_partitioned` (partitioned mirror table) with current-month partition + default partition
- `remediation_actions` constraint expanded to include `executing`, `verifying`, `cancelled`, `rolled_back`

### Summary for Drizzle schema definitions
The column that MUST be added to the Drizzle `incidents` schema:
- `version: integer('version').notNull().default(0)` — added in migration 006

No new columns added to `incident_events` across migrations 005–007.

New tables that may need Drizzle schemas if used from the dashboard:
- `agent_runs` (run_id, incident_id, agent_id, started_at, ended_at, outcome, metadata)
- `tool_calls` (call_id, run_id, tool_name, input, output, latency_ms, status, called_at)
- `retrieved_contexts` (context_id, run_id, doc_id, similarity_score, content_snippet, source, retrieved_at)
- `processed_events` (consumer, event_id, processed_at)

---

## Q5 — drizzle-zod in lib/db/package.json

**File:** `fullstackapp/SRE-Command-Center/lib/db/package.json`

**Yes — `drizzle-zod` is already a dependency.**

```json
"drizzle-zod": "^0.8.3"
```

No installation needed. Ready to import and use.

---

## Q6 — Express app.ts: default export and http.Server

**File:** `fullstackapp/SRE-Command-Center/artifacts/api-server/src/app.ts`

### Key findings

- `app.ts` creates an Express `app` of type `Express`
- It configures: `pino-http` logging, CORS (configurable via `CORS_ORIGIN` env var), `express.json()`, `express.urlencoded()`, `/api` router, global error handler
- **Default export:** `export default app` — YES, the Express app is the default export
- **Does it expose `http.Server`?** **No.** Only the Express `app` instance is exported. There is no `http.createServer(app)` call in `app.ts`.

### Implication for WebSocket attachment
To attach a WebSocket server (e.g., `ws` library), the consuming server entry point (`server.ts` or equivalent) must call `http.createServer(app)` itself and then pass the `server` instance to `new WebSocket.Server({ server })`. The WebSocket upgrade cannot be attached directly to `app.ts` as written — it needs to be done in the server startup file.

---

## Q7 — Drizzle ORM version and pg packages in lib/db/package.json

**File:** `fullstackapp/SRE-Command-Center/lib/db/package.json`

### Dependencies

| Package | Version |
|---|---|
| `drizzle-orm` | `catalog:` (resolved from workspace catalog — version TBD from root catalog) |
| `drizzle-zod` | `^0.8.3` |
| `pg` | `^8.20.0` |
| `zod` | `catalog:` (workspace catalog) |

### Dev Dependencies

| Package | Version |
|---|---|
| `@types/node` | `catalog:` |
| `@types/pg` | `^8.20.0` |
| `drizzle-kit` | `^0.31.10` |

### Notes
- `drizzle-orm` and `zod` use a workspace `catalog:` version reference — the exact version is defined in the root workspace `pnpm-workspace.yaml` or equivalent catalog file
- `drizzle-kit@^0.31.10` is a very recent release (current as of mid-2025)
- `pg@^8.20.0` and `@types/pg@^8.20.0` are the standard PostgreSQL node client

---

## Key Discoveries Summary

1. **No pg_notify** — The Python SRE Agent does **not** emit any PostgreSQL notifications. Real-time WebSocket push via LISTEN/NOTIFY requires net-new work: either a Python-side `pg_notify` call added to `event_store.py` after each insert, or a PostgreSQL trigger on `incident_events`.

2. **incidents.version column** — Migration 006 added a `version` column (OCC) to `incidents`. This must be reflected in the Drizzle schema definition.

3. **drizzle-zod already available** — `drizzle-zod@^0.8.3` is already in `lib/db/package.json`. No install step required.

4. **Express app has no http.Server** — `app.ts` exports only the Express app. WebSocket attachment must happen in the server entrypoint by calling `http.createServer(app)` externally.

5. **coordination_audit is dashboard-ready** — Rich columns including `actor_type`, `actor_id`, `action`, `resource_id`, `provider`, `compute_mechanism`, `lock_priority`, `fencing_token`, `created_at`, and `details_json` JSONB.

6. **metric_baselines** — Provides avg and p95 per service/metric per 5-minute bucket. No resolution rate or accuracy metrics. TimescaleDB-only (skips gracefully if not installed).

---

## Clarifying Questions (cannot be answered by research alone)

1. What is the exact resolved version of `drizzle-orm` from the workspace catalog? (Need to read root `pnpm-workspace.yaml` or `package.json`.)
2. Is there a `server.ts` or similar entry point in `artifacts/api-server/src/` that calls `http.createServer(app)`? If not, one must be created for WebSocket support.
3. Should the `pg_notify` call be added to the Python `event_store.py` directly, or via a DB trigger?

---

## References

- `src/sre_agent/adapters/persistence/migrations/009_metric_baselines_continuous_aggregate.sql`
- `src/sre_agent/adapters/persistence/migrations/003_coordination_audit.sql`
- `src/sre_agent/adapters/persistence/migrations/005_postgres_schema_reconciliation.sql`
- `src/sre_agent/adapters/persistence/migrations/006_schema_improvements.sql`
- `src/sre_agent/adapters/persistence/migrations/007_partition_readiness_and_status_fidelity.sql`
- `src/sre_agent/adapters/persistence/event_store.py`
- `src/sre_agent/adapters/persistence/postgres_outbox.py`
- `fullstackapp/SRE-Command-Center/lib/db/package.json`
- `fullstackapp/SRE-Command-Center/artifacts/api-server/src/app.ts`
