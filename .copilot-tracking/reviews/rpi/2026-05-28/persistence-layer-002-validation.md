<!-- markdownlint-disable-file -->
# RPI Validation Report — Phase 2: Pydantic Domain Model Migration

**Validation Date:** 2026-05-28
**Plan File:** `.copilot-tracking/plans/2026-05-28/persistence-layer-plan.instructions.md`
**Changes Log:** `.copilot-tracking/changes/2026-05-28/persistence-layer-changes.md`
**Research Document:** `.copilot-tracking/research/2026-05-28/data-persistence-research.md`
**Phase:** 2 — Pydantic Domain Model Migration (QG-01, QG-03)
**Phase Status:** **PARTIAL**

---

## Executive Summary

Phase 2 targets three steps: migrating all `domain/models/` files from `@dataclass` to Pydantic `BaseModel` (Step 2.1), adding status-transition validators (Step 2.2), and updating adapter and test construction-site imports (Step 2.3). Inspection of the actual source files reveals that Steps 2.1 and 2.2 are **fully implemented in the code** — all domain model files use Pydantic `BaseModel` and carry `model_validator(mode="after")` guards for every status state machine. However, the changes log records **no Phase 2 changes whatsoever**: it covers only Phase 1 deliverables. The plan checklist also remains `[ ]` for every Phase 2 step. This creates a significant tracking discrepancy between the documented state and the actual code state. Step 2.3 is effectively vacuous — no adapter or test constructs domain model instances directly (they use port DTOs), so there are no construction sites to migrate.

A secondary finding is that the research document asserted "all 4 domain model files use `@dataclass`" as a current gap (QG-01), but the actual code contains zero `@dataclass` usages in `src/sre_agent/domain/models/`. This means either the research was inaccurate at the time of writing, or the migration occurred between the research and this validation pass without being recorded in the changes log.

---

## Phase Requirements (from Plan)

| Step | Requirement | Quality Gate |
|------|-------------|--------------|
| 2.1 | Migrate all `src/sre_agent/domain/models/` from `@dataclass` to Pydantic `BaseModel`; no `@dataclass` imports remaining | QG-01 |
| 2.2 | Add Pydantic `field_validator` / `model_validator` for `IncidentStatus` and `RemediationStatus` transition enforcement | QG-03 |
| 2.3 | Update all adapter and test files that construct domain model instances to use Pydantic keyword-argument construction | QG-01, QG-03 |

---

## Step-by-Step Findings

### Step 2.1 — Migrate Domain Models from `@dataclass` to Pydantic `BaseModel`

**Finding:** IMPLEMENTED — not documented in changes log.

**Evidence — Domain Model Files:**

All five files in `src/sre_agent/domain/models/` import from `pydantic` and extend `BaseModel`:

| File | Pydantic Import | BaseModel Usage |
|------|-----------------|-----------------|
| `persistence.py` | `from pydantic import BaseModel, ConfigDict, Field, model_validator` (line 21) | `IncidentEvent`, `Incident`, `DiagnosisResult`, `RemediationAction`, `OutboxEntry`, `CoordinationAuditEntry` |
| `canonical.py` | `from pydantic import BaseModel, ConfigDict, Field` (line 21) | `ServiceLabels`, `CanonicalMetric`, `TraceSpan`, `CanonicalTrace`, `CanonicalLogEntry`, all others |
| `diagnosis.py` | `from pydantic import BaseModel, ConfigDict, Field, model_validator` (line 17) | `ConfidenceLevel`, `EvidenceCitation`, `ImpactDimensions`, `Diagnosis` |
| `detection_config.py` | `from pydantic import BaseModel` (line 12) | `DetectionConfig` |
| `vector.py` | `from pydantic import BaseModel, ConfigDict, Field` (line 13) | `VectorDocument`, `SearchResult` |

**Evidence — Dataclass Absence:**

Grep for `@dataclass` and `from dataclasses import` across `src/sre_agent/domain/models/` returns **zero matches**. The plan success criterion ("no `@dataclass` decorators remain") is satisfied.

**Evidence — Discrepancy with Research and Plan:**

- Research document (QG-01 section): "All 4 domain model files use `@dataclass`; ADR-002 mandates Pydantic BaseModel" — this is contradicted by the actual code.
- Plan checklist: `[ ] Step 2.1` — marked not done.
- Changes log: Contains no entries for domain model migration.

**Severity of tracking gap:** Major — the plan and changes log report this as unimplemented, but the code is fully compliant with ADR-002.

