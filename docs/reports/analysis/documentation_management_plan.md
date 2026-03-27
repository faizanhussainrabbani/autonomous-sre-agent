---
title: Documentation Management Plan — Comprehensive Evaluation
description: Full audit of all 145 markdown files in the repository with severity-graded findings and a concrete management plan.
ms.date: 2026-03-12
version: "1.0"
status: "APPROVED"
author: "GitHub Copilot"
---

# Documentation Management Plan — Comprehensive Evaluation

> **Scope:** All 145 markdown files across `docs/`, `phases/`, `openspec/`, `.agent/`, `.claude/`, `.specify/`, and root-level  
> **Date:** March 12, 2026  
> **Goal:** Eliminate duplication, promote DRAFT docs to APPROVED, archive point-in-time reports, and establish maintenance discipline.

---

## 1. Current State Summary

| Zone | Files | Status |
|---|---|---|
| Root level | 6 | Mixed — 2 ad-hoc research docs out of place |
| `docs/architecture/` | 17 | All DRAFT; core content is accurate but statuses are stale |
| `docs/api/` | 1 | DRAFT; content is valid |
| `docs/operations/` | 13 (inc. 5 runbooks) | All DRAFT; some placeholders only |
| `docs/project/` | 11 | 2 exact/near-duplicates confirmed |
| `docs/reports/` | 12 | Mix of point-in-time reports and living improvement docs |
| `docs/security/` | 4 | DRAFT; high-value content, unused |
| `docs/testing/` | 8 | 4 overlapping LocalStack / E2E docs |
| `phases/` | 5 | Inconsistent — only 3 phases represented |
| `openspec/changes/` | 39 | Active workflow format; well-structured |
| `.agent/workflows/` | 4 | Agent skill files — correct location |
| `.claude/commands/` | 9 | Claude slash-command templates — correct location |
| `.specify/` | 6 | Spec tooling config — correct location |

**Total unique content docs requiring active management:** ~80  
**39 docs** still carry `Status: DRAFT` despite representing implemented, shipped features.

---

## 2. Findings — Categorized by Severity

### 🔴 CRITICAL — Remove or Fix Immediately

#### C-1: Exact Duplicate Files — `engineering_standards.md`

`docs/project/engineering_standards.md` and `docs/project/standards/engineering_standards.md` are **byte-for-byte identical** (660 lines each).

**Action:** Delete `docs/project/engineering_standards.md`. Update `docs/README.md` to reference the canonical path `docs/project/standards/engineering_standards.md` only.

#### C-2: Near-Duplicate Files — `FAANG_Documentation_Standards.md`

`docs/project/FAANG_Documentation_Standards.md` and `docs/project/standards/FAANG_Documentation_Standards.md` differ only in relative link paths (2 lines).

**Action:** Delete `docs/project/FAANG_Documentation_Standards.md`. Adopt `docs/project/standards/` as the canonical home for all standards documents.

#### C-3: CHANGELOG Duplication — `docs/project/CHANGELOG.md` Was Deleted But Root `CHANGELOG.md` Exists

The root `CHANGELOG.md` is the correct location. The `docs/project/CHANGELOG.md` was already deleted in the last commit. Verify `docs/README.md` does not still link to it.

---

### 🟠 HIGH — Address Within the Next Sprint

#### H-1: 39 DRAFT Documents Representing Shipped Code

Every document under `docs/architecture/layers/`, `docs/architecture/models/`, `docs/api/api_contracts.md`, all runbooks under `docs/operations/runbooks/`, and most of `docs/security/` carry `Status: DRAFT` despite the features they describe being fully implemented and tested. This creates false uncertainty for new contributors.

**Affected files (representative sample):**
- All 7 layer architecture docs (`action_layer.md`, `detection_layer.md`, etc.)
- `docs/api/api_contracts.md`
- `docs/operations/runbooks/deployment.md`, `incident_response.md`, `agent_failure_runbook.md`, `kill_switch.md`
- `docs/security/threat_model.md`, `guardrails_configuration.md`, `features_and_safety.md`
- `docs/project/engineering_standards.md` / `docs/project/standards/engineering_standards.md`
- `docs/project/onboarding.md`, `docs/project/glossary.md`

**Action:** Run a bulk DRAFT → APPROVED promotion pass. A document is ready to promote when its described feature has passing tests and merged code. Use the rule: _if it has `Status: DRAFT` and the corresponding code is in `main`, it should be `APPROVED`._

