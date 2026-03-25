---
title: Documentation Restructure Execution Plan
description: Step 1 implementation blueprint for phased documentation restructuring across README, docs navigation, architecture, development, reference, ADR, and governance artifacts.
ms.date: 2026-03-19
ms.topic: how-to
author: GitHub Copilot
status: APPROVED
version: "1.1"
---

## Scope and objectives

This plan implements the approved critical review and executes Phases 1 through 4 in sequence with controlled migration.

Primary objectives:

* Make root navigation concise and role-oriented for contributors, operators, maintainers, and automation agents
* Add a deterministic getting-started path without breaking existing operational documentation
* Separate conceptual architecture documentation from operational runbooks while preserving current stable paths
* Introduce development and reference navigation domains as non-destructive overlays
* Expand ADR coverage for coordination and safety decisions
* Add documentation governance controls: lifecycle policy, taxonomy, glossary authority, and measurable SLOs

## Areas to be addressed during execution

### Phase 1: Navigation hardening

* Update `README.md` to be short, action-oriented, and safety-first
* Add `docs/getting-started.md` as the canonical first-run path
* Update `docs/README.md` so role-based routing is first-class

### Phase 2: Conceptual separation

* Add `docs/architecture/overview.md`
* Add `docs/architecture/multi-agent-coordination.md`
* Add `docs/architecture/permissions-and-rbac.md`

### Phase 3: Domain alignment without destructive migration

* Introduce `docs/development/` navigation pages and links to current canonical docs
* Introduce `docs/reference/` navigation pages and links to current canonical docs
* Keep existing `docs/project/`, `docs/security/`, and `docs/testing/` paths active

### Phase 4: Governance and ADR normalization

* Add ADRs for coordination backend, remediation safety boundaries, and priority/preemption policy
* Add documentation lifecycle policy for active vs archived artifacts

### Additional recommendations for precision and longevity

* Add document type taxonomy guidance
* Establish stable term authority through canonical glossary routing
* Add documentation quality SLOs with measurable targets

## Dependencies, risks, and assumptions

### Dependencies

* Existing canonical docs remain available during migration overlay
* Existing architecture and runbook docs provide source material for new landing pages
* Current markdown rules and frontmatter requirements are enforced for all new files

### Assumptions

* No destructive path moves are required in this execution
* Existing runbook and security docs remain the canonical operational sources until explicitly superseded
* Root `CHANGELOG.md` is the active changelog target for this work

### Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Link breakage from new navigation | High | Use relative links only and run post-change link validation |
| Content duplication drift | Medium | Use pointer-style pages and identify canonical source in each new page |
| Inconsistent policy authority between `AGENTS.md` and architecture docs | High | Explicitly declare authority chain in coordination documents |
| Excessive root README detail regrowth | Medium | Keep README concise and route details to `docs/getting-started.md` and docs index |
| Standards non-compliance | Medium | Perform explicit Step 2 compliance review before execution |

## File and module breakdown of changes

### Files to create

* `docs/getting-started.md`
* `docs/architecture/overview.md`
* `docs/architecture/multi-agent-coordination.md`
* `docs/architecture/permissions-and-rbac.md`
* `docs/development/README.md`
* `docs/development/setup.md`
* `docs/development/testing.md`
* `docs/development/code-style.md`
* `docs/development/contributing.md`
* `docs/reference/README.md`
* `docs/reference/api.md`
* `docs/reference/commands.md`
* `docs/reference/runbooks.md`
* `docs/reference/glossary.md`
* `docs/reference/document-taxonomy.md`
* `docs/project/standards/documentation_lifecycle_policy.md`
* `docs/project/standards/documentation_quality_slos.md`
* `docs/project/ADRs/003-coordination-backend-selection.md`
* `docs/project/ADRs/004-remediation-safety-boundaries.md`
* `docs/project/ADRs/005-multi-agent-priority-preemption.md`
* `docs/reports/documentation_restructure_acceptance_criteria.md` (Step 3)
* `docs/reports/documentation_restructure_verification_report.md` (Step 5)
* `docs/reports/documentation_restructure_run_validation.md` (Step 6)

### Files to update

* `README.md`
* `docs/README.md`
* `docs/project/glossary.md`
* `CHANGELOG.md`
* `docs/reports/documentation_optimization_critical_review.md` (link references if required)

## Execution sequence and controls

1. Complete Step 2 compliance review and apply plan updates before edits
2. Create Step 3 acceptance criteria mapped to this plan sections
3. Execute file edits exactly by phase order
4. Verify each acceptance criterion with explicit pass or fail evidence
5. Run link and markdown validation against changed files
6. Update changelog with references to Step 1 and Step 3 artifacts

## Out-of-scope constraints

* No removal of existing docs directories in this execution
* No bulk relocation of historical docs in this execution
* No source code logic changes under `src/`
