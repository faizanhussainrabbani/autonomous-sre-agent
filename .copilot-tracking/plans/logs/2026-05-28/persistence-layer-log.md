<!-- markdownlint-disable-file -->
# Planning Log: Persistence Layer Gap Remediation

## Discrepancy Log

Gaps and differences identified between research findings and the implementation plan.

### Unaddressed Research Items

* DR-01: QG-08 — Phases 4 and 6 not implemented (`RedisDiagnosticCache`, TimescaleDB baseline adapter)
  * Source: .copilot-tracking/research/2026-05-28/data-persistence-research.md (Section 9, QG-08)
  * Reason: Both phases require new adapters and potentially new infrastructure services (TimescaleDB for Phase 6). Adding them would introduce new tool dependencies, violating the "no new additions" constraint specified in user input.
  * Impact: medium — documented as deferred in WI-01 and WI-02

* DR-02: pgvector auto-wiring on `persistence.enabled=True`
  * Source: .copilot-tracking/research/2026-05-28/data-persistence-research.md (Section 6, Bootstrap Sequence)
  * Reason: Changing `create_vector_store()` to auto-wire pgvector when persistence is enabled would alter bootstrap behaviour and could break ChromaDB dev path. Considered a separate concern from gap remediation.
  * Impact: low — documented as WI-03

* DR-03: `.env.example` missing `POSTGRES_DSN`, `REDIS_URL` and other required env vars
  * Source: .copilot-tracking/research/2026-05-28/data-persistence-research.md (Section 5)
  * Reason: Doc/config update is lower priority than structural code gaps; deferred to WI-04.
  * Impact: low

### Plan Deviations from Research

* DD-01: Migration runner uses asyncpg + plain Python, not Alembic
  * Research recommends: a `schema_migrations` tracking table + script runner
  * Plan implements: `scripts/dev/migrate.py` using asyncpg directly, reading SQL files in numeric order, tracking applied migrations in a `schema_migrations` table — no Alembic
  * Rationale: Alembic would be a new external dependency, violating the "no new additions" constraint. The existing pattern uses raw SQL files; the runner simply applies unapplied ones. asyncpg is already present.

* DD-02: `EventStore` adapter wraps existing `incident_events` table
  * Research recommends: PostgreSQL-backed append-only event log
  * Plan implements: `PostgresEventStore` reading/writing the existing `incident_events` table, which already exists from migration 001. No new table required.
  * Rationale: The `incident_events` table is the natural backing store. The adapter translates between the `EventStore` port (`DomainEvent`) and the existing `IncidentEvent` domain model to avoid duplication.

* DD-03: Status transition enforcement added as Pydantic validators, not a new domain service
  * Research recommends: a domain service or validator
  * Plan implements: Pydantic `model_validator` on the status-bearing models during Phase 2 (domain model migration). This collocates validation with the model definition, avoiding a new service class.
  * Rationale: Pydantic BaseModel migration (Phase 2) is already required by ADR-002. Embedding validators there is efficient and adds no structural complexity.

* DD-04: Plan Implementation Checklist line-number cross-references for Phase 2 Steps 2.2–2.3 and all Phase 3–5 steps are systematically offset from actual content positions in the details file
  * Research recommends: N/A — this is a plan-to-details file navigation error identified during cross-reference validation; it does not represent a deviation from research recommendations
  * Plan implements: Line-number references in the Implementation Checklist cite ranges that are offset from the actual heading positions in the details file. Measured offsets: Step 2.2 cited at Lines 271–330 (actual ~Lines 254–306, offset −17); Step 2.3 cited at Lines 331–395 (actual ~Lines 307–342, offset −22); Step 3.1 cited at Lines 396–450 (actual ~Lines 343–393, offset −53); Step 3.2 cited at Lines 451–505 (actual ~Lines 394–442, offset −57); Step 4.1 cited at Lines 506–555 (actual ~Lines 443–491, offset −63); Step 4.2 cited at Lines 556–615 (actual ~Lines 492–510, offset −64); Step 5.1 cited at Lines 616–660 (actual ~Lines 516–554, offset −98); Step 5.2 cited at Lines 661–710 (actual ~Lines 555–600, offset −106). Phase 1 (Steps 1.1 and 1.2) and Step 2.1 references are accurate.
  * Rationale: The details file is shorter than the plan author anticipated from Step 2.2 onward; each phase's content is more concise than the allocated line budget, causing the undercount to accumulate. An implementer navigating to the cited line ranges for any Phase 3, 4, or 5 step will land in a different step's content. Severity: **major** — 8 of 11 step cross-references are incorrect; however, step names and QG labels in the checklist correctly identify each step, so an implementer using section headings rather than line numbers is unaffected.

