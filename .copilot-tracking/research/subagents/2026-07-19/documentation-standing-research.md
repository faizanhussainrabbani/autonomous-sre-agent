---
title: Documentation Standing Research
description: Consistency analysis of architecture and capability docs versus implemented/planned status claims.
ms.date: 2026-07-19
ms.topic: reference
status: DRAFT
owner: Researcher Subagent
---

## Research status

Complete for requested scope.

## Research topics and questions

- Analyze repository-level and architecture docs that describe capabilities and phase status.
- Identify what is documented as implemented/current versus planned/future.
- Detect stale or conflicting documentation statements.
- Provide exact evidence references with file paths and line numbers.

## Scope covered

- README.md
- master_system_document.md
- docs/getting-started.md
- docs/architecture/* (including overview, architecture, evolution roadmap, technology stack, extensibility, persistence)
- docs/project/standards/*

## Implemented vs planned claims map

### Claimed as implemented/current

- Top-level README claims full incident loop execution and cross-platform operators.
  - Evidence: README.md:16
  - Evidence: README.md:21
- Master system document claims Phase 1, 1.5, and 2 are complete.
  - Evidence: master_system_document.md:48
  - Evidence: master_system_document.md:49
  - Evidence: master_system_document.md:50
- Master system document claims observability, detection, and intelligence are implemented.
  - Evidence: master_system_document.md:99
  - Evidence: master_system_document.md:100
  - Evidence: master_system_document.md:101
- Roadmap claims Phase 1 production readiness and all architecture layers implemented/tested.
  - Evidence: docs/architecture/evolution/roadmap.md:24
  - Evidence: docs/architecture/evolution/roadmap.md:37
- Roadmap claims remediation is complete in Phase 1 and Phase 1.5 cloud operators are full support.
  - Evidence: docs/architecture/evolution/roadmap.md:34
  - Evidence: docs/architecture/evolution/roadmap.md:52
  - Evidence: docs/architecture/evolution/roadmap.md:53
  - Evidence: docs/architecture/evolution/roadmap.md:54
  - Evidence: docs/architecture/evolution/roadmap.md:55
  - Evidence: docs/architecture/evolution/roadmap.md:56

### Claimed as planned/future/deferred

- Master system document marks action and operator layers as planned; Phase 3 remediation is next.
  - Evidence: master_system_document.md:51
  - Evidence: master_system_document.md:102
  - Evidence: master_system_document.md:103
- architecture.md marks intelligence, action, and target infrastructure as planned.
  - Evidence: docs/architecture/architecture.md:13
  - Evidence: docs/architecture/architecture.md:14
  - Evidence: docs/architecture/architecture.md:15
- overview.md says Azure App Service latency support is deferred to Phase 2.5B pending Azure Monitor adapter.
  - Evidence: docs/architecture/overview.md:88
- extensibility.md says current telemetry support is OTel backends only.
  - Evidence: docs/architecture/extensibility.md:11
- Technology_Stack still contains pending/open decisions and planned statuses in several sections.
  - Evidence: docs/architecture/Technology_Stack.md:58
  - Evidence: docs/architecture/Technology_Stack.md:59
  - Evidence: docs/architecture/Technology_Stack.md:188
  - Evidence: docs/architecture/Technology_Stack.md:189
  - Evidence: docs/architecture/Technology_Stack.md:206

## Top findings: stale/conflicting documentation

1. Direct conflict on intelligence/action implementation status.
- master_system_document.md says intelligence is implemented and Phase 2 complete.
  - Evidence: master_system_document.md:50
  - Evidence: master_system_document.md:101
- docs/architecture/architecture.md says intelligence and action are planned.
  - Evidence: docs/architecture/architecture.md:13
  - Evidence: docs/architecture/architecture.md:14
- Impact: readers cannot determine whether diagnosis and remediation orchestration are production-ready.

2. Roadmap says all architecture layers implemented, while master doc still marks action/operator planned.
- Roadmap: all architecture layers implemented and tested.
  - Evidence: docs/architecture/evolution/roadmap.md:37
- Master doc: action/operator planned and Phase 3 next.
  - Evidence: master_system_document.md:51
  - Evidence: master_system_document.md:102
  - Evidence: master_system_document.md:103
- Impact: contradictory program status across two architecture authorities.

3. Telemetry backend support scope conflicts across docs.
- extensibility.md says current support is OTel collector backends only.
  - Evidence: docs/architecture/extensibility.md:11
- master_system_document.md says CloudWatch and New Relic adapters are implemented.
  - Evidence: master_system_document.md:193
  - Evidence: master_system_document.md:198
  - Evidence: master_system_document.md:199
- roadmap also lists CloudWatch/Azure Monitor additions in Phase 1.5.
  - Evidence: docs/architecture/evolution/roadmap.md:60
  - Evidence: docs/architecture/evolution/roadmap.md:61
- Impact: integration boundary guidance is stale for extension authors.

4. Azure support appears both full-support and deferred depending on document and feature slice.
- Roadmap claims full support for Azure App Services and Azure Functions.
  - Evidence: docs/architecture/evolution/roadmap.md:55
  - Evidence: docs/architecture/evolution/roadmap.md:56
- overview.md says App Service response-time metric support is deferred to Phase 2.5B.
  - Evidence: docs/architecture/overview.md:88
- Impact: likely not a true contradiction if interpreted as "operator support present, specific telemetry metric deferred," but this distinction is undocumented and causes ambiguity.

5. Persistence authority rules are explicit, but drift remains in adjacent docs.
- persistence_architecture.md declares itself authoritative for persistence conflicts and says Technology_Stack must be updated to match.
  - Evidence: docs/architecture/persistence_architecture.md:12
  - Evidence: docs/architecture/persistence_architecture.md:16
- persistence doc closes vector store and event bus decisions.
  - Evidence: docs/architecture/persistence_architecture.md:17
  - Evidence: docs/architecture/persistence_architecture.md:18
- Technology_Stack still carries obsolete planned status entries for some adapters (Phase 1 listed as planned) while also having resolved-decision rows later in same file.
  - Evidence: docs/architecture/Technology_Stack.md:188
  - Evidence: docs/architecture/Technology_Stack.md:189
  - Evidence: docs/architecture/Technology_Stack.md:211
  - Evidence: docs/architecture/Technology_Stack.md:215
- Impact: intra-file inconsistency increases risk of architectural misreads.

6. Document lifecycle standards require canonical-source control, but several overlapping docs are still DRAFT with conflicting status content.
- Lifecycle policy requires canonical source declaration for overlapping topics.
  - Evidence: docs/project/standards/documentation_lifecycle_policy.md:37
- architecture.md, extensibility.md, Technology_Stack.md are marked DRAFT.
  - Evidence: docs/architecture/architecture.md:3
  - Evidence: docs/architecture/extensibility.md:3
  - Evidence: docs/architecture/Technology_Stack.md:3
- Impact: quality controls are defined but not consistently enforced for architecture status pages.

## Additional observations

- README points users to architecture overview as first source.
  - Evidence: README.md:32
- overview.md is status APPROVED and generally capability-oriented without detailed phase matrix, so phase authority is dispersed to other docs.
  - Evidence: docs/architecture/overview.md:7

## Recommended next research not completed in this session

- Verify claims against code reality for disputed areas:
  - action-layer implementation completeness (ports/adapters/services/tests).
  - operator-layer human-in-the-loop/dashboard readiness.
  - Azure Monitor adapter existence and maturity versus deferred note.
- Audit docs/architecture/layers/*.md for additional status drift against master_system_document.md.
- Build a single authoritative status matrix (phase x layer x provider) and map all docs to it.
- Check docs/reports for monthly documentation SLO summaries promised by policy.
  - Reference target: docs/project/standards/documentation_quality_slos.md:34

## Clarifying questions requiring user/maintainer input

- Which file should be the canonical source of truth for phase completion and layer readiness:
  - master_system_document.md,
  - docs/architecture/evolution/roadmap.md,
  - or a new dedicated status ledger?
- Should "full support" in roadmap be interpreted as operator/action support only, while observability metric parity can still be deferred?
- Should DRAFT architecture docs with contradictory status claims be deprecated or rewritten to align with approved docs?

## Confidence

High confidence on documentation inconsistency findings within requested scope. Medium confidence on implementation reality because this session analyzed documentation statements, not full code verification.
