<!-- markdownlint-disable-file -->
# RPI Validation: Persistence Layer — Phase 3

**Plan**: `.copilot-tracking/plans/2026-05-28/persistence-layer-plan.instructions.md`
**Changes Log**: `.copilot-tracking/changes/2026-05-28/persistence-layer-changes.md`
**Research Document**: `.copilot-tracking/research/2026-05-28/data-persistence-research.md`
**Phase**: 3 — Medium-Priority Structural Fixes (QG-06, QG-07)
**Validation Date**: 2026-05-28
**Validator**: GitHub Copilot (RPI Validator mode)

---

## Phase Status: PARTIAL

Phase 3 code fixes are present and functionally correct in both target files. However, Phase 3 is
not documented in the changes log's detailed section, the plan checklist remains unchecked, and
one plan success criterion (concurrent parallel fencing token uniqueness unit test) is not
satisfied. Lint/test validation for Phase 3 is unconfirmed.

---

## Finding Summary

| Severity | Count |
|----------|-------|
| Critical | 0 |
| Major    | 2 |
| Minor    | 3 |
| **Total** | **5** |

---

## Step 3.1: Fix Coordination Audit Store Duplicate Pool (QG-06)

### Plan Requirements

From `.copilot-tracking/details/2026-05-28/persistence-layer-details.md` lines 347–386:

1. `coordination_store.py`: `PostgresCoordinationAuditStore.__init__` accepts an
   `asyncpg.Pool` parameter; does **not** create its own pool internally.
2. `bootstrap.py`: `bootstrap_coordination_audit` signature changes from
   `bootstrap_coordination_audit(config: AgentConfig)` to
   `bootstrap_coordination_audit(pool: asyncpg.Pool)`. No internal `asyncpg.create_pool()`
   call for the audit store.
3. `api/main.py`: call site passes the shared pool to `bootstrap_coordination_audit`.

Plan success criteria:
- `bootstrap_coordination_audit(pool)` accepts the same `asyncpg.Pool` used by all other stores.
- No second `asyncpg.create_pool()` exists in `coordination_store.py` or `bootstrap.py` for
  the audit store.
- All 7 existing `test_coordination_store.py` tests pass.

### Evidence — Actual Code State

**`src/sre_agent/adapters/persistence/coordination_store.py`** — lines 62–72:

```python
def __init__(self, pool: Any) -> None:
    """Initialise the store with an asyncpg connection pool.

    Args:
        pool: An asyncpg.Pool instance (or compatible async pool).
    """
    self._pool = pool
```

✅ Constructor accepts an injected pool. No `asyncpg.create_pool()` call anywhere in the file.

**`src/sre_agent/adapters/bootstrap.py`** — lines 272–292:

```python
async def bootstrap_coordination_audit(
    pool: object | None,
) -> CoordinationAuditPort | None:
    ...
    return PostgresCoordinationAuditStore(pool=pool)
```

✅ Signature accepts shared pool. No internal `create_pool()` call in this function.
The `asyncpg.create_pool()` at line 386 belongs to `bootstrap_asyncpg_pool()`, not this function.

**`src/sre_agent/api/main.py`** — line 141:

```python
coordination_audit = await bootstrap_coordination_audit(pool)
```

✅ Call site passes the shared pool.

### Step 3.1 Findings

| # | Severity | Finding |
|---|----------|---------|
| F-3.1-1 | **Minor** | Changes log detailed section (`## Changes`) does not list the `bootstrap_coordination_audit` signature change or `coordination_store.py` pool injection fix as a Phase 3 change. The `bootstrap.py` entry reads only "Added `bootstrap_event_store(pool)` factory function". The summary paragraph mentions "fixes the coordination audit duplicate pool" but this is not substantiated by a detailed change entry. Evidence: `.copilot-tracking/changes/2026-05-28/persistence-layer-changes.md` lines 14–22. |
| F-3.1-2 | **Minor** | Plan checklist entry `[ ] Step 3.1` remains unchecked despite the fix being implemented. Evidence: `.copilot-tracking/plans/2026-05-28/persistence-layer-plan.instructions.md` line ~95. |

