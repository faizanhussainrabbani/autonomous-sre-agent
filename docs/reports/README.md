---
title: Reports Index
description: Canonical index and lifecycle taxonomy for report artifacts and evidence in the documentation set.
ms.date: 2026-03-27
ms.topic: reference
author: SRE Agent Engineering Team
status: APPROVED
---

## Purpose

This directory stores time-bound reporting artifacts, implementation evidence, and validation outputs.

## Directory taxonomy

| Folder | Content type | Naming pattern |
|---|---|---|
| `acceptance-criteria/` | Pass and fail criteria used before implementation closeout | `*_acceptance_criteria.md` |
| `planning/` | Execution plans and implementation plans | `*_execution_plan.md`, `*_implementation_plan.md` |
| `compliance/` | Checks that evaluate plan conformance | `*_plan_compliance_check.md` |
| `validation/` | Runtime or checklist-based run validations | `*_run_validation.md` |
| `verification/` | Final verification reports against acceptance criteria | `*_verification_report.md` |
| `analysis/` | Research, reviews, evaluations, gap analysis, and traceability reports | free-form report names |
| `archive/` | Historical artifacts retained for traceability | historical files and folders |
| `audit-data/` | Source inventory and audit datasets | `.json`, `.csv` |
| `plan/` | Legacy plan artifacts pending migration to `planning/` | project-specific files |

## Placement rules

* Place new report files in the folder that matches their lifecycle stage.
* Keep report names stable and descriptive to preserve traceability from `CHANGELOG.md` and operations guides.
* Use repository-relative links when referencing reports across documentation domains.
* Move obsolete evidence to `archive/` instead of deleting historical records.

## Maintenance workflow

* When adding a new implementation stream, create the full artifact chain: planning, acceptance criteria, verification report, and run validation.
* Update cross-references in related docs when file paths change.
* Keep this index aligned with folder structure and naming policy.