#### H-2: `docs/testing/` — Four Overlapping LocalStack/E2E Docs

These four docs describe overlapping testing concerns without clear differentiation:

| File | Lines | Scope |
|---|---|---|
| `testing_strategy.md` | 1,340 | Comprehensive strategy + pyramid — APPROVED |
| `e2e_testing_plan.md` | 550 | Phase 1/1.5 E2E plan — DRAFT, superseded |
| `localstack_pro_live_testing_plan.md` | 742 | Live LocalStack Pro plan — superseded by actual scripts |
| `localstack_e2e_live_specs.md` | 87 | BDD specs — partial, never completed |

**Action:**
- **Keep:** `testing_strategy.md` as the single source of truth for test organization.
- **Archive to `docs/reports/`:** `e2e_testing_plan.md` and `localstack_pro_live_testing_plan.md` as historical planning artifacts.
- **Delete:** `localstack_e2e_live_specs.md` — 87 lines of incomplete BDD specs that were never implemented. The actual test files in `tests/` serve as the executable specification.

#### H-3: `docs/architecture/phase_2_2_token_optimization.md` Is Mislocated (778 lines)

This is a detailed implementation strategy + execution doc for a specific phase initiative. Placing it under `docs/architecture/` implies it is architectural reference; it is actually a phase implementation report.

**Action:** Move to `docs/reports/analysis/phase_2_2_token_optimization_report.md` and add a stub `docs/architecture/phase_2_2_token_optimization.md` that links to it.

#### H-4: Two Ad-Hoc Research Docs at Root Level

`ai_agent_architecture_research.md` (215 lines) and `alignment_report.md` (72 lines) sit at the project root, breaking the rule that root-level markdown files are only project governance docs (README, CHANGELOG, CONTRIBUTING, AGENTS).

**Action:** Move both to `docs/reports/`:
- `ai_agent_architecture_research.md` → `docs/reports/analysis/ai_agent_architecture_research.md`
- `alignment_report.md` → `docs/reports/analysis/alignment_report.md`

Update all inbound links.

---

### 🟡 MEDIUM — Address Within the Next Month

#### M-1: `docs/reports/` Is a Dump of Temporal One-Off Reports

The `docs/reports/` folder contains 12 documents ranging from formal verification reports to informal progress snapshots. There is no clear lifecycle policy — reports accumulate indefinitely.

**Current reports inventory:**

| File | Type | Recommendation |
|---|---|---|
| `documentation_review.md` | Point-in-time audit (Jan 2025) | Archive — superseded by this plan |
| `gap_closure_report.md` | Phase 2 gap closure | Keep — valuable historical record |
| `implementation_progress.md` | Phase 2 snapshot | Archive — superseded by CHANGELOG |
| `live_demo_evaluation.md` | Demo 7 evaluation | Keep — valuable post-mortem |
| `localstack_test_resolution.md` | Test fix log | Archive — no longer actionable |
| `observability_improvement_areas.md` | Improvement backlog | Keep — actionable if work is planned |
| `phase_1_5_test_findings.md` | Phase 1.5 test findings | Keep — useful regression baseline |
| `phase_1_status.md` | 33-line status stub | **Delete** — no content; phase is done |
| `phase_2_changelog.md` | Phase 2 change log | Archive — duplicates root CHANGELOG |
| `improvement_areas_phase_1_5.md` | Improvement backlog (DRAFT) | Merge content into roadmap, then delete |
| `aws_data_collection_review.md` | Phase 2.3 pre-work review | Keep — needed to understand Phase 2.3 |
| `phase_2_3_verification_report.md` | Phase 2.3 verification | Keep — formal test evidence |

**Policy to adopt:** Reports older than 2 phases that have no open action items move to a `docs/reports/archive/` subfolder. Non-substantive stubs (< 50 lines, no open actions) are deleted.

#### M-2: `phases/` Directory is Incomplete

`phases/` contains entries for phase-1-data-foundation and phase-2.2-token-optimization but nothing for phase-1.5, phase-2.1, or phase-2.3.

**Action:** Either commit to using `phases/` as the canonical phase-tracking location (and add missing phases) or retire it in favor of `openspec/changes/` (which has better coverage). Don't maintain both half-heartedly.

**Recommended decision:** Archive `phases/` content into `docs/reports/` and remove the directory. `openspec/changes/` is the designated spec/phase workflow tool.