**Step 3.1 Code Status: ✅ IMPLEMENTED** — All three required code locations are correct.

---

## Step 3.2: Fix etcd Fencing Token Non-Atomic Generation (QG-07)

### Plan Requirements

From `.copilot-tracking/details/2026-05-28/persistence-layer-details.md` lines 391–430:

1. Replace the non-atomic read-increment-write in `EtcdLockManager` with a CAS loop using
   etcd transactions.
2. Plan specifies function name `_increment_fencing_token` and key suffix `:fencing_counter`.
3. Success criteria include:
   - No plain read-increment-write in fencing token generation.
   - A new test case where concurrent parallel `acquire()` calls produce unique fencing tokens.
   - `mypy` passes on the modified file.

### Evidence — Actual Code State

**`src/sre_agent/adapters/coordination/etcd_lock_manager.py`** — `_next_fencing_token` method
(lines ~243–270):

```python
async def _next_fencing_token(self, lock_key: str) -> int:
    token_key = f"{lock_key}:fencing"
    while True:
        raw, _meta = await anyio.to_thread.run_sync(self._client.get, token_key)
        if raw is None:
            # Key does not exist — attempt atomic creation with value "1"
            success, _responses = await anyio.to_thread.run_sync(
                lambda: self._client.transaction(
                    compare=[self._client.transactions.version(token_key) == 0],
                    success=[self._client.transactions.put(token_key, "1")],
                    failure=[],
                )
            )
            if success:
                return 1
            # Another writer won the race; retry to read the new value
        else:
            ...
            # Atomic CAS: only write next_str when stored value is still current_str
            success, _responses = await anyio.to_thread.run_sync(
                lambda _cv=current_str, _nv=next_str: self._client.transaction(
                    compare=[self._client.transactions.value(token_key) == _cv],
                    success=[self._client.transactions.put(token_key, _nv)],
                    failure=[],
                )
            )
            if success:
                return next_token
            # CAS lost to a concurrent writer; retry with the updated value
```

✅ Non-atomic read-increment-write has been replaced with a CAS loop using etcd transactions.
Both the "create new" and "increment existing" paths use atomic etcd transactions.
✅ CAS retry on failure is implemented correctly.

**No unit test file for etcd lock manager in unit tests:**

`file_search tests/unit/adapters/coordination/` returned no results. No
`tests/unit/adapters/coordination/test_etcd_lock_manager.py` exists.

**Integration test** `tests/integration/test_etcd_lock_manager_integration.py` (lines 121–123):

```python
assert high.fencing_token is not None
assert low.fencing_token is not None
assert high.fencing_token > low.fencing_token
```

This checks ordering under sequential acquisition, not concurrent parallel uniqueness.

### Step 3.2 Findings

| # | Severity | Finding |
|---|----------|---------|
| F-3.2-1 | **Major** | Plan success criterion not met: no unit test or integration test verifies that concurrent parallel `acquire()` calls produce unique fencing tokens. The integration test at `tests/integration/test_etcd_lock_manager_integration.py` lines 121–123 checks sequential ordering only, not parallel uniqueness. No unit test file exists for the etcd lock manager (`tests/unit/adapters/coordination/` does not exist). Evidence: file_search and grep_search confirmed no parallel/concurrent fencing token test. |
| F-3.2-2 | **Minor** | Function name deviation from plan spec: plan specified `_increment_fencing_token`; actual implementation uses `_next_fencing_token`. Evidence: `src/sre_agent/adapters/coordination/etcd_lock_manager.py` (method name). Not a functional issue but diverges from the documented design. |
| F-3.2-3 | **Minor** | Counter key suffix deviation from plan spec: plan specified `{lock_key}:fencing_counter`; actual uses `{lock_key}:fencing`. This is a non-functional naming difference but diverges from specification. Evidence: `etcd_lock_manager.py` line `token_key = f"{lock_key}:fencing"`. |

**Step 3.2 Code Status: ✅ CORE FIX IMPLEMENTED** — CAS atomicity is correct. Missing: concurrent
uniqueness test required by plan success criteria.

---

