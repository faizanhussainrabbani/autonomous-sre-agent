# Research: SREAgent Persistence Test Coverage and Architecture Documentation

**Date:** 2026-05-28
**Status:** Complete
**Researcher:** Researcher Subagent

---

## 1. Test File Inventory

### 1.1 Unit Tests — Persistence (`tests/unit/adapters/persistence/`)

| File | Adapter Under Test | Key Tests |
|---|---|---|
| `test_incident_store.py` | `PostgresIncidentStore` | `save_event_inserts_event_and_outbox_rows`, `save_event_passes_correct_event_id`, `save_event_includes_idempotency_key`, `save_event_outbox_payload_is_valid_json`, `save_event_raises_duplicate_event_error_on_unique_violation`, `get_events_by_incident_returns_in_chronological_order`, `get_events_by_incident_returns_empty_list_for_unknown`, `get_incident_returns_correct_record`, `get_incident_returns_none_for_unknown`, `update_projection_upserts_incidents_table`, `update_projection_sets_closed_at_for_resolved_status` |
| `test_coordination_store.py` | `PostgresCoordinationAuditStore` | `test_record_lock_event_includes_all_agents_fields`, `test_record_lock_event_non_kubernetes_provider`, `test_record_lock_event_rejects_invalid_compute_mechanism`, `test_record_lock_event_rejects_invalid_provider`, `test_record_cooldown_uses_compute_mechanism_token`, `test_record_cooldown_kubernetes_provider`, `test_record_override_sets_audit_required_true` |
| `test_outbox_relay.py` | `OutboxRelay` | `test_run_once_uses_claim_pending_not_get_pending`, `test_run_once_publishes_and_marks_sent`, `test_run_once_returns_processed_count`, `test_run_once_returns_zero_when_no_entries`, `test_run_once_releases_claim_on_publish_failure`, `test_run_once_marks_failed_after_max_retries`, `test_run_once_does_not_mark_failed_before_max_retries`, `test_run_once_skips_publish_when_event_already_processed`, `test_run_once_preserves_event_id_from_payload`, `test_run_once_preserves_timestamp_from_payload`, `test_run_once_falls_back_on_missing_event_id` |
| `test_postgres_outbox.py` | `PostgresOutboxStore` | `test_store_implements_outbox_port`, `test_enqueue_inserts_pending_row`, `test_enqueue_passes_correct_event_id`, `test_enqueue_returns_uuid`, `test_mark_sent_updates_status`, `test_mark_failed_updates_status`, `test_mark_dlq_updates_status_and_reason`, `test_is_event_processed_returns_true_when_marker_exists`, `test_is_event_processed_returns_false_when_marker_missing`, `test_mark_event_processed_returns_true_on_insert`, `test_mark_event_processed_returns_false_on_conflict`, `test_get_pending_uses_skip_locked`, `test_get_pending_passes_limit`, `test_get_pending_returns_empty_when_none`, `test_claim_pending_uses_update_returning` |
| `test_reasoning_trace_store.py` | `PostgresReasoningTraceStore` | `test_store_implements_reasoning_trace_port`, `test_start_run_inserts_agent_runs_row`, `test_end_run_updates_outcome_and_end_time`, `test_log_tool_call_persists_payloads`, `test_log_retrieved_context_clamps_similarity`, `test_get_run_returns_record_when_present`, `test_get_run_returns_none_when_missing`, `test_list_runs_by_incident_returns_ordered_rows`, `test_list_tool_calls_maps_json_payloads`, `test_list_retrieved_contexts_maps_rows` |
| `test_remediation_store.py` | `PostgresRemediationStore` | `test_store_implements_remediation_store_port`, `test_save_action_maps_proposed_to_planned`, `test_update_status_preserves_fidelity_statuses`, `test_update_status_rejects_unknown_status` |
| `test_retention_executor.py` | `RetentionExecutor` | `test_run_once_deletes_expected_row_counts`, `test_stop_sets_running_flag_false` |

### 1.2 Unit Tests — VectorDB (`tests/unit/adapters/vectordb/`)

| File | Adapter Under Test | Key Tests |
|---|---|---|
| `test_pgvector_adapter.py` | `PgVectorStoreAdapter` | `test_implements_vector_store_port`, `test_store_inserts_document_pgvector_mode`, `test_store_inserts_document_jsonb_mode`, schema probing (pgvector extension available vs not), cosine similarity computation, search in pgvector vs JSONB fallback, `VECTOR_FALLBACK_TRUNCATED` metric |