---

### Step 2.2 — Add Pydantic Validators for Status Transition Enforcement

**Finding:** IMPLEMENTED — not documented in changes log.

**Evidence — Validators in `persistence.py`:**

Six `model_validator(mode="after")` decorators are present in `src/sre_agent/domain/models/persistence.py`:

| Class | Validator Method | Lines | Enforces |
|-------|-----------------|-------|---------|
| `IncidentEvent` | `_validate_fields` | 147–158 | `event_type` non-empty; `compute_mechanism` in `ComputeMechanismToken`; `provider` in `ProviderToken` |
| `Incident` | `_validate_status_transition` | 180–190 | `IncidentStatus` transition via `INCIDENT_STATUS_TRANSITIONS` table |
| `DiagnosisResult` | `_validate_confidence_score` | 205–210 | `confidence_score` in `[0, 1]` |
| `RemediationAction` | `_validate_status_transition` | 231–242 | `RemediationStatus` transition via `REMEDIATION_STATUS_TRANSITIONS` table |
| `OutboxEntry` | `_validate_status_transition` | 261–272 | `OutboxStatus` transition via `OUTBOX_STATUS_TRANSITIONS` table |
| `CoordinationAuditEntry` | `_validate_fields` | 295–307 | `compute_mechanism` in `ComputeMechanismToken`; `provider` in `ProviderToken` |

**Evidence — Transition Table Coverage:**

All three state machines referenced by QG-03 have both transition tables AND validators:

```
INCIDENT_STATUS_TRANSITIONS     → referenced by Incident._validate_status_transition     (line 184)
REMEDIATION_STATUS_TRANSITIONS  → referenced by RemediationAction._validate_status_transition (line 235)
OUTBOX_STATUS_TRANSITIONS       → referenced by OutboxEntry._validate_status_transition  (line 265)
```

**Evidence — Validator Pattern:**

The validators use a `previous_status` sentinel field: transition enforcement fires only when `previous_status is not None`. This correctly allows initial construction (no previous state) while blocking illegal state advances. The plan success criterion ("attempting to set an invalid status transition raises `pydantic.ValidationError`") is satisfied — the `ValueError` raised inside `model_validator` is wrapped by Pydantic into `ValidationError`.

**Severity of tracking gap:** Major — QG-03 is closed in code but not acknowledged in the changes log or plan checklist.

---

### Step 2.3 — Update Adapter and Test Construction-Site Imports

**Finding:** VACUOUS — no construction sites exist; step is effectively a no-op.

**Evidence:**

A workspace-wide grep for imports of `sre_agent.domain.models.persistence` finds exactly **one match**:

- `src/sre_agent/adapters/persistence/coordination_store.py` line 24: imports `ComputeMechanismToken` and `ProviderToken` enum values only — no model construction.

All persistence adapters construct **port DTOs** (e.g., `IncidentEventRecord`, `IncidentRecord`, `DiagnosisResultRecord`, `RemediationActionRecord`) defined as `@dataclass` in `src/sre_agent/ports/persistence.py`, not the domain model classes. These port DTOs are intentionally outside the scope of QG-01 (which targets `domain/models/`, not `ports/`).

No test file in `tests/` imports or constructs domain model instances from `sre_agent.domain.models.persistence`.

**Note:** The port-layer DTOs in `ports/persistence.py` still use `@dataclass` (lines 44, 55, 65, 84). This is a separate concern outside Phase 2 scope and is not flagged here, but should be considered for a future QG-01 extension pass if ADR-002 is interpreted to cover port DTOs as well.

**Severity:** None (step is vacuous; no impact on functionality or compliance).

---

## Finding Inventory

### Critical Findings (0)

None. All Phase 2 code requirements are met in the actual implementation.

### Major Findings (2)

| ID | Finding | Evidence |
|----|---------|---------|
| M-001 | **Changes log does not document Phase 2 completion.** The changes log (`persistence-layer-changes.md`) lists only Phase 1 deliverables (migrate.py, event_store.py, test_event_store.py, bootstrap.py, \_\_init\_\_.py). Phase 2 migration of domain models and addition of status validators is entirely absent. | Changes log lines 7–30 (Added/Modified sections only contain Phase 1 items) |
| M-002 | **Plan checklist not updated.** All three Phase 2 checklist items remain `[ ]` in the plan despite the code being fully compliant. This will cause downstream confusion for any process that relies on the checklist as authoritative state. | Plan file lines (Phase 2 checklist block); `persistence.py` lines 21, 147–310 |