#### M-3: `docs/project/phase_2_preparation_guide.md` Is a Temporary Artifact

This document (a pre-Phase-2 readiness checklist) served its purpose during planning. Phase 2 is now complete.

**Action:** Move to `docs/reports/archive/phase_2_preparation_guide.md`.

#### M-4: `docs/operations/localstack_live_incident_demo.md` Documents Demo 7 Only

Now that Demo 8 (ECS multi-service cascade) exists, this doc covers Lambda/Demo 7 only. It should either be generalized or supplemented.

**Action:** Add a `docs/operations/live_demo_guide.md` as a single landing page linking to both demos' setup instructions and scripts. Keep `localstack_live_incident_demo.md` as the Lambda-specific deep dive.

#### M-5: `docs/operations/ci_cd_pipeline.md` and `docs/operations/operational_readiness.md` Are Pure Stubs

Both are DRAFT with minimal or placeholder content.

**Action:** Either populate them (if CI/CD and production readiness are actively being planned) or delete them. Stub documents signal false confidence in having a process that doesn't exist yet.

#### M-6: Runbooks Need Actual Content

Five runbooks under `docs/operations/runbooks/` are marked DRAFT:

- `deployment.md`
- `incident_response.md`
- `agent_failure_runbook.md`
- `kill_switch.md`
- `phase_management.md`

These are high-value operational documents that on-call engineers would reach for in a crisis. DRAFT runbooks in production are dangerous.

**Action:** Assign each runbook to a team member for review and promotion to APPROVED before the project moves to a production environment.

---

### 🟢 LOW — Housekeeping (Do When Convenient)

#### L-1: `docs/project/ADRs/000-template.md` Should Be Unexposed

The ADR template document appears alongside actual ADRs (001, 002) in the same folder, which can be confusing.

**Action:** Rename to `docs/project/ADRs/_template.md` (underscore prefix) so it appears clearly as metadata rather than a decision.

#### L-2: `docs/reports/archive/documentation_review.md` (Jan 2025) Is Superseded

The previous documentation review is now superseded by this document.

**Action:** Keep it in `docs/reports/archive/` as superseded historical reference.

#### L-3: `.specify/memory/` Docs Should Stay Internal

`constitution.md` and `engineering_standards.md` under `.specify/memory/` are tool-specific configuration files masquerading as documentation. They are not part of the project's documentation surface.

**Action:** Verify they are consumed only by the `speckit` CLI toolchain and not cross-referenced from `docs/`. Add a note in `.specify/README.md` (if it exists) distinguishing framework memory from project docs.

#### L-4: `docs/architecture/evolution/` Has Only 2 Files, Both Incomplete

`phase_1_5_migration.md` (65 lines, DRAFT) and `target_architecture.md` (79 lines, DRAFT) describe the eventual multi-cloud target state but are underdeveloped.

**Action:** Merge both into a single `docs/architecture/evolution/roadmap.md` that covers the phased evolution path (K8s → Phase 1.5 → Phase 2.x → target state) and promote from DRAFT to APPROVED.

---

## 3. Recommended Folder Structure (Target State)