### 1.3 Unit Tests — Events (`tests/unit/adapters/events/`)

| File | Adapter Under Test | Key Tests |
|---|---|---|
| `test_redis_streams_event_bus.py` | `RedisStreamsEventBus` | Redis Streams publish/subscribe behavior |

### 1.4 Integration Tests — Persistence (`tests/integration/`)

| File | Scope | Key Tests |
|---|---|---|
| `test_incident_store_integration.py` | Full PostgreSQL lifecycle with `testcontainers` (Postgres 16), migrations 001–007 | `test_save_event_persists_to_incident_events_table`, `test_save_event_atomically_writes_outbox_row`, `test_duplicate_idempotency_key_raises`, `test_get_events_chronological_order`, `test_get_incident_returns_none_when_not_found`, `test_update_projection_sets_closed_at_for_resolved`, `test_migration_005_creates_processed_events_and_dlq_contract`, `test_migration_006_processed_events_fk_is_restrict` |
| `test_schema_migration_008_009_integration.py` | Migrations 008–010 applied to Postgres 16 container | `test_migration_008_creates_retention_and_covering_indexes`, `test_migration_009_is_extension_aware_for_metric_baselines`, `test_migration_010_promotes_partitioned_incident_events` |
| `test_chroma_integration.py` | ChromaDB adapter (in-memory) | `test_store_and_retrieve`, `test_batch_store`, `test_similarity_search_min_score`, `test_delete`, `test_delete_stale` |
| `test_event_sourcing_integration.py` | `InMemoryEventBus` + `InMemoryEventStore` | Phase 2 domain events emitted in order, append-only EventStore, aggregate ID consistency, async subscribers, novel incidents produce INCIDENT_DETECTED events |

---

## 2. Coverage Gaps — Missing Tests

### 2.1 Identified Gaps

| Gap | Description | Risk Level |
|---|---|---|
| **TimescaleDB adapter unit tests** | No unit tests for a `TimescaleBaselineAdapter` (persisting `CanonicalMetric` to hypertable, querying `metric_baselines`). The adapter is planned (Phase 6) but not yet tested. | High (when implemented) |
| **PgVector integration test** | `test_pgvector_adapter.py` is unit-only (FakePool). There is no integration test for `PgVectorStoreAdapter` against a real PostgreSQL+pgvector instance. ChromaDB has an integration test; pgvector does not. | High |
| **Remediation store integration test** | `test_remediation_store.py` is unit-only. No integration test validates `save_action`, `update_status`, and FK constraints in a live database. | Medium |
| **Reasoning trace store integration test** | `test_reasoning_trace_store.py` is unit-only. No integration test validates end-to-end agent_runs, tool_calls, retrieved_contexts against a real database. | Medium |
| **Coordination audit store integration test** | `test_coordination_store.py` is unit-only. No integration test validates the `coordination_audit` table schema or constraints against a real database. | Medium |
| **RetentionExecutor integration test** | Only two trivial unit tests. No integration test checks that real DELETE FROM processed_events and baseline_snapshots operations execute correctly and return accurate row counts. | Medium |
| **OutboxRelay integration test** | `test_outbox_relay.py` uses in-memory fakes only. No integration test validates relay behavior against real PostgreSQL + Redis Streams simultaneously. | High |
| **DiagnosticCache (Redis) unit/integration** | `RedisDiagnosticCache` adapter (Phase 4) has no unit or integration tests visible in the test tree. Current in-memory `DiagnosticCache` is tested implicitly through RAG pipeline tests. | Medium |
| **Migration 007 specific schema test** | The integration test covers migrations 001–007 but does not explicitly verify Migration 007's partition readiness or status fidelity constraints. | Low |
| **`coordination_store.py` preemption scenario** | Tests cover lock/cooldown/override individually but no test covers the full preemption sequence (acquire → preempt by higher-priority → revoke pub/sub). | Low |
| **pgvector HNSW index quality tests** | No test validates that HNSW index is created correctly or that cosine similarity results satisfy recall quality thresholds. | Low |

### 2.2 Deliberately Not Tested (Out of Scope)

Per `persistence_architecture.md` §5 (Decision 5), the following are deferred and thus have no tests:
- Cooldown, kill-switch, and severity-override state persistence (accepted operational gap)

---

## 3. `persistence_architecture.md` — Full Content Summary