### Minor Findings (1)

| ID | Finding | Evidence |
|----|---------|---------|
| m-001 | **Research document QG-01 claim is inaccurate relative to actual code state.** The research states "all 4 domain model files use `@dataclass`" but zero `@dataclass` usages exist in `src/sre_agent/domain/models/`. Either the research captured a stale state or a prior migration was never logged. This affects trust in the research as a baseline document. | Research doc, "Code Search Results" section: "all 4 domain model files use `@dataclass`"; actual code: no `@dataclass` in `domain/models/` |

### Finding Counts

| Severity | Count |
|----------|-------|
| Critical | 0 |
| Major | 2 |
| Minor | 1 |
| **Total** | **3** |

---

## Per-Step Coverage Assessment

| Step | Plan Required | Implemented in Code | Documented in Changes Log | Plan Checklist Updated |
|------|-------------|-------------------|--------------------------|----------------------|
| 2.1 — @dataclass → BaseModel | Yes | Yes — all 5 domain model files | No | No `[ ]` |
| 2.2 — Status transition validators | Yes | Yes — 3 state machines with model_validator | No | No `[ ]` |
| 2.3 — Update construction sites | Yes (conditional on sites existing) | N/A — no construction sites exist | No | No `[ ]` |

**Overall Phase 2 Code Coverage:** ~100% of stated requirements are met in the implementation.
**Tracking Coverage:** 0% — no Phase 2 activity appears in the changes log or plan checklist.

---

## Observations and Context

1. **The domain models appear to have been migrated prior to or independently of the formal Phase 2 plan.** The module-level docstring of `persistence.py` reads "Implements: Phase 4.0 Persistence Architecture Reconciliation," suggesting this work was done as part of an earlier architectural pass rather than as a response to this plan.

2. **The `previous_status` sentinel pattern is the correct Pydantic v2 approach for enforcing transitions on mutable projections.** The `Incident` and `RemediationAction` models are not `frozen=True`, which is appropriate since they represent mutable projections. `IncidentEvent` and `DiagnosisResult` correctly carry `model_config = ConfigDict(frozen=True)`.

3. **Port DTOs remain as `@dataclass`.** `src/sre_agent/ports/persistence.py` contains `LockAuditEntry`, `CooldownAuditEntry`, `OverrideAuditEntry`, and `CoordinationAuditRecord` as frozen dataclasses. If ADR-002 is interpreted to cover port-layer DTOs (not just `domain/models/`), these would also need migration. This is not in Phase 2 scope but may be a relevant follow-on item.

4. **`vector.py` is now in `domain/models/`** (not in `ports/`), which means QG-05 (`VectorDocument` misplaced in `ports/vector_store.py`) may already be partially addressed. The `ports/vector_store.py` still exists and would need to import from `domain/models/vector.py`. Verification of this is out of Phase 2 scope but should be checked during Phase 4 validation.

---

## Recommended Next Validations

- [ ] Confirm whether `ports/vector_store.py` still defines its own `VectorDocument` or now imports from `domain/models/vector.py` (Phase 4 / QG-05 validation).
- [ ] Update the plan checklist to mark Phase 2 steps as `[x]` to reflect actual code state and prevent double-work.
- [ ] Add a Phase 2 entry to the changes log documenting the domain model migration and validator additions with file paths and line references.
- [ ] Verify whether any integration test or API endpoint constructs domain model instances directly; if so, check that construction uses keyword arguments compatible with Pydantic (no positional-arg dataclass patterns).
- [ ] Assess whether `ports/persistence.py` port DTOs (`LockAuditEntry`, etc.) should be migrated under an extended QG-01 interpretation.

---

## Clarifying Questions

1. **When was the domain model migration performed?** The plan implies it was not yet done (Phase 2 unchecked), and the research explicitly listed it as a gap. Understanding whether this was done in a prior session or concurrently without documentation would clarify whether the changes log needs a retroactive entry or whether the research baseline was simply stale.

2. **Does the `previous_status` sentinel approach satisfy all QG-03 use cases?** The validators fire only when `previous_status is not None`. If callers never set this field (e.g., when updating status through an adapter that reconstructs the model from DB rows), the transition guard will never fire. Confirmation that callers are expected to populate `previous_status` when performing status updates is needed to confirm QG-03 is operationally enforced, not just structurally present.