```
docs/
├── README.md                          ← Master index (always keep current)
├── api/
│   └── api_contracts.md
├── architecture/
│   ├── architecture.md                ← Promote to APPROVED
│   ├── Technology_Stack.md
│   ├── dependency_graph.md
│   ├── extensibility.md
│   ├── sequence_incident_lifecycle.md
│   ├── evolution/
│   │   └── roadmap.md                 ← Merge phase_1_5_migration + target_architecture
│   ├── layers/                        ← All 6 layer docs → promote to APPROVED
│   └── models/                        ← All 3 model docs → promote to APPROVED
├── operations/
│   ├── external_dependencies.md
│   ├── live_demo_guide.md             ← NEW: landing page for Demo 7 + Demo 8
│   ├── localstack_live_incident_demo.md
│   ├── slos_and_error_budgets.md
│   ├── aws_data_collection_improvements.md
│   └── runbooks/                      ← All 5 runbooks → promote to APPROVED
├── project/
│   ├── onboarding.md
│   ├── glossary.md
│   ├── roadmap.md
│   ├── ADRs/
│   │   ├── _template.md               ← Renamed from 000-template.md
│   │   ├── 001-hexagonal-architecture.md
│   │   └── 002-pydantic-over-dataclasses.md
│   └── standards/                     ← CANONICAL location for standards
│       ├── engineering_standards.md
│       └── FAANG_Documentation_Standards.md
├── reports/
│   ├── ai_agent_architecture_research.md   ← Moved from root
│   ├── alignment_report.md                 ← Moved from root
│   ├── aws_data_collection_review.md
│   ├── documentation_management_plan.md    ← This file
│   ├── gap_closure_report.md
│   ├── live_demo_evaluation.md
│   ├── observability_improvement_areas.md
│   ├── phase_1_5_test_findings.md
│   ├── phase_2_2_token_optimization_report.md  ← Moved from architecture/
│   ├── phase_2_3_verification_report.md
│   └── archive/                        ← Point-in-time reports with no active actions
│       ├── documentation_review.md
│       ├── e2e_testing_plan.md
│       ├── implementation_progress.md
│       ├── localstack_test_resolution.md
│       ├── localstack_pro_live_testing_plan.md
│       ├── phase_1_status.md           ← Or delete (33-line stub)
│       ├── phase_2_changelog.md
│       ├── phase_2_preparation_guide.md
│       └── improvement_areas_phase_1_5.md
├── security/
│   ├── features_and_safety.md         ← Promote to APPROVED
│   ├── guardrails_configuration.md    ← Promote to APPROVED
│   ├── security_review.md
│   └── threat_model.md               ← Promote to APPROVED
└── testing/
    ├── testing_strategy.md            ← Keep as canonical; promote to APPROVED
    ├── bugs.md
    ├── live_validation_test_cases.md
    ├── localstack_pro_guide.md
    └── test_infrastructure.md
```

**Deleted (not just archived):**
- `docs/project/engineering_standards.md` — exact duplicate
- `docs/project/FAANG_Documentation_Standards.md` — near-duplicate
- `docs/testing/localstack_e2e_live_specs.md` — incomplete, never implemented
- `phase_1_status.md` (deleted stub) — 33-line stub with no content
- `phases/` directory — retire in favor of `openspec/changes/`

---

## 4. Concrete Action Plan

### Sprint 1 (This Week) — De-duplicate and Clean Up

| # | Action | Owner | Effort |
|---|---|---|---|
| 1 | Delete `docs/project/engineering_standards.md` (exact duplicate) | Any | 5 min |
| 2 | Delete `docs/project/FAANG_Documentation_Standards.md` (near-duplicate) | Any | 5 min |
| 3 | Delete `phase_1_status.md` (empty stub) | Any | 5 min |
| 4 | Delete `docs/testing/localstack_e2e_live_specs.md` (never implemented) | Any | 5 min |
| 5 | Move `ai_agent_architecture_research.md` → `docs/reports/` | Any | 10 min |
| 6 | Move `alignment_report.md` → `docs/reports/` | Any | 10 min |
| 7 | Create `docs/reports/archive/` and move 8 point-in-time reports there | Any | 20 min |
| 8 | Update all broken links after above moves | Any | 30 min |

### Sprint 2 (Next Week) — Promote DRAFT Docs

| # | Action | Owner | Effort |
|---|---|---|---|
| 9 | Promote all 6 architecture layer docs from DRAFT to APPROVED | Arch lead | 1 hr |
| 10 | Promote 3 architecture model docs from DRAFT to APPROVED | Arch lead | 30 min |
| 11 | Promote `docs/api/api_contracts.md` from DRAFT to APPROVED | API lead | 1 hr |
| 12 | Promote all 4 security docs from DRAFT to APPROVED | Security lead | 2 hr |
| 13 | Promote `docs/project/onboarding.md` and `glossary.md` | DX lead | 1 hr |
| 14 | Promote `docs/testing/testing_strategy.md` to APPROVED | QA lead | 30 min |

### Sprint 3 (Month 1) — Fill Gaps

| # | Action | Owner | Effort |
|---|---|---|---|
| 15 | Merge `phase_1_5_migration.md` + `target_architecture.md` → `evolution/roadmap.md` | Arch lead | 2 hr |
| 16 | Write `docs/operations/live_demo_guide.md` covering Demo 7 + Demo 8 | SRE lead | 1 hr |
| 17 | Populate or delete `docs/operations/ci_cd_pipeline.md` | DevOps lead | 1 hr |
| 18 | Populate or delete `docs/operations/operational_readiness.md` | SRE lead | 1 hr |
| 19 | Promote all 5 runbooks from DRAFT to APPROVED | On-call team | 3 hr |
| 20 | Move `docs/project/phase_2_preparation_guide.md` to archive | Any | 5 min |
| 21 | Move `docs/architecture/phase_2_2_token_optimization.md` to reports | Arch lead | 10 min |
| 22 | Retire `phases/` directory — move content to `docs/reports/archive/` | Any | 30 min |
| 23 | Rename `docs/project/ADRs/000-template.md` → `_template.md` | Any | 5 min |
| 24 | Update `docs/README.md` to reflect new structure | Doc lead | 1 hr |

