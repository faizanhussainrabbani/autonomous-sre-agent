# Persistence Architecture Plan

> **Status:** Proposal — v1.1
> **Author:** Architecture Review
> **Date:** 2026-04-07
> **Scope:** End-to-end data persistence strategy for the Autonomous SRE Agent

---

## Architecture Authority and Resolved Decisions

The following questions were formally resolved on 2026-04-07. These answers supersede any conflicting statements in `docs/architecture/Technology_Stack.md` or `docs/architecture/evolution/roadmap.md`. Where those documents conflict with this plan, **this plan is the persistence authority; the Roadmap is the product sequencing authority**.

| # | Question | Decision | Rationale |
|---|---|---|---|
| 1 | Which document is authoritative when persistence, Technology_Stack, and roadmap conflict? | **This document** is authoritative for persistence decisions. The **Roadmap** is authoritative for product sequencing and phase ordering. `Technology_Stack.md` must be updated to match. | Prevents three-way drift during implementation. |
| 2 | Is production vector backend pgvector or ChromaDB? | **pgvector** | Consolidates into PostgreSQL operational surface; ChromaDB retained for local development only. `CLAUDE.md` and `roadmap.md` references to ChromaDB as the vector store are superseded. |
| 3 | Is the internal event bus Redis Streams or Kafka/NATS? | **Redis Streams** | Redis is already mandatory infrastructure. Kafka complexity is premature at current event volume. `Technology_Stack.md` open decision is now closed. `aiokafka` dependency remains for future optionality but is not used for the internal bus. |
| 4 | Delivery semantics: at-least-once + idempotent consumers, or strict exactly-once? | **At-least-once + idempotent consumers** | See Section 4-Q below for industry rationale. |
| 5 | Are cooldown, kill-switch, severity-override state in scope for first migration wave? | **No** — deferred to a later wave | Accepted operational gap: these surfaces lose state on restart. Documented as a known risk; addressed after core event and incident persistence is stable. |
| 6 | What SLO thresholds trigger split from shared PostgreSQL to dedicated TimescaleDB or vector store? | Industry benchmarks — see Section 6-Q below | Objective, measurable gates prevent a subjective call under incident pressure. |

### Decision 4: Delivery semantics — industry rationale

The industry-standard answer across Stripe, Uber, AWS, and the event-streaming literature is **at-least-once delivery with idempotent consumers**, not strict exactly-once end-to-end.

True exactly-once across a message bus and a database boundary requires distributed transactions (two-phase commit) between the bus and every consumer's database — an approach universally rejected at production scale due to latency, lock contention, and operational fragility. Apache Kafka's "exactly-once semantics" (EOS) is itself transactional at-least-once with idempotent producers scoped to the Kafka broker; it does not extend across the consumer's database writes.

**The standard pattern used in production (Stripe, Uber, and this plan):**
1. Each `DomainEvent` carries a stable `event_id` (UUID, set at creation time, never regenerated on retry).
2. The `OutboxRelay` publishes with `XADD` and marks rows `sent` in `event_outbox` — if it crashes between the two, the row is re-published on the next poll cycle.
3. Each consumer checks `event_id` against a `processed_events` table (or an idempotency column on the target row) before executing side effects. If already processed, it skips and acknowledges.
4. The consumer's `processed_events` INSERT and the business write happen in the same database transaction.

This gives effectively exactly-once **business outcomes** with at-least-once **message delivery** — which is what the SRE agent actually needs.

### Decision 6: SLO thresholds for store splits

The following gates are based on TimescaleDB production benchmarks, pgvector HNSW benchmark data, and PostgreSQL community operational guidance. Crossing any gate triggers an architecture review, not an automatic migration.

**pgvector → dedicated vector store (Pinecone / Weaviate)**

| Metric | Threshold | Measurement method |
|---|---|---|
| Total vector count | > 2M embeddings | `SELECT count(*) FROM vector_embeddings` |
| p95 search latency | > 50ms sustained over 1h | Prometheus `sre_agent_db_query_duration_seconds{table="vector_embeddings",quantile="0.95"}` |
| HNSW build time | > 10 min for full index rebuild | Measured during maintenance window |

**TimescaleDB (shared) → dedicated TimescaleDB node**

| Metric | Threshold | Measurement method |
|---|---|---|
| Active metric series | > 50M | TimescaleDB `timescaledb_information.chunks` cardinality estimate |
| p99 ingest latency | > 500ms sustained over 5m | Prometheus histogram on `telemetry_metrics` INSERT |
| Hypertable chunk count | > 10,000 | `SELECT count(*) FROM timescaledb_information.chunks` |
| Shared PostgreSQL I/O wait | > 20% CPU time consistently | `pg_stat_activity` I/O wait ratio |

**Redis → dedicated Redis cluster or NATS JetStream**

| Metric | Threshold | Measurement method |
|---|---|---|
| `domain_events` stream consumer lag | > 10,000 messages sustained > 15m | `XINFO GROUPS domain_events` pending count |
| Redis memory utilisation | > 75% of `maxmemory` | Prometheus `redis_memory_used_bytes / redis_memory_max_bytes` |
| Redis CPU | > 60% sustained over 5m | `redis_cpu_sys_seconds_total` rate |