**File:** `docs/architecture/persistence_architecture.md`
**Status:** Proposal — v1.1 (2026-04-07)
**Authority:** This document is the persistence authority; supersedes Technology_Stack.md and roadmap.md on all persistence decisions.

### 3.1 Resolved Architectural Decisions

| Decision | Resolution |
|---|---|
| Authoritative persistence document | This file. Roadmap is product-sequencing authority. |
| Production vector backend | **pgvector** (PostgreSQL extension). ChromaDB retained for local dev only. |
| Internal event bus | **Redis Streams** (already mandatory; aiokafka dependency retained for future optionality, not used now). |
| Delivery semantics | **At-least-once + idempotent consumers** (not strict exactly-once). Industry-standard pattern (Stripe, Uber, AWS). |
| Cooldown/kill-switch/severity-override persistence | **Deferred to later wave**. Accepted operational gap: state lost on restart. |
| Store split thresholds | Defined objectively: pgvector → dedicated vector store at >2M embeddings or >50ms p95; TimescaleDB → dedicated at >50M series or >500ms p99; Redis → cluster at >10K message lag sustained >15m or >75% memory. |

### 3.2 Current State at Time of Writing

All persistence beyond Redis distributed locks is ephemeral:
- Domain events: `InMemoryEventStore` (dev placeholder, explicitly marked)
- Incident records: Not implemented
- Diagnosis results: In-memory `DiagnosticCache` (4h TTL, lost on restart)
- Remediation plans: In-memory + emitted events, no queryable history
- Vector embeddings: ChromaDB in-process (disappears on restart unless persistence path set)
- Distributed locks/cooldowns: Redis/etcd — production-ready

### 3.3 Architecture Decisions (ADRs 001–006)

- **ADR-001:** PostgreSQL 16 + TimescaleDB + pgvector as single primary durable store
- **ADR-002:** Append-only `incident_events` + mutable `incidents` projection (FireHydrant/PagerDuty pattern)
- **ADR-003:** Transactional outbox pattern for reliable event publishing to Redis Streams
- **ADR-004:** Redis Streams as the internal event bus (replaces `InMemoryEventBus`)
- **ADR-005:** ChromaDB for dev; pgvector for production (VectorStorePort already abstracts this)
- **ADR-006:** No Node.js persistence proxy (asyncpg direct writes are correct architecture for single-language stack)

### 3.4 Target Architecture: Three Stores

```
PostgreSQL 16 + pgvector:   incidents, incident_events, diagnosis_results,
                            remediation_plans, remediation_actions, coordination_audit,
                            agent_runs, tool_calls, retrieved_contexts,
                            vector_embeddings, event_outbox, processed_events

TimescaleDB (PG extension): telemetry_metrics (hypertable), metric_baselines (continuous agg.)

Redis 7 (existing):         Locks, cooldowns, DiagnosticCache (TTL), domain_events stream
```

### 3.5 Schema Table Inventory (Section 8)

16 tables/objects mapped:
- `incidents` (mutable projection)
- `incident_events` (append-only log)
- `diagnosis_results`, `remediation_plans`, `remediation_actions`, `coordination_audit`
- `agent_runs`, `tool_calls`, `retrieved_contexts`
- `vector_embeddings` (pgvector HNSW)
- `event_outbox`, `processed_events` (dedup markers)
- `telemetry_metrics` (TimescaleDB hypertable)
- `detection_baselines` (TimescaleDB cont. aggregate)
- `domain_events` (Redis Stream)
- `diagcache:*` (Redis HASH + TTL)

### 3.6 Migration Roadmap (Phases 0–6)

| Phase | Description | Status (inferred from tests) |
|---|---|---|
| Phase 0 | Alembic setup, asyncpg, DATABASE_URL | Completed (migrations 001-010 exist) |
| Phase 1 | Event persistence (replaces InMemoryEventStore) | Completed — tested |
| Phase 2 | Operational state (diagnosis, remediation, coordination_audit) | Completed — partial tests |
| Phase 3 | Intelligence trace persistence (agent_runs, tool_calls, retrieved_contexts) | Completed — unit tests exist |
| Phase 4 | Diagnostic cache externalisation to Redis | Not yet (no tests found) |
| Phase 5 | pgvector adapter for production | Partially completed — unit tests exist, no integration test |
| Phase 6 | TimescaleDB metrics persistence | Not yet — no tests found |

### 3.7 Retention Policy

