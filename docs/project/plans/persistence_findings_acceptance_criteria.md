---
title: Persistence Findings Remediation — Acceptance Criteria
description: Measurable pass/fail criteria for all 10 findings from Phase 4.0 review. Each criterion is specific, testable, and traceable to the remediation plan.
ms.date: 2026-04-12
ms.topic: acceptance-criteria
author: SRE Agent Engineering Team
---

# Persistence Findings Remediation — Acceptance Criteria

Plan reference: `docs/project/plans/persistence_findings_remediation_plan.md`

---

## F1 — Provider Defaults in `update_projection`

**AC-F1.1** `IncidentStorePort.update_projection()` signature includes three new
required parameters: `provider: str`, `compute_mechanism: str`, `resource_id: str`.

**AC-F1.2** `PostgresIncidentStore.update_projection()` no longer contains any
hardcoded `"unknown"` or `"KUBERNETES"` string literals as fallback defaults.

**AC-F1.3** A unit test demonstrates that calling `update_projection()` on a
brand-new incident (no existing row) with `provider="aws"`,
`compute_mechanism="SERVERLESS"`, `resource_id="arn:..."` executes without
raising an exception.

**AC-F1.4** The SQL `_UPSERT_PROJECTION` query in the adapter receives the
caller-supplied `provider`, `compute_mechanism`, and `resource_id` values rather
than derived defaults for the INSERT path.

---

## F2 — Atomic Outbox Row Claiming

**AC-F2.1** `OutboxPort` declares abstract method `claim_pending(limit: int) ->
list[dict[str, Any]]`.

**AC-F2.2** `OutboxPort` declares abstract method `release_claim(outbox_id: UUID)
-> None` for resetting 'processing' → 'pending'.

**AC-F2.3** Migration `004_relay_vector_fixes.sql` alters the `event_outbox`
check constraint to include `'processing'` alongside `'pending'`, `'sent'`,
`'failed'`.

**AC-F2.4** `PostgresOutboxStore.claim_pending()` uses a single `UPDATE …
SET status = 'processing' … RETURNING` statement — no `SELECT … FOR UPDATE`.

**AC-F2.5** Two concurrent calls to `claim_pending(limit=1)` against a DB with
one pending row return that row in exactly one call and an empty list in the
other (verified in unit test via ordered FakeConnection queues).

**AC-F2.6** `OutboxRelay.run_once()` calls `claim_pending()` (not
`get_pending()`) to acquire rows for publish.

**AC-F2.7** On publish failure, the relay calls `release_claim()` (not
`get_pending`) so the row reverts to 'pending' for retry.

**AC-F2.8** `get_pending()` is retained on `OutboxPort` and its implementation
unchanged (backward-compatible, for monitoring use).

---

## F3 — Reader Loops Lifecycle

**AC-F3.1** `EventBus` port defines concrete method `async def start(self,
task_group: anyio.abc.TaskGroup) -> None` with a no-op default body.

**AC-F3.2** `RedisStreamsEventBus.start(task_group)` stores the task group
reference and spawns all readers queued in `_pending_readers`.

**AC-F3.3** `InMemoryEventBus` inherits the no-op `start()` without requiring
any override.

**AC-F3.4** A unit test calls `bus.subscribe(...)` then `bus.start(tg)` and
verifies that `_read_loop` is invoked (mocked).

**AC-F3.5** `run_readers()` is kept for backward compatibility and internally
delegates to `start()`.

---

## F4 — Late Subscriptions Started Dynamically

**AC-F4.1** After `bus.start(task_group)` is called, a subsequent
`bus.subscribe(event_type, handler)` call immediately spawns a reader task into
the stored task group rather than queuing in `_pending_readers`.

**AC-F4.2** A unit test verifies that a subscription added after `start()` has
`_reader_scopes` populated for the new event_type.

**AC-F4.3** A subscription added before `start()` is still started when `start()`
is finally called (original pre-start path unbroken).

---

## F5 — pgvector Upsert Semantics for Non-UUID doc_ids

**AC-F5.1** Migration `004_relay_vector_fixes.sql` adds
`CONSTRAINT uq_vector_source UNIQUE (source_type, source_id)` to
`vector_embeddings`.

**AC-F5.2** Both `_INSERT_VEC` and `_INSERT_JSON` SQL use
`ON CONFLICT (source_type, source_id) DO UPDATE`.

**AC-F5.3** `store()` always generates `embedding_id = uuid4()` (no UUID
coercion from `doc_id`).

**AC-F5.4** A unit test stores the same `doc_id = "non-uuid-string"` twice and
verifies the `FakeConnection.execute()` is called with the upsert SQL both times
(idempotent, not duplicate insert).

