---
title: Best Engineering Teams Practices Gap Research Acceptance Criteria
description: Step 3 measurable acceptance criteria for research, gap analysis, compliance, verification, and validation outputs.
ms.date: 2026-03-27
ms.topic: reference
author: SRE Agent Engineering Team
---

## 1. Acceptance criteria list

| ID | Criterion (pass or fail) | Plan traceability |
|----|---------------------------|-------------------|
| AC-01 | A plan document exists at the planned path and contains scope, objectives, execution areas, dependencies, risks, assumptions, and file breakdown. | Plan Sections 1, 2, 3, 4 |
| AC-02 | Compliance-check document exists and explicitly evaluates plan alignment against all three required standards documents. | Plan Section 5, Step 2 |
| AC-03 | Analysis report contains a source-backed benchmark across reliability, delivery, testing, security/supply-chain, and learning-loop practices. | Plan Section 2.1 |
| AC-04 | Analysis report contains a repository-specific gap matrix with at least: current state, missing control, impact, effort, confidence, and recommendation. | Plan Section 2.2 |
| AC-05 | Analysis report includes prioritized roadmap with dependency ordering and measurable milestones (P0/P1/P2 or equivalent). | Plan Section 2.3 |
| AC-06 | Any recommendation requiring external admin/org permissions is explicitly labeled as external enablement required. | Plan Sections 3.2, 3.3, 3.4 |
| AC-07 | Verification report evaluates every acceptance criterion AC-01 through AC-10 with explicit pass/fail and evidence. | Plan Section 2.4, Step 5 |
| AC-08 | Run-validation report documents commands executed, outputs observed, and final validation outcome. | Plan Section 2.4, Step 6 |
| AC-09 | All created markdown artifacts include required frontmatter and conform to repository markdown conventions. | Plan Section 6; standards in Step 2 |
| AC-10 | `CHANGELOG.md` includes a structured entry with what changed, why, files affected, and references to plan and acceptance-criteria artifacts. | Plan Section 4.2, Step 7 |

## 2. Edge-case and standards compliance checks

### 2.1 Edge-case criteria

| ID | Criterion (pass or fail) | Traceability |
|----|---------------------------|--------------|
| EC-01 | If a source page is partially inaccessible or low fidelity, the analysis uses alternate authoritative sources and marks confidence appropriately. | Plan Sections 3.2, 3.3 |
| EC-02 | If a control cannot be directly implemented from this repository (for example branch protection settings), the recommendation is still captured with implementation path and ownership boundary. | Plan Sections 3.3, 3.4 |
| EC-03 | Recommendations avoid unsupported claims and include confidence grading where evidence strength differs. | Plan Sections 2.1, 6 |

### 2.2 Standards compliance criteria

| ID | Criterion (pass or fail) | Traceability |
|----|---------------------------|--------------|
| SC-01 | Artifacts follow documentation-as-code structure and remain maintainable under `docs/reports/` taxonomy. | Plan Section 4 |
| SC-02 | Verification approach is deterministic, explicit, and evidence-oriented, consistent with repository testing strategy expectations. | Plan Sections 2.4, 6 |
| SC-03 | Output remains repository-specific and does not prescribe generic controls without mapping to current codebase state. | Plan Sections 2.2, 2.3 |

## 3. Completion rule

Execution is complete only when all AC, EC, and SC criteria are evaluated in Step 5 and unresolved failures are either fixed or explicitly documented with constrained next actions.