| Data | Retention |
|---|---|
| `telemetry_metrics` | 90 days (TimescaleDB policy) |
| `incident_events` | 2 years (archive to S3 Parquet) |
| `coordination_audit` | 7 years (compliance) |
| `diagnosis_results`, `remediation_*` | 1 year (soft-delete) |
| `agent_runs`, `tool_calls`, `retrieved_contexts` | 180 days (scheduled DELETE) |
| `vector_embeddings` | Indefinite |
| Redis Streams (`domain_events`) | 7 days MAXLEN |
| Redis diagnostic cache | 4 hours EXPIRE |

---

## 4. `system_architecture_with_persistence.md` — Full Content Summary

**File:** `docs/architecture/system_architecture_with_persistence.md`
**Status:** Current target state (post-persistence migration), 2026-04-07

### 4.1 Document Structure

A single multi-band Mermaid flowchart covering:
- **Band 1 — Infrastructure:** Kubernetes, AWS, Azure targets
- **Band 2 — Telemetry Sources:** Prometheus, Jaeger, Loki, CloudWatch, New Relic
- **Band 3 — SRE Agent:** Four sequential stages: Detect → Diagnose → Safety → Remediate, plus `OutboxRelay` and `REST API/CLI`
- **Band 4 — Persistence Layer:** PostgreSQL 16 (operational store + pgvector + TimescaleDB) and Redis 7 (locks, DiagnosticCache, domain_events stream)
- **Band 5 — Coordination:** Human Operator, SecOps Agent (Priority 1), FinOps Agent (Priority 3)

### 4.2 Key Data Flows Documented

- Telemetry → Detection (metrics, traces, logs via PromQL/Jaeger/LogQL/CloudWatch/NerdGraph)
- Detection ↔ TimescaleDB (baseline loop: write CanonicalMetric snapshots; read rolling mean/stddev)
- Intelligence ↔ pgvector (embed query → vector search → top-k EvidenceCitation)
- Intelligence ↔ Redis DiagnosticCache (cache hit avoids LLM call with 4h TTL)
- SRE Agent → PostgreSQL (all operational writes: AnomalyAlert, Diagnosis, RemediationPlan, DomainEvent audit log, reasoning trace, outbox staging)
- OutboxRelay → Redis Stream (at-least-once XADD from committed PENDING rows)
- Redis Stream → SRE Agent (event-driven fan-out: anomaly.detected triggers Intelligence; remediation.approved triggers Executor)
- Safety ↔ Redis (lock/cooldown/kill-switch enforcement)
- Coordination ↔ Redis (multi-agent lock protocol, human kill-switch)
- API ↔ PostgreSQL (read incidents, audit trail, reasoning traces)

---

## 5. `docs/architecture/overview.md` — Persistence-Related Content

The overview is a **high-level conceptual document** (no explicit persistence section). Key references:

- Lists "Eventing and telemetry adapters for observability ingestion and audit trails" as a primary component
- Detection to remediation flow mentions step 6: "Post-action validation confirms service recovery or triggers rollback controls"
- Integration boundary principle: "Domain code depends on ports, not concrete provider SDKs" — directly applies to persistence ports
- No mention of PostgreSQL, Redis, or specific persistence stores by name

**Assessment:** The overview is intentionally abstract; `persistence_architecture.md` is the authoritative persistence reference.

---

## 6. `master_system_document.md` — Persistence-Related Content

**File length:** 922 lines. Persistence is not mentioned explicitly by name in the document. Key relevant mentions:

- Lists `vector_store.py` (VectorStorePort) in the ports directory tree (line 220)
- Phase 1, 1.5, and 2 are complete; Phases 3 and 4 (Autonomous Remediation, Predictive) are next
- Technology stack table mentions Redis/etcd for coordination but does not enumerate database stores
- Architecture diagram shows a five-layer model without a dedicated persistence band
- Configuration section lists agent.yaml fields including feature flags but no DATABASE_URL/persistence settings visible
- `aiokafka>=0.10` listed as a core dependency (used for future event bus optionality)
- Contribution guidelines note: "Tests passing — 100% for domain/, >85% for adapters/" — **note this is lower than the `pyproject.toml` 90% fail_under**

**Key Discrepancy:** The master_system_document.md predates the persistence_architecture.md (2026-03-14 vs 2026-04-07) and does not reflect the persistence layer architecture or the three-store design.

---

