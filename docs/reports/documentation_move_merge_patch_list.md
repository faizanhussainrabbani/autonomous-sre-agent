# Documentation Move/Merge Patch List

**Status:** DRAFT
**Version:** 1.0.0
**Date:** 2026-03-17

## Scope

Ready-to-apply operations for consolidation work identified in `docs/reports/audit-data/documentation_audit_2026-03-17.json`.

## Patch Set A — README Consolidation

**Intent:** Keep one canonical onboarding narrative while preserving docs index usability.

### A1. Merge `docs/README.md` into root `README.md`

- Keep root `README.md` as canonical entry point.
- Retain `docs/README.md` as a short navigation index only.

```bash
# 1) manually merge overlapping overview sections
# source: docs/README.md
# target: README.md

# 2) reduce docs/README.md to directory index + links only
```

## Patch Set B — Roadmap Consolidation

**Intent:** Remove dual roadmap ownership between architecture and project planning.

### B1. Merge strategy timeline into project roadmap

```bash
# Manual content merge:
# source: docs/architecture/evolution/roadmap.md
# target: docs/project/roadmap.md
```

### B2. Replace architecture roadmap with pointer page

```bash
# after merge completion
mv docs/architecture/evolution/roadmap.md docs/architecture/evolution/roadmap.archived.md
# create a new lightweight roadmap.md pointing to docs/project/roadmap.md
```

## Patch Set C — Archive Acceptance Criteria Normalization

**Intent:** Normalize repeated acceptance-criteria naming in archive reports.

### C1. Rename to phase-specific filenames

```bash
mv docs/reports/archive/phase-1-data-foundation/acceptance_criteria.md \
   docs/reports/archive/phase-1-data-foundation/phase_1_acceptance_criteria.md

mv docs/reports/archive/phase-2.2-token-optimization/acceptance_criteria.md \
   docs/reports/archive/phase-2.2-token-optimization/phase_2_2_acceptance_criteria.md
```

### C2. Update inbound references after rename

```bash
# update links in docs/reports/archive/** and docs/reports/**
# replace acceptance_criteria.md references with phase-specific filenames
```

## Patch Set D — Optional OpenSpec Historical Cleanup

**Intent:** Reduce topic noise while preserving change history.

### D1. Do not merge OpenSpec `design.md`/`proposal.md` across changes

OpenSpec files are intentionally per-change artifacts; merging them would remove decision traceability. Instead:

```bash
# optional: add index docs instead of merging historical specs
# create openspec/changes/README.md with links grouped by phase and topic
```

## Execution Order

1. Patch Set A
2. Patch Set B
3. Patch Set C
4. Link validation + final docs index refresh

## Validation Commands

```bash
# verify no broken relative links in docs
python3 scripts/validate_links.py  # if available

# fallback lightweight check
rg -n "\]\((\.\.?/|[^h#][^)]+)\)" docs | head -100
```