## Implementation Paths Considered

### Selected: Incremental gap remediation using existing tools only

* Approach: Address each quality gap (QG-01 through QG-10, minus deferred QG-08) in priority order using only tools already present in the project (asyncpg, Pydantic v2, anyio, structlog, pytest).
* Rationale: User constraint is "existing persistence layer/tools, no new additions". All required capabilities (SQL execution, async pool management, Pydantic validation) already exist.
* Evidence: .copilot-tracking/research/2026-05-28/data-persistence-research.md (Section 3 — asyncpg confirmed; Section 5 — Pydantic BaseSettings already used in config; pyproject.toml — Pydantic v2 confirmed as dependency)

### IP-01: Alembic-based migration management

* Approach: Add Alembic as a migration management tool. Convert existing SQL files to Alembic revision files. Gain automatic schema version tracking and downgrade capability.
* Trade-offs: Clean migration graph with upgrade/downgrade scripts; industry-standard tooling. However, requires converting 10 existing raw SQL files and introducing a new dependency. Adds Alembic config files and `env.py`.
* Rejection rationale: Violates "no new additions" constraint. The existing raw SQL pattern with a lightweight tracker is sufficient for the scale of this project.

### IP-02: Pydantic validators as separate domain service (for QG-03)

* Approach: Create a `StatusTransitionService` that validates transitions before adapter writes.
* Trade-offs: Cleaner separation of business rule from data model. Requires a new service class, new port interface, and adapter updates.
* Rejection rationale: Over-engineered for the scale of validation needed. Pydantic `model_validator` on the model itself (DD-03) achieves the same correctness guarantee with less code. Also, creating a new service would be an "addition" beyond the constraint.

## Suggested Follow-On Work

Items identified during planning that fall outside current scope.

* WI-01: Implement Phase 4 — `RedisDiagnosticCache` adapter — (medium priority)
  * Source: docs/architecture/persistence_architecture.md Phase 4 definition
  * Dependency: None technical; requires decision to include Redis as a caching backend and any associated Redis caching configuration in `AgentConfig`

* WI-02: Implement Phase 6 — TimescaleDB baseline adapter — (low priority)
  * Source: docs/architecture/persistence_architecture.md Phase 6 definition
  * Dependency: TimescaleDB service must be added to docker-compose.deps.yml; migration 009 must be validated against real TimescaleDB

* WI-03: Auto-wire pgvector in `create_vector_store()` when `persistence.enabled=True` — (medium priority)
  * Source: .copilot-tracking/research/2026-05-28/data-persistence-research.md (Section 6)
  * Dependency: Completes Phase 5 requirement and eliminates dev/prod wiring gap

* WI-04: Add `.env.example` documenting all required environment variables — (low priority)
  * Source: .copilot-tracking/research/2026-05-28/data-persistence-research.md (Section 5)
  * Dependency: None

* WI-05: Add pgvector real-DB integration test using testcontainers — (medium priority)
  * Source: .copilot-tracking/research/2026-05-28/data-persistence-research.md (Section 7)
  * Dependency: Phase 1.2 (PostgresEventStore) completion; existing testcontainers pattern from test_incident_store_integration.py can be reused

* WI-06: Push unit test coverage from 83.3% to ≥90% threshold — (high priority)
  * Source: Post-review remediation session; `python -m pytest --cov-fail-under=90` fails at 83.33%
  * Primary gaps (by uncovered lines):
    - `adapters/vectordb/chroma/adapter.py`: 13.4% (75 missing lines) — ChromaDB write/query/delete paths
    - `api/rest/diagnose_router.py`: 64.4% (34 missing lines) — FastAPI route handlers
    - `domain/remediation/engine.py`: 66.1% (39 missing lines) — execute/rollback paths
    - `ports/persistence.py`: 86.2% (31 missing lines) — abstract method docstrings/stubs
    - `domain/diagnostics/severity.py`: 65.2% (14 missing lines)
  * Dependency: None; all infrastructure present. Estimated 50-80 new test cases needed.
  * Note: Safety module coverage was partially improved this session (cooldown.py, guardrails.py, persistence models) but the ChromaDB adapter alone accounts for ~50 uncovered lines.