## 7. `rag_implementation_analysis.md` — Full Summary

**Date:** 2026-03-30 | **Scope:** RAG diagnostic pipeline in `src/sre_agent/`

### 7.1 Architecture Components Mapped

| Concern | Primary File |
|---|---|
| Diagnosis orchestration | `src/sre_agent/domain/diagnostics/rag_pipeline.py` — `RAGDiagnosticPipeline.diagnose()` |
| Document indexing | `src/sre_agent/domain/diagnostics/ingestion.py` — `DocumentIngestionPipeline` |
| Runtime ingest endpoint | `src/sre_agent/api/rest/diagnose_router.py` — `ingest_document()` |
| Vector search | `src/sre_agent/adapters/vectordb/chroma/adapter.py` — `ChromaVectorStoreAdapter.search()` |
| Embedding | `src/sre_agent/adapters/embedding/sentence_transformers_adapter.py` |
| Prompt augmentation | `src/sre_agent/adapters/llm/openai/adapter.py` |
| Validation | `src/sre_agent/domain/diagnostics/validator.py` — `SecondOpinionValidator` |
| Confidence scoring | `src/sre_agent/domain/diagnostics/confidence.py` — `ConfidenceScorer` |

### 7.2 Two Indexing Paths (Key Discrepancy Found)

1. **Chunked ingestion path:** `DocumentIngestionPipeline.ingest()` uses `_chunk_by_headers()`, batch embedding, then batch store
2. **API direct path:** `ingest_document()` embeds full payload once and stores one `VectorDocument` — **bypasses semantic chunking**

**Impact:** API ingestion currently bypasses chunking logic, reducing retrieval recall quality compared to the designed ingestion pipeline.

### 7.3 Root-Cause Decision Logic

- Retrieval-gated (not root-cause-quality-gated): if retrieval returns at least one result, pipeline proceeds to LLM
- Empty retrieval → `_handle_novel_incident()` static fallback (NOT an LLM general inference call)
- Validator disagreement applies a confidence penalty but does NOT force root-cause replacement or escalation

### 7.4 Gap Matrix

| Gap ID | Finding | Impact |
|---|---|---|
| G1 | No general LLM fallback when retrieval is empty | Fails requirement: call LLM generally after RAG miss |
| G2 | No explicit root-cause-unresolved state machine | Transition from RAG certainty to fallback is ambiguous |
| G3 | Validation disagreement can still return uncorrected root cause | Root cause may be returned even when validator rejects it |
| G4 | Freshness penalty weakened by metadata stripping in Chroma adapter | Stale evidence can remain influential |
| G5 | API ingestion bypasses chunking pipeline | Retrieval recall and grounding quality may be lower than designed |
| G6 | Evidence citation type mismatch between port and pipeline payload | Auditability may be inconsistent |

### 7.5 Compliance Conclusion

- Retrieval-first behavior: **Implemented**
- General LLM fallback after RAG failure: **NOT implemented**
- Explicit root-cause-unresolved state: **NOT modeled**

---

## 8. `docs/architecture/layers/` — All Files Summary

| File | Status | Persistence Relevance |
|---|---|---|
| `action_layer.md` | DRAFT v1.0.0 | Safety guardrails, remediation executor. Mentions audit trail and post-remediation monitor. No database specifics. |
| `detection_layer.md` | DRAFT v1.0.0 | Mentions Redis for feature store (rolling windows, baselines). No PostgreSQL. Pre-dates TimescaleDB decision. |
| `intelligence_layer.md` | DRAFT v1.0.0 | Mentions vector DB for RAG retrieval (Historical Incidents/Runbooks KB). Covers DiagnosticCache concept. No pgvector specifics. |
| `observability_layer.md` | DRAFT v1.0.0 | Prometheus, Jaeger, Loki, GraphDB (topology). No PostgreSQL mention. |
| `orchestration_layer.md` | DRAFT v1.0.0 | Redis/etcd for distributed lock DB. PostgreSQL (or MySQL) mentioned for long-term historical data for graduation evaluations. Still shows Redis as lock-manager only. |
| `operator_layer.md` | Not read (not persistence-relevant) | Dashboard/notification layer |

**Common observation across all layer docs:** All are DRAFT and predate the 2026-04-07 persistence_architecture.md. They reflect an earlier design where persistence was less defined. The orchestration layer doc still shows Redis/etcd as primary (consistent with current impl) but mentions PostgreSQL for graduation history — this is not yet implemented.