---

## 5. Documentation Maintenance Rules (Going Forward)

Add these rules to `CONTRIBUTING.md`:

1. **No DRAFT in production.** Any document describing a feature that has passing tests and merged code must be promoted to `APPROVED` in the same PR that merges the feature.

2. **One source of truth per topic.** Before creating a new document, check if an existing doc covers the topic. If a new doc supersedes an old one, archive or delete the old one in the same PR.

3. **Reports go in `docs/reports/`.** One-off analysis, phase reviews, and verification reports belong in `docs/reports/`. Architecture docs belong in `docs/architecture/`. Do not mix.

4. **Archive, don't delete history (unless it's a stub).** When a doc becomes outdated, move it to `docs/reports/archive/` with an `## Archived` section at the top explaining what superseded it. Delete only if the file has < 50 lines and no historical value.

5. **Root-level markdown = governance only.** Only `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, and `AGENTS.md` belong at the project root. Research, reports, and plans go in `docs/`.

6. **`openspec/changes/` is the active spec workflow.** New feature proposals, designs, and acceptance criteria go through `openspec/changes/`. The `phases/` directory is retired.

---

## 6. Summary of Files to Delete (Immediate)

| File | Reason |
|---|---|
| `docs/project/engineering_standards.md` | Exact byte-for-byte duplicate of `docs/project/standards/engineering_standards.md` |
| `docs/project/FAANG_Documentation_Standards.md` | Near-duplicate of `docs/project/standards/FAANG_Documentation_Standards.md` |
| `phase_1_status.md` (deleted) | 33-line empty status stub; information is in CHANGELOG |
| `docs/testing/localstack_e2e_live_specs.md` | 87 lines of incomplete BDD specs; never implemented |

**Total immediate deletes: 4 files**

## 7. Summary of Files to Move

| From | To | Reason |
|---|---|---|
| `ai_agent_architecture_research.md` | `docs/reports/analysis/ai_agent_architecture_research.md` | Research reports don't belong at root |
| `alignment_report.md` | `docs/reports/analysis/alignment_report.md` | Reports don't belong at root |
| `docs/architecture/phase_2_2_token_optimization.md` | `docs/reports/analysis/phase_2_2_token_optimization_report.md` | Phase report, not architecture reference |
| `docs/project/phase_2_preparation_guide.md` | `docs/reports/archive/phase_2_preparation_guide.md` | Phase complete; archive |
| `docs/reports/archive/documentation_review.md` | `docs/reports/archive/documentation_review.md` | Superseded by this plan |
| `docs/reports/archive/implementation_progress.md` | `docs/reports/archive/implementation_progress.md` | Superseded by CHANGELOG |
| `docs/reports/archive/localstack_test_resolution.md` | `docs/reports/archive/localstack_test_resolution.md` | No longer actionable |
| `docs/reports/archive/phase_2_changelog.md` | `docs/reports/archive/phase_2_changelog.md` | Duplicates root CHANGELOG |
| `docs/reports/archive/improvement_areas_phase_1_5.md` | `docs/reports/archive/improvement_areas_phase_1_5.md` | Superseded by roadmap |
| `docs/testing/e2e_testing_plan.md` | `docs/reports/archive/e2e_testing_plan.md` | Superseded by testing_strategy.md |
| `docs/testing/localstack_pro_live_testing_plan.md` | `docs/reports/archive/localstack_pro_live_testing_plan.md` | Superseded by actual scripts |
| `phases/phase-1-5-review.md` | `docs/reports/archive/phase_1_5_review.md` | Phase complete; archive |
| `phases/phase-1-data-foundation/` | `docs/reports/archive/phase_1_data_foundation/` | Phase complete; archive |
| `phases/phase-2.2-token-optimization/` | `docs/reports/archive/phase_2_2_token_optimization/` | Phase complete; archive |

**Total moves: 14 files/directories**

---

*This document itself should be treated as living documentation. Update it as actions are completed.*