**AC-F5.5** A unit test stores the same `doc_id = str(uuid4())` twice and
verifies the same idempotent upsert behavior.

---

## F6 — Document Content Persistence

**AC-F6.1** `store()` sets `meta["content"] = document.content` before
serializing `metadata_json`.

**AC-F6.2** A unit test stores a document with `content="test content"` and
verifies that `search()` returns a `SearchResult` with `content="test content"`.

**AC-F6.3** Storing a document with empty `content=""` returns `content=""`
(not `None`) from search.

---

## F7 — Collection Isolation in Queries

**AC-F7.1** `_SEARCH_VEC` SQL contains `WHERE source_type = $3` (or equivalent
positional parameter) scoping results to the collection.

**AC-F7.2** `_FETCH_ALL_JSON` (or equivalent) SQL contains `WHERE source_type = $1`.

**AC-F7.3** `_COUNT` SQL contains `WHERE source_type = $1`.

**AC-F7.4** `_DELETE_STALE` SQL contains `AND source_type = $2`.

**AC-F7.5** `_GET_BY_SOURCE_ID` SQL contains `AND source_type = $2`.

**AC-F7.6** A unit test instantiates two adapters with different `collection`
names and verifies that `search()`, `count()`, and `delete_stale()` pass
`self._collection` as a query parameter in the executed SQL.

---

## F8 — Durable Retry Counts

**AC-F8.1** `OutboxPort` declares abstract method `increment_retry(outbox_id:
UUID) -> int` that returns the new persisted retry count.

**AC-F8.2** `PostgresOutboxStore.increment_retry()` executes
`UPDATE event_outbox SET retry_count = retry_count + 1 WHERE outbox_id = $1 RETURNING retry_count`.

**AC-F8.3** `OutboxRelay` has no `_retry_counts: dict` field.

**AC-F8.4** On publish failure, `OutboxRelay.run_once()` calls
`self._outbox.increment_retry(outbox_id)` and uses the returned count to decide
whether to call `mark_failed()`.

**AC-F8.5** A unit test simulates `increment_retry()` returning `max_retries`
and verifies `mark_failed()` is called on that entry.

**AC-F8.6** A unit test simulates `increment_retry()` returning less than
`max_retries` and verifies `mark_failed()` is NOT called (retry continues).

---

## F9 — Event Identity Preservation

**AC-F9.1** `OutboxRelay.run_once()` extracts `event_id` from
`payload["event_id"]` and passes it to `DomainEvent(event_id=...)`.

**AC-F9.2** `OutboxRelay.run_once()` extracts `occurred_at` from
`payload["occurred_at"]` (ISO string), parses it, and passes it to
`DomainEvent(timestamp=...)`.

**AC-F9.3** When `payload["event_id"]` is absent or malformed, relay falls back
to `uuid4()` without raising.

**AC-F9.4** When `payload["occurred_at"]` is absent or malformed, relay falls
back to `datetime.now(UTC)` without raising.

**AC-F9.5** `RedisStreamsEventBus._dispatch()` extracts `event_id` and
`timestamp` from the deserialized stream data and passes them to `DomainEvent`.

**AC-F9.6** A unit test for the relay verifies the published `DomainEvent` has
`event_id` equal to the value in the payload.

**AC-F9.7** A unit test for the bus dispatch verifies the dispatched `DomainEvent`
has `event_id` equal to the value in the stream message.

---

## F10 — Ruff Lint Compliance

**AC-F10.1** `ruff check src/ tests/` exits with code 0 (zero violations).

**AC-F10.2** No `timezone.utc` references remain in test files (`UP017` —
replaced with `datetime.UTC`).

**AC-F10.3** No quoted type annotations remain in test files (`UP037`).

**AC-F10.4** All import blocks in test files are sorted (`I001`).

---

## Cross-Cutting Standards Criteria

**AC-STD.1** All new/modified adapter files maintain ≥ 90% line coverage
(verified by `pytest --cov`).

**AC-STD.2** `ruff check --select ALL src/ tests/` exits 0 after excluding
only pre-approved noqa suppressions.

**AC-STD.3** All new abstract methods on ports follow the existing docstring
style (Args / Returns / Raises).

**AC-STD.4** No new imports of asyncpg, redis, or anyio appear in
`src/sre_agent/ports/` — ports must remain infrastructure-free.

**AC-STD.5** All new SQL constants follow the `_UPPER_SNAKE_CASE` naming
convention used in existing adapters.

**AC-STD.6** All new `structlog` log events follow the
`component.event_name` dot-notation pattern.

**AC-STD.7** Migration 004 is idempotent — re-running it on a DB that already
has the changes applied must not error.