---

## 9. `pyproject.toml` — Test Coverage Configuration

```toml
[tool.coverage.run]
source = ["src/sre_agent"]
branch = true
omit = [
    "src/sre_agent/tests/*",
    "src/sre_agent/__pycache__/*",
]

[tool.coverage.report]
fail_under = 90
show_missing = true
precision = 1
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "if __name__ ==",
    "@overload",
    "raise NotImplementedError",
]
```

**Minimum coverage threshold: 90%** (`fail_under = 90`)

**Note:** The master_system_document.md PR checklist states "Tests passing — 100% for domain/, >85% for adapters/" which is inconsistent. `pyproject.toml` is the binding configuration; `fail_under = 90` applies to the entire `src/sre_agent` source tree.

---

## 10. Architecture Doc Accuracy vs. Actual Implementation

### Confirmed Consistent

| Document claim | Implementation status |
|---|---|
| `PostgresIncidentStore` with append-only `incident_events` + mutable `incidents` projection | Implemented and tested (unit + integration) |
| Transactional outbox pattern with `PostgresOutboxStore` + `OutboxRelay` | Implemented and tested (unit + integration) |
| `claim_pending()` for exclusive row ownership (not `get_pending` with FOR UPDATE) | Implemented and unit-tested |
| `DuplicateEventError` on idempotency_key collision | Implemented and tested at unit and integration levels |
| AGENTS.md-compliant lock audit: provider + compute_mechanism + fencing_token | Implemented and tested in `test_coordination_store.py` |
| pgvector adapter with JSONB fallback for non-pgvector environments | Implemented and unit-tested |
| Migrations 001–010 in `src/sre_agent/adapters/persistence/migrations/` | Confirmed by integration test fixture |
| `RetentionExecutor` for `processed_events` and `baseline_snapshots` cleanup | Implemented and unit-tested |

### Discrepancies / Gaps Found

| Discrepancy | Detail |
|---|---|
| `master_system_document.md` predates persistence architecture | Written 2026-03-14; persistence plan written 2026-04-07. Master doc does not mention PostgreSQL persistence, outbox pattern, or three-store design. |
| Layer docs all DRAFT and pre-persistence | `detection_layer.md` proposes Redis as Feature Store for baselines; actual decision is TimescaleDB. Not updated. |
| No integration test for pgvector | Only ChromaDB has an integration test. `PgVectorStoreAdapter` tested with FakePool only — no real PostgreSQL+pgvector validation. |
| Phase 4 (DiagnosticCache → Redis) not started | No `RedisDiagnosticCache` adapter found; no tests. `persistence_architecture.md` Phase 4 describes it but it is not implemented. |
| Phase 6 (TimescaleDB) not started | No `TimescaleBaselineAdapter` found; no tests. Architecture doc describes it but migration 009 is TimescaleDB-aware (extension check only). |
| PR checklist in master doc says ">85% adapters" but pyproject.toml enforces 90% | Inconsistency; pyproject.toml binding configuration takes precedence. |
| `aiokafka` in core dependencies | Listed as a core dependency in pyproject.toml but explicitly closed as "not used for internal bus" per ADR-004. Retained for future optionality only; creates a misleading dependency footprint. |

---

## 11. Summary Findings

### What Is Well-Tested
- All seven persistence adapter unit tests use `FakePool/FakeConnection` pattern — no real database required, fast execution
- Integration tests for `PostgresIncidentStore` cover the full lifecycle including all migrations 001–007 and specific migration 008/009/010 schema assertions
- `OutboxRelay` has thorough retry/failure/idempotency behavioral tests
- Coordination audit store tests explicitly validate AGENTS.md policy compliance (compute_mechanism tokens, AGENTS.md mandatory fields)
- `test_reasoning_trace_store.py` covers all six public methods including similarity clamping edge case

### What Is NOT Tested
- Integration: pgvector against real PostgreSQL+pgvector extension
- Integration: OutboxRelay against real PostgreSQL + Redis Streams simultaneously
- Integration: Remediation store, reasoning trace store, coordination audit store (all unit-only)
- Phase 4: RedisDiagnosticCache (not implemented)
- Phase 6: TimescaleDB baseline adapter (not implemented)

### Coverage Minimum: 90% (`fail_under = 90` in `pyproject.toml`)

---

*Research output file: `.copilot-tracking/research/subagents/2026-05-28/tests-and-docs-research.md`*