## Step 3.3: Validate Phase Changes (Lint + Unit Tests)

### Plan Requirements

From `.copilot-tracking/plans/2026-05-28/persistence-layer-plan.instructions.md` Phase 3
checklist:

- Run `bash scripts/dev/run.sh lint` for modified adapters.
- Run `bash scripts/dev/run.sh test:unit` scoped to coordination and events.

### Evidence

The changes log contains no record of these validation commands being executed for Phase 3.
The changes log's "Additional or Deviating Changes" section documents only Phase 1 deviations
(Steps 1.1 and 1.2). Phase 3 validation results are entirely absent.

### Step 3.3 Findings

| # | Severity | Finding |
|---|----------|---------|
| F-3.3-1 | **Major** | Changes log contains no evidence that lint (`ruff`/`mypy`) or unit tests were executed against the Phase 3 file changes (`coordination_store.py`, `bootstrap.py` coordination audit path, `etcd_lock_manager.py`). The plan specifies this as a required step. Cannot confirm that `mypy` passes on `etcd_lock_manager.py` (a plan success criterion for QG-07). Evidence: `.copilot-tracking/changes/2026-05-28/persistence-layer-changes.md` — no Step 3.3 entry. |

---

## Coverage Assessment

| Plan Item | Code Implemented | Changes Log Entry | Plan Checklist | Test Coverage |
|-----------|-----------------|------------------|----------------|---------------|
| Step 3.1: coordination_store.py pool injection | ✅ Yes | ❌ Missing | ❌ Unchecked | ✅ 7 existing tests valid |
| Step 3.1: bootstrap.py signature change | ✅ Yes | ❌ Missing (partial: summary only) | ❌ Unchecked | N/A |
| Step 3.1: api/main.py call site update | ✅ Yes | ❌ Missing | ❌ Unchecked | N/A |
| Step 3.2: etcd CAS fencing token loop | ✅ Yes | ❌ Missing | ❌ Unchecked | ⚠ No concurrent uniqueness test |
| Step 3.3: lint + test validation | ❓ Unconfirmed | ❌ Missing | ❌ Unchecked | N/A |

**QG-06 resolution**: Code satisfies all plan success criteria.
**QG-07 resolution**: Code satisfies the functional CAS requirement but lacks the required
concurrent uniqueness test.

---

## Findings by Severity

### Major (2)

**F-3.2-1** — Missing concurrent parallel fencing token uniqueness test (QG-07 success
criterion). Plan requires a test case proving parallel `acquire()` calls produce unique tokens.
No such test exists in unit or integration test suites.

**F-3.3-1** — No validation evidence in changes log for Phase 3. Lint and test execution
against `etcd_lock_manager.py` changes is unconfirmed. `mypy` compliance on the modified file
cannot be verified without running it.

### Minor (3)

**F-3.1-1** — Changes log detailed `## Changes` section omits Phase 3 modifications.
Summary paragraph references them but detailed entries are absent.

**F-3.1-2** — Plan checklist `[ ] Step 3.1` and `[ ] Step 3.2` and `[ ] Step 3.3` remain
unchecked despite code being implemented.

**F-3.2-2** — Function name `_next_fencing_token` deviates from plan-specified
`_increment_fencing_token`. Non-functional.

**F-3.2-3** — Counter key suffix `:fencing` deviates from plan-specified `:fencing_counter`.
Non-functional.

---

## Clarifying Questions

1. Were the Phase 3 code changes (`coordination_store.py` pool injection, `bootstrap_coordination_audit` signature, `etcd_lock_manager.py` CAS loop) implemented as part of the Phase 1 `bootstrap.py` session, or in a separate undocumented session? Knowing this would clarify whether the changes log omission was intentional or an oversight.
2. Was `mypy` run against `etcd_lock_manager.py` after the CAS loop change? The `anyio.to_thread.run_sync` lambda captures (`_cv`, `_nv`) need type-checker verification.
3. Is the concurrent parallel fencing token uniqueness test expected to be a unit test (mock etcd client) or an integration test (real etcd via testcontainers)? The plan says "add test case" without specifying scope.