---

## Table of Contents

0. [Architecture Authority and Resolved Decisions](#architecture-authority-and-resolved-decisions)
1. [Current State Assessment](#1-current-state-assessment)
2. [What Needs to Be Persisted](#2-what-needs-to-be-persisted)
3. [Industry Research Summary](#3-industry-research-summary)
4. [Architectural Decision Records](#4-architectural-decision-records)
5. [Target Persistence Architecture](#5-target-persistence-architecture)
6. [Data Store Responsibilities](#6-data-store-responsibilities)
7. [Key Patterns](#7-key-patterns)
8. [Schema Design](#8-schema-design)
9. [Migration Roadmap](#9-migration-roadmap)
10. [Operational Considerations](#10-operational-considerations)
11. [What We Deliberately Ruled Out](#11-what-we-deliberately-ruled-out)

---

## 1. Current State Assessment

The agent today has no durable persistence beyond distributed lock state. Every other form of data is either:

- **Ephemeral in-process memory** — diagnostic cache (4h TTL), baseline computation, alert correlation windows.
- **Pending Kafka migration** — the `InMemoryEventStore` in `src/sre_agent/events/in_memory.py` is explicitly marked as a dev placeholder; `aiokafka` is already a listed dependency but the Kafka-backed event store adapter does not exist yet.
- **Embedded and process-local** — ChromaDB is initialised in-process via `chromadb.Client()` in `src/sre_agent/adapters/vectordb/chroma/adapter.py`. Data disappears on process restart unless an explicit persistence path is set.
- **Operationally ready** — Redis/etcd-backed distributed locks (`src/sre_agent/adapters/coordination/redis_lock_manager.py`) are production-grade.

### Persistence gap summary

| Data category | Current storage | Production-ready? |
|---|---|---|
| Domain events (audit trail) | `InMemoryEventStore` | No — ephemeral |
| Incident / alert records | None | No — not implemented |
| Diagnosis results | In-memory `DiagnosticCache` (4h TTL) | No — lost on restart |
| Remediation plans and actions | In-memory + emitted events | No — no queryable history |
| Vector embeddings (RAG knowledge base) | ChromaDB embedded | No — in-process only |
| Anomaly detection baselines | In-memory computation | No — recomputed each startup |
| Metrics snapshots (for correlation) | None | No — not persisted |
| Distributed locks and cooldowns | Redis / etcd | **Yes** |
| Prometheus operational metrics | Prometheus scrape | **Yes** (ephemeral by design) |

---

## 2. What Needs to Be Persisted

Based on a full read of the domain models (`canonical.py`, `diagnosis.py`, `remediation/models.py`) and the incident lifecycle, the data divides into four categories with different access patterns:

### 2.1 Incident lifecycle and audit data
**Source:** `DomainEvent`, `AnomalyAlert`, `Diagnosis`, `RemediationPlan`, `RemediationAction`, `AuditEntry`
**Access pattern:** Write-once (immutable events), read for postmortems, dashboards, and compliance audits. Low-to-moderate volume (hundreds to thousands per day).
**Dominant need:** Durability, queryability, and immutability of the audit log.

### 2.2 Operational state (mutable projections)
**Source:** Current incident status, active remediation plans, severity overrides, kill-switch state, agent lock state
**Access pattern:** Frequent reads (every API call), occasional writes (state transitions).
**Dominant need:** Consistency, low latency, transactional integrity.

### 2.3 Intelligence context (RAG / vector embeddings)
**Source:** Runbook embeddings, incident pattern embeddings, evidence citations from `EvidenceCitation` model
**Access pattern:** Batch writes during knowledge base ingestion, high-frequency similarity searches during active diagnosis.
**Dominant need:** Efficient ANN (approximate nearest neighbour) search, moderate durability.

### 2.4 Time-series signal data (anomaly detection inputs)
**Source:** `CanonicalMetric` snapshots, computed baselines, detection thresholds
**Access pattern:** High-frequency writes at scrape intervals; time-windowed range queries for baseline computation and correlation.
**Dominant need:** Write throughput, time-range query performance, data compression.

---

## 3. Industry Research Summary

Research against Datadog, Uber, Netflix, Cloudflare, FireHydrant, PagerDuty, incident.io, and the LangGraph/CrewAI/AutoGen agent frameworks produced the following high-signal findings directly applicable to this project.

### 3.1 SRE and incident management platforms

**FireHydrant and incident.io** (two of the most modern incident management platforms) both converge on the same persistence pattern:
- A **mutable projection table** (`incidents`) holding current state.
- An **append-only event log table** (`incident_events`) holding every state transition, action, and annotation — never updated or deleted.
- JSONB payload columns for flexibility without migration overhead on every new event type.
- PostgreSQL as the substrate — relational for queryability, JSONB for schema flexibility.

**PagerDuty** exposes audit trail data as a first-class API entity. The internal model is structurally equivalent: a state machine projection + an immutable log.

### 3.2 Time-series at scale

Platforms at Uber-scale (500M metrics/second) build custom engines in Rust or Go. At the scale of this SRE agent (10k–1M time-series, 15s scrape interval), **TimescaleDB** — the PostgreSQL extension for time-series — is the correct choice:
- Native PromQL-compatible storage via Prometheus remote write.
- Hypertable partitioning handles time-range queries efficiently.
- Continuous aggregates replace manual baseline windowing.
- Stays within the PostgreSQL operational surface: one engine, one backup procedure, one connection pool.

VictoriaMetrics is the correct upgrade path if write volume genuinely exceeds TimescaleDB's single-node ceiling (~50M active series). There is no need to plan for it now.

### 3.3 AI agent memory and RAG persistence

**LangGraph** (the production-grade agent framework as of 2025) uses two separate stores:
- `PostgresSaver` for **checkpoint storage** — delta-only writes of graph state per execution step, enabling time-travel replay and human-in-the-loop suspension.
- A separate **long-term vector store** (pgvector, MongoDB, or ChromaDB) for cross-session semantic recall.

The `DiagnosticCache` in this codebase maps directly to LangGraph's short-term checkpoint concept. The ChromaDB adapter maps to LangGraph's long-term vector store concept. The architecture is already correctly separated at the port level; only the backing implementations need upgrading.

**pgvector** (PostgreSQL extension) collapses the ChromaDB dependency into PostgreSQL for moderate embedding scales (up to ~1M vectors with HNSW indexing). This is significant: it means the vector store, incident data, and operational state can all live in one PostgreSQL instance with one backup procedure.

### 3.4 Queue placement

The research finding here is precise: a message queue in front of the database is justified when write volume exceeds database sustain rate, multiple downstream consumers need fan-out, or producers must never block on database backpressure.

**For this SRE agent:**
- Incident event volume is low (thousands per day). Direct PostgreSQL writes via asyncpg are appropriate.
- Redis is already in the stack for locks and cooldowns. **Redis Streams** provides a write buffer and fan-out mechanism for high-frequency events (e.g., continuous metric snapshots) without adding a second message bus.
- Full Kafka is appropriate only if this becomes a multi-tenant SaaS product with independent teams producing events at high volume. It is premature now.

### 3.5 The Node.js persistence microservice question

The user proposed a separate Node.js application as a persistence layer. Industry research produces a clear verdict: **this is the correct pattern for multi-language producer environments, and the wrong pattern for single-language stacks.**

The data service pattern (a microservice owning a database and exposing it via a typed API) exists at Netflix, Stripe, and Cloudflare — but in each case, the data service *is* the domain service. It is not a persistence proxy layer in front of a database that another service also owns. Introducing a Node.js sidecar would add:
- A network hop on every write (1–5ms latency penalty).
- A second deployment, failure domain, and runbook.
- JSON serialization/deserialization overhead on a Python→HTTP→Node.js→PostgreSQL path.
- No meaningful throughput benefit: `asyncpg` (the Python async PostgreSQL driver) achieves 50k+ inserts per second in a single async process, which exceeds incident management write requirements by three orders of magnitude.

The Node.js BFF pattern is appropriate if a React or Next.js frontend needs a server-side aggregation layer. It is not appropriate as a persistence proxy for a Python FastAPI backend. **Write directly from Python/FastAPI to PostgreSQL using asyncpg.**

---

## 4. Architectural Decision Records

### ADR-001: PostgreSQL as the primary operational store
**Decision:** Use PostgreSQL (with the TimescaleDB and pgvector extensions) as the single primary durable store for incident data, operational state, agent audit logs, and vector embeddings at current scale.

**Rationale:**
- One engine, one operational surface, one backup procedure.
- TimescaleDB extension handles time-series without a separate TSDB.
- pgvector extension handles similarity search without a separate vector database.
- `asyncpg` provides production-grade async Python connectivity.
- Mature ecosystem, well-understood operationally, trivially hosted on AWS RDS or Google Cloud SQL.

**Consequences:** If vector search performance degrades past ~2M embeddings, or metrics write volume exceeds ~50M active series, a targeted migration to a dedicated store (Pinecone, VictoriaMetrics) is straightforward because the `VectorStorePort` and `BaselineQuery` ports already abstract the backing implementation.

---

### ADR-002: Append-only event log with mutable projection
**Decision:** Persist domain events to an append-only `incident_events` table. Never UPDATE or DELETE rows in this table. Maintain a separate `incidents` table as a mutable current-state projection.

**Rationale:**
- Satisfies the existing `EventStore.append()` contract defined in `src/sre_agent/ports/events.py`.
- The `InMemoryEventStore` is already append-only (`§1.5 — append-only constraint` comment in the source). This pattern formalises that constraint in the database schema.
- Provides a complete postmortem audit trail: every status change, severity override, remediation execution, and human override is permanently recorded with actor, timestamp, and structured payload.
- Aligns with FireHydrant and PagerDuty's internal architecture.
- No full CQRS complexity required: projections are updated in the same transaction as event appends via PostgreSQL triggers or application-layer handlers.

---

### ADR-003: Outbox pattern for reliable event publishing
**Decision:** Use the transactional outbox pattern for publishing domain events to Redis Streams or any future message bus.

**Rationale:**
- The current `InMemoryEventBus` has no delivery guarantees across process restarts or failures.
- Dual-write bugs (database write succeeds, event publish fails) corrupt the audit trail.
- The outbox pattern: write the event to both `incident_events` and `event_outbox` in a single PostgreSQL transaction. A background relay worker (`OutboxRelay`) polls committed `pending` rows (PostgreSQL `READ COMMITTED` isolation — only committed rows are visible) and publishes them to Redis Streams, then marks them `sent`.
- Delivery guarantee: **at-least-once to Redis Streams**. The relay may publish a row more than once if it crashes between `XADD` and updating `event_outbox` status. Consumers must be idempotent: deduplicate on `event_id` before side-effecting (check-and-skip if already processed). This is the standard industry model — see Section 4 decision log.

---

### ADR-004: Redis Streams as the internal event bus
**Decision:** Replace `InMemoryEventBus` with a Redis Streams-backed implementation for production.

**Rationale:**
- Redis is already mandatory infrastructure (lock manager, cooldown keys).
- Redis Streams handles 100k+ events/second on a single node — orders of magnitude beyond SRE agent event volume.
- Consumer groups provide exactly the fan-out model needed for multi-subscriber event handling (e.g., diagnosis pipeline subscribes to `anomaly.detected`; metrics pipeline subscribes to `remediation.completed`).
- Zero additional operational surface area vs. Kafka, which would require ZooKeeper or KRaft, broker management, topic partitioning strategy, and consumer group lag monitoring.

---

### ADR-005: Keep ChromaDB for development; use pgvector in production
**Decision:** Retain ChromaDB as the default adapter in local development (already present, zero-config). Implement a `pgvector` adapter under `src/sre_agent/adapters/vectordb/pgvector/` for production deployments.

**Rationale:**
- The `VectorStorePort` already abstracts the backing implementation. Swapping ChromaDB for pgvector requires implementing the port interface and updating config — no domain logic changes.
- pgvector HNSW indexing is sufficient for up to ~1–2M embeddings with sub-10ms query latency.
- Eliminates a separate ChromaDB process in production.
- Consolidates backups: embeddings backed up with the rest of the PostgreSQL data.

---

### ADR-006: No separate Node.js persistence service
**Decision:** Do not introduce a Node.js (or any other language) microservice as a persistence proxy layer.

**Rationale:** See [Section 3.5](#35-the-nodejs-persistence-microservice-question). Direct asyncpg writes from Python/FastAPI are the correct architecture for a single-language stack. The data service pattern is about domain service ownership, not persistence proxying.

---

## 5. Target Persistence Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        SRE Agent (FastAPI / anyio)                       │
│                                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐ │
│  │  Detection   │  │ Intelligence │  │ Remediation  │  │   API/CLI   │ │
│  │    Domain    │  │    Domain    │  │    Domain    │  │   Layer     │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬──────┘ │
│         │                 │                  │                  │        │
│         └─────────────────┴──────────────────┴──────────────────┘        │
│                                    │                                     │
│                          ┌─────────▼──────────┐                         │
│                          │   Port Interfaces   │                         │
│                          │  EventStore         │                         │
│                          │  EventBus           │                         │
│                          │  VectorStorePort    │                         │
│                          │  BaselineQuery      │                         │
│                          └─────────┬──────────┘                         │
└────────────────────────────────────┼────────────────────────────────────┘
                                     │
             ┌───────────────────────┼───────────────────────┐
             │                       │                       │
             ▼                       ▼                       ▼
  ┌──────────────────┐    ┌──────────────────┐   ┌──────────────────────┐
  │   PostgreSQL 16  │    │   Redis 7        │   │   TimescaleDB        │
  │   + pgvector     │    │   (existing)     │   │   (PG extension)     │
  │                  │    │                  │   │                      │
    │  incidents          │    │  Locks           │   │  telemetry_metrics   │
    │  incident_events    │    │  Cooldowns       │   │  detection_baselines │
    │  diagnosis_results  │    │  Kill switch     │   │  anomaly_alerts_ts   │
    │  remediations       │    │  DiagCache TTL   │   │                      │
    │  coordination_audit │    │                  │   │  (continuous agg.    │
    │  vector_embeddings  │    │  Streams:        │   │   for baselines)     │
    │  event_outbox       │    │  domain_events   │   │                      │
    │  agent_runs         │    │  (event bus)     │   └──────────────────────┘
  │  tool_calls      │    │                  │
  │  retrieved_ctx   │    │  (outbox relay   │
  │                  │    │   publishes here)│
  └──────────────────┘    └──────────────────┘
```

### Component mapping

| Application component | Target store | Adapter location |
|---|---|---|
| `InMemoryEventStore` | PostgreSQL `incident_events` table | `adapters/persistence/incident_store.py` |
| `InMemoryEventBus` | Redis Streams | `adapters/events/redis_event_bus.py` |
| `DiagnosticCache` | Redis with TTL | `adapters/cache/redis_diagnostic_cache.py` |
| `ChromaVectorStoreAdapter` (production) | PostgreSQL + pgvector | `adapters/vectordb/pgvector/adapter.py` |
| Baseline computation (in-memory) | TimescaleDB continuous aggregates | `adapters/telemetry/timescale/baseline_adapter.py` |
| Incident state (none today) | PostgreSQL `incidents` projection table | `adapters/persistence/incident_store.py` |
| Agent reasoning traces (none today) | PostgreSQL `agent_runs` + `tool_calls` | `adapters/persistence/postgres_agent_run_store.py` |

---

## 6. Data Store Responsibilities

### 6.1 PostgreSQL (primary durable store)

**Owns:** Everything that must survive process restarts and be queryable.

- **Incident lifecycle data:** `incidents` (mutable projection), `incident_events` (append-only log), `diagnosis_results`, `remediation_plans`, `remediation_actions`.
- **Audit trail:** `coordination_audit` — immutable record of every agent action, human override, kill-switch activation, and severity change. Directly maps to `AuditEntry` model.
- **Agent intelligence traces:** `agent_runs`, `tool_calls`, `retrieved_contexts`, `reasoning_steps` — structured audit for every LLM call, tool invocation, and evidence retrieval. Required for postmortem analysis ("why did the agent restart that pod?").
- **Vector embeddings:** `vector_embeddings` table via pgvector HNSW index. Replaces ChromaDB in production.
- **Outbox table:** `event_outbox` transient staging for events awaiting relay to Redis Streams.

**Not responsible for:** Sub-second TTL state (use Redis), raw metric streams (use TimescaleDB), or ephemeral per-request context (use in-process memory).

---

### 6.2 TimescaleDB (PostgreSQL extension — same instance or dedicated)

**Owns:** Time-ordered numerical data with high write rates and time-range query patterns.

- **`telemetry_metrics`:** Stores `CanonicalMetric` values as they arrive from telemetry adapters — the raw material for anomaly detection. Hypertable partitioned by time.
- **`detection_baselines`:** Continuous aggregate over `telemetry_metrics` computing rolling mean and standard deviation. Replaces the in-memory `BaselineStorage` class. The `BaselineQuery` port implementation reads from this table.
- **`anomaly_alerts_ts`:** Time-series copy of alert events for correlation window queries.

**Decision point:** Start with TimescaleDB as an extension on the same PostgreSQL instance. The operational surface does not change. Migrate to a dedicated TimescaleDB node or VictoriaMetrics only when:
- Active metric series exceed 10M, OR
- TimescaleDB write latency degrades below SLO on the shared instance.

---

### 6.3 Redis (existing — extended responsibilities)

**Owns:** Ephemeral coordination state and low-latency caching.

**Existing (do not change):**
- Distributed lock keys with fencing tokens (`sre-agent:lock:…`).
- Cooldown keys with TTL (`cooldown:{provider}:{compute_mechanism}:{resource_id}`) — exact token matches `AGENTS.md:125`.
- Kill-switch flag.

**New responsibilities:**
- **`DiagnosticCache`:** Move the in-memory `DiagnosticCache` to Redis with the existing 4h TTL. Key: `diagcache:{service}:{anomaly_type}:{metric_name}`. This survives agent restarts and is shared across agent replicas.
- **Redis Streams (`domain_events` stream):** Replace `InMemoryEventBus`. Producers call `XADD`, consumers use consumer groups. The outbox relay worker is the sole producer; domain event handlers are consumers.

---

### 6.4 ChromaDB (development only)

Retained as the default `VectorStorePort` implementation when `VECTOR_STORE_BACKEND=chroma` (the existing default). No changes to the existing adapter. In production, set `VECTOR_STORE_BACKEND=pgvector`.

---

## 7. Key Patterns

### 7.1 Transactional outbox

This pattern prevents the dual-write bug between database persistence and event bus publication.

```
┌────────────────────────────────────────────────────────────────┐
│  Application (e.g., DiagnosisService.run_diagnosis())          │
│                                                                 │
│  BEGIN TRANSACTION                                              │
│    INSERT INTO diagnosis_results (...) -- persist state        │
│    INSERT INTO incident_events (...)  -- append to audit log   │
│    INSERT INTO event_outbox (event_id, topic, payload_json, status='pending') │
│  COMMIT                                                         │
│                                                                 │
│  ← transaction commits atomically or rolls back entirely       │
└──────────────────────────────┬─────────────────────────────────┘
                               │  (async)
                    ┌──────────▼──────────┐
                    │   OutboxRelay        │
                    │   (background task) │
                    │                     │
                    │  Poll event_outbox  │
                    │  WHERE status='pending' │
                    │  XADD → Redis Stream│
                    │  UPDATE status='sent' │
                    └─────────────────────┘
```

The outbox relay runs as an `anyio` background task inside the FastAPI lifespan. It is deliberately simple: poll interval of 100ms, persisted retry counters, and DLQ transition (`status='dlq'`, `dlq_at`, `dlq_reason`) after exhaustion.

---

### 7.2 Append-only event log with mutable projection

```sql
-- Append-only: never UPDATE or DELETE
CREATE TABLE incident_events (
    event_id         UUID PRIMARY KEY,
    incident_id      UUID NOT NULL,
    event_type       TEXT NOT NULL,           -- e.g. 'remediation.started'
    payload_json     JSONB NOT NULL,
    idempotency_key  TEXT NOT NULL UNIQUE,
    occurred_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON incident_events (incident_id, occurred_at ASC);

-- Mutable projection: reflects current state
CREATE TABLE incidents (
    incident_id      UUID PRIMARY KEY,
    service          TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'open',   -- open, mitigating, resolved
    severity         TEXT,
    opened_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at        TIMESTAMPTZ,
    latest_event_id  UUID NOT NULL,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Application-layer handlers (subscribers to `ANOMALY_DETECTED`, `REMEDIATION_COMPLETED`, etc.) update the `incidents` projection in the same transaction that appends to `incident_events`.

---

### 7.3 Agent reasoning trace schema

Provides the "why did the agent do this?" answer required by postmortems and the human supremacy principle in `AGENTS.md`.

```sql
CREATE TABLE agent_runs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID REFERENCES incidents(id),
    agent_id    TEXT NOT NULL,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at    TIMESTAMPTZ,
    outcome     TEXT,   -- 'success', 'failed', 'aborted_by_human'
    metadata    JSONB
);

-- Every LLM call within a run
CREATE TABLE tool_calls (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id      UUID NOT NULL REFERENCES agent_runs(id),
    tool_name   TEXT NOT NULL,
    input       JSONB NOT NULL,
    output      JSONB,
    latency_ms  INTEGER,
    status      TEXT NOT NULL,  -- 'success', 'error', 'timeout'
    called_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Evidence retrieved from vector store per diagnosis
CREATE TABLE retrieved_contexts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID NOT NULL REFERENCES agent_runs(id),
    doc_id          TEXT NOT NULL,
    similarity_score FLOAT NOT NULL,
    content_snippet TEXT,
    source          TEXT,
    retrieved_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

### 7.4 Vector store schema (pgvector)

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE vector_embeddings (
    embedding_id    UUID PRIMARY KEY,
    source_type     TEXT NOT NULL,
    source_id       TEXT NOT NULL,
    embedding       vector(1536),
    embedding_json  JSONB,
    metadata_json   JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    embedding_dim   INTEGER GENERATED ALWAYS AS (
        CASE
            WHEN embedding IS NOT NULL THEN vector_dims(embedding)
            WHEN embedding_json IS NOT NULL THEN jsonb_array_length(embedding_json)
            ELSE 0
        END
    ) STORED
);

-- HNSW index: fast approximate nearest-neighbour search
CREATE INDEX ON vector_embeddings USING hnsw (embedding vector_cosine_ops)
    WITH (m = 24, ef_construction = 200);
```

The `pgvector` adapter implements `VectorStorePort` using `asyncpg` for connection management. The `search()` method maps to `ORDER BY embedding <=> $1 LIMIT $2` with an optional metadata filter applied as a `WHERE metadata_json @> $3` clause.

---

## 8. Schema Design

### 8.1 Full table inventory

| Table | Store | Type | Maps to model |
|---|---|---|---|
| `incidents` | PostgreSQL | Mutable projection | `AnomalyAlert` + lifecycle state |
| `incident_events` | PostgreSQL | Append-only log | `DomainEvent` |
| `diagnosis_results` | PostgreSQL | Mutable + versioned | `Diagnosis` |
| `remediation_plans` | PostgreSQL | Mutable | `RemediationPlan` |
| `remediation_actions` | PostgreSQL | Mutable | `RemediationAction` |
| `coordination_audit` | PostgreSQL | Append-only | `AuditEntry` |
| `agent_runs` | PostgreSQL | Mutable | (new) |
| `tool_calls` | PostgreSQL | Append-only | (new) |
| `retrieved_contexts` | PostgreSQL | Append-only | `EvidenceCitation` |
| `vector_embeddings` | PostgreSQL (pgvector) | Mutable | `VectorDocument` |
| `event_outbox` | PostgreSQL | Transient (status-tracked) | Internal |
| `telemetry_metrics` | TimescaleDB hypertable | Append-only | `CanonicalMetric` |
| `detection_baselines` | TimescaleDB cont. aggregate | Derived | `BaselineStorage` |
| `domain_events` stream | Redis Streams | TTL-bounded | `DomainEvent` (bus) |
| `diagcache:*` | Redis (HASH + TTL) | Cache | `DiagnosticCache` |
| `sre-agent:lock:*` | Redis (existing) | TTL key | `LockRequest` |
| `cooldown:*` | Redis (existing) | TTL key | Cooldown protocol |

---

### 8.2 TimescaleDB telemetry metrics

```sql
CREATE TABLE telemetry_metrics (
    ts              TIMESTAMPTZ NOT NULL,
    service         TEXT NOT NULL,
    metric_name     TEXT NOT NULL,
    value           DOUBLE PRECISION NOT NULL,
    labels_json     JSONB NOT NULL,
    label_hash      TEXT NOT NULL
);

-- TimescaleDB hypertable: partitioned by time, 1-day chunks
SELECT create_hypertable('telemetry_metrics', 'ts', chunk_time_interval => INTERVAL '1 day');
CREATE INDEX ON telemetry_metrics (service, metric_name, ts DESC);

-- Continuous aggregate: 5-minute rolling baseline
CREATE MATERIALIZED VIEW metric_baselines
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('5 minutes', ts) AS bucket,
    service,
    metric_name,
    AVG(value) AS mean,
    STDDEV(value) AS stddev,
    COUNT(*) AS sample_count
FROM telemetry_metrics
GROUP BY bucket, service, metric_name;
```

The `BaselineQuery` port adapts this continuous aggregate view. `query_baseline()` selects from `metric_baselines` by `(service, metric_name)` and returns the latest bucket's `(mean, stddev)`. Deviation calculation (`(current - mean) / stddev`) moves from in-process Python to a SQL expression, keeping the domain logic clean.

---

## 9. Migration Roadmap

### Phase 0 — Foundation (prerequisite, no behavioural change)

1. Add Alembic for database migrations: `alembic init alembic/`.
2. Add `asyncpg`, `sqlalchemy[asyncio]`, and `alembic` to `pyproject.toml` core dependencies.
3. Add `pgvector` Python package to `[intelligence]` optional dependencies.
4. Add TimescaleDB to `docker-compose.deps.yml` (or enable it as a PostgreSQL extension).
5. Add `DATABASE_URL` to `.env.example`.
6. Create `src/sre_agent/config/settings.py` database config block:
   ```python
   class DatabaseConfig:
       url: str = "postgresql+asyncpg://sre_agent:password@localhost/sre_agent"
       pool_size: int = 10
       vector_store_backend: Literal["chroma", "pgvector"] = "chroma"
   ```

---

### Phase 1 — Event persistence (replaces InMemoryEventStore)

**Target:** Durable audit trail for all `DomainEvent` instances.

1. Implement Alembic migration: create `incidents`, `incident_events`, `event_outbox` tables.
2. Implement `PostgresIncidentStore` adapter in `src/sre_agent/adapters/persistence/incident_store.py`.
   - `append(event)` → INSERT into `incident_events` + INSERT into `event_outbox` in one transaction.
   - `get_events(aggregate_id, event_types)` → SELECT from `incident_events`.
3. Implement `RedisEventBus` adapter in `src/sre_agent/adapters/events/redis_event_bus.py`.
   - `publish(event)` → `XADD domain_events * …`
   - `subscribe(event_type, handler)` → consumer group read loop.
4. Implement `PostgresOutboxStore` and `OutboxRelay` in `src/sre_agent/adapters/persistence/postgres_outbox.py` and `src/sre_agent/adapters/persistence/outbox_relay.py`.
5. Wire new adapters through `src/sre_agent/config/bootstrap.py` behind `USE_POSTGRES_EVENTS=true` feature flag.
6. Unit tests: mock PostgreSQL via `pytest-asyncio` + testcontainers. Integration tests against real PostgreSQL via Docker Compose.

---

### Phase 2 — Operational state persistence

**Target:** Queryable incident history that survives restarts.

1. Alembic migration: create `diagnosis_results`, `remediation_plans`, `remediation_actions`, `coordination_audit` tables.
2. Implement `PostgresIncidentStore` adapter. Expose via a new `IncidentStorePort` in `src/sre_agent/ports/incident_store.py`.
3. Update `DiagnosticsService` to write `Diagnosis` records after each successful RAG pipeline run.
4. Update `RemediationExecutor` to write `RemediationPlan` and `RemediationAction` records.
5. Expose read API: add `GET /incidents`, `GET /incidents/{id}`, `GET /incidents/{id}/events` to `rest/` routers.

---

### Phase 3 — Intelligence trace persistence

**Target:** Full audit of agent reasoning for postmortem and compliance.

1. Alembic migration: create `agent_runs`, `tool_calls`, `retrieved_contexts` tables.
2. Implement `PostgresAgentRunStore` adapter.
3. Instrument `DiagnosticsService.diagnose()` to open an `agent_run` record, log each LLM call as a `tool_call` row, and log each retrieved document as a `retrieved_context` row.
4. Expose read API: `GET /agent-runs/{id}` showing full reasoning trace.

---

### Phase 4 — Diagnostic cache externalisation

**Target:** Diagnosis results shared across agent replicas and survived across restarts.

1. Implement `RedisDiagnosticCache` adapter in `src/sre_agent/adapters/cache/redis_diagnostic_cache.py`.
   - Uses `HSET` with `EXPIRE` matching existing 4h TTL.
   - Key format: `diagcache:{service}:{anomaly_type}:{metric_name}`.
2. Replace `DiagnosticCache` instantiation in bootstrap to use the Redis adapter when Redis is configured.
3. No changes to `DiagnosticsService` — it interacts via the existing cache interface.

---

### Phase 5 — Vector store production upgrade

**Target:** Durable, production-grade vector embeddings without a separate ChromaDB process.

1. Alembic migration: `CREATE EXTENSION vector`, create `vector_embeddings` table with HNSW index.
2. Implement `PgvectorAdapter` in `src/sre_agent/adapters/vectordb/pgvector/adapter.py` implementing `VectorStorePort`.
3. Add `VECTOR_STORE_BACKEND=pgvector` to production `.env`.
4. Migrate existing ChromaDB embeddings via a one-time CLI script: `scripts/migrate_chroma_to_pgvector.py`.

---

### Phase 6 — Time-series metrics persistence

**Target:** Persistent anomaly detection baselines; query-able metric history for incident correlation.

1. Enable TimescaleDB extension on PostgreSQL instance.
2. Alembic migration: create `telemetry_metrics` hypertable, `metric_baselines` continuous aggregate, `anomaly_alerts_ts` hypertable.
3. Implement `TimescaleBaselineAdapter` replacing in-memory `BaselineStorage`.
4. Add telemetry ingestion path: `CanonicalMetric` objects written to `telemetry_metrics` after each telemetry poll cycle.
5. Update `DetectionConfig` thresholds to be persisted and editable via API.

---

## 10. Operational Considerations

### Connection pooling
Use a shared `asyncpg` connection pool (via SQLAlchemy async engine) with `pool_size=10` (configurable). All adapters receive the pool via dependency injection at bootstrap time — not created per-request.

### Database migrations
All schema changes go through Alembic migration files committed to `alembic/versions/`. No manual DDL in production. The FastAPI application runs `alembic upgrade head` on startup in non-production environments; production uses a pre-deploy migration job.

### Retention policy
| Data | Retention | Mechanism |
|---|---|---|
| `telemetry_metrics` | 90 days | TimescaleDB `add_retention_policy` |
| `incident_events` | 2 years | Application-level archive to S3 Parquet |
| `coordination_audit` | 7 years | Application-level archive to S3 Parquet (compliance) |
| `diagnosis_results`, `remediation_*` | 1 year | Soft-delete (archived flag) |
| `agent_runs`, `tool_calls` | 180 days | Scheduled DELETE job |
| `retrieved_contexts` | 180 days | Scheduled DELETE job |
| `vector_embeddings` | Indefinite | Manual curation |
| Redis Streams (`domain_events`) | 7 days maxlen | `MAXLEN ~10000` on stream |
| Redis diagnostic cache | 4 hours | `EXPIRE` per key |

### Backup
PostgreSQL: continuous WAL archiving to S3 via pgBackRest or managed service (AWS RDS automated backups). Point-in-time recovery target: 1-hour RPO.
Redis: RDB snapshot every 15 minutes + AOF enabled. AOF sync policy: `everysec`.

### Observability
Add the following Prometheus metrics to `src/sre_agent/observability/metrics.py`:
- `sre_agent_db_query_duration_seconds` (Histogram) — labels: `table`, `operation`
- `sre_agent_db_pool_active_connections` (Gauge)
- `sre_agent_outbox_pending_rows` (Gauge) — alert if > 1000 for > 5 minutes
- `sre_agent_redis_stream_lag` (Gauge) — per consumer group

### Testing strategy
- **Unit tests:** Use `pytest-asyncio` + `unittest.mock` to mock database calls. No real database required.
- **Integration tests:** Use `testcontainers` (already implied by existing Docker Compose test infrastructure) to spin up PostgreSQL + Redis for each test run.
- **Migration tests:** CI pipeline runs `alembic upgrade head` against a clean database on every PR touching `alembic/versions/`.
- **Coverage:** Maintain ≥ 90% per existing `pyproject.toml` policy.

---

## 11. What We Deliberately Ruled Out

| Option | Reason rejected |
|---|---|
| **Node.js persistence service** | Single-language Python stack; asyncpg matches throughput requirements with zero additional operational surface. Network hop adds 1–5ms latency with no benefit. |
| **Kafka** | Operational complexity (broker management, partition strategy, consumer group lag) not justified at current event volume (thousands/day). Redis Streams is sufficient and already operational. Revisit at multi-tenant SaaS scale. |
| **InfluxDB / InfluxDB IOx** | Flux query language lock-in; TimescaleDB gives equivalent time-series features with standard SQL and stays within the PostgreSQL operational boundary. |
| **MongoDB** | No clear access pattern advantage over PostgreSQL + JSONB for incident data; adds a second operational surface area. |
| **Full CQRS / EventStoreDB** | Projection rebuild complexity and event versioning overhead not justified for current team size. Lightweight append-only log + mutable projection achieves the same audit trail guarantees with far less complexity. |
| **VictoriaMetrics** | Correct upgrade path for >50M active series; premature at current scale. Re-evaluate if TimescaleDB write latency degrades. |
| **ClickHouse** | Powerful for log analytics at Cloudflare scale. Not justified until log query volume produces measurable latency issues against PostgreSQL. |
| **Pinecone / Weaviate** | External managed services add vendor coupling; pgvector on PostgreSQL provides equivalent ANN search at current embedding scale with no additional service to manage. |
| **Separate TimescaleDB instance** | Start co-located as a PostgreSQL extension. Split only if metric write volume causes I/O contention on the shared instance. |
