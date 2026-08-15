---
applyTo: '.copilot-tracking/changes/2026-05-31/mockup-sandbox-to-operator-dashboard-changes.md'
---
<!-- markdownlint-disable-file -->
# Implementation Plan: Mockup Sandbox to Operator Dashboard

## Overview

Build a production-grade operator dashboard by introducing a new frontend package under fullstackapp/SRE-Command-Center/artifacts/operator-dashboard that consumes only Node.js backend endpoints and keeps mockup-sandbox as a design-only surface.

## Objectives

### User Requirements

* Deliver a highly accurate, precise, and well-structured implementation plan with milestones and task breakdown for converting mockup frontend to production dashboard — Source: User request (current conversation)
* Scope planning to fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox, openspec/changes/phase-2-7-operator-dashboard, and fullstackapp/SRE-Command-Center/lib — Source: User request (current conversation)
* Enforce the frontend constraint to consume only Node.js backend endpoints — Source: User request (current conversation)
* Produce planning deliverable as plan.md-equivalent artifact under .copilot-tracking/plans — Source: User request (current conversation)

### Derived Objectives

* Select one migration path with explicit alternatives to reduce implementation ambiguity — Derived from: .copilot-tracking/research/2026-05-31/mockup-sandbox-to-operator-dashboard-research.md
* Preserve existing design velocity by retaining mockup-sandbox and isolating production runtime concerns in a new package — Derived from: .copilot-tracking/research/subagents/2026-05-31/migration-alternatives-analysis-research.md
* Align phase ordering to phase-2-7 MVP acceptance requirements (realtime, reconnect/reconcile, responsive and performance behavior) — Derived from: openspec/changes/phase-2-7-operator-dashboard/specs/dashboard-mvp/spec.md
* Include implementation-time discrepancy handling and follow-on items for unresolved contract gaps — Derived from: backend/API discrepancy findings in research

## Context Summary

### Project Files

* .copilot-tracking/research/2026-05-31/mockup-sandbox-to-operator-dashboard-research.md - Primary evidence and selected architecture path
* .copilot-tracking/research/subagents/2026-05-31/mockup-sandbox-analysis-research.md - Mockup asset reuse/refactor/replace matrix
* .copilot-tracking/research/subagents/2026-05-31/backend-api-contracts-analysis-research.md - Node API contracts and mismatch findings
* .copilot-tracking/research/subagents/2026-05-31/openspec-phase-2-7-analysis-research.md - OpenSpec requirement mapping and contradictions
* fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml - Backend API contract source for dashboard integration
* openspec/changes/phase-2-7-operator-dashboard/tasks.md - Required dashboard MVP sequencing baseline

### References

* openspec/changes/phase-2-7-operator-dashboard/specs/dashboard-mvp/spec.md - SHALL acceptance behavior for MVP
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/ws/incidents.ts - Runtime websocket behavior and sequence/reconcile semantics
* fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/src/App.tsx - Current preview-oriented frontend shell to avoid coupling in production package

### Standards References

* /home/faizan-hussain/Documents/PersonalProjects/SREAgent/CLAUDE.md — architecture boundaries and workflow expectations
* /home/faizan-hussain/Documents/PersonalProjects/SREAgent/AGENTS.md — multi-agent constraints and operational boundaries

## Implementation Checklist

### [x] Implementation Phase 1: Package Foundation and Boundary Setup (Milestone M1)

<!-- parallelizable: false -->

* [x] Step 1.1: Create new production package scaffold under artifacts/operator-dashboard
  * Details: .copilot-tracking/details/2026-05-31/mockup-sandbox-to-operator-dashboard-details.md (Lines 12-35)
* [x] Step 1.2: Add runtime boundary configuration for Node.js backend-only API consumption
  * Details: .copilot-tracking/details/2026-05-31/mockup-sandbox-to-operator-dashboard-details.md (Lines 37-55)
* [x] Step 1.3: Add baseline app shell and route skeleton for operator workflows
  * Details: .copilot-tracking/details/2026-05-31/mockup-sandbox-to-operator-dashboard-details.md (Lines 57-76)
* [x] Step 1.4: Validate phase changes
  * Run package-level lint, typecheck, and build commands for new package only
  * Skip cross-workspace full checks at this stage

### [x] Implementation Phase 2: Core Data Surfaces and UI Porting (Milestone M2)

<!-- parallelizable: false -->

* [x] Step 2.1: Implement incidents list and detail views using generated API client hooks
  * Details: .copilot-tracking/details/2026-05-31/mockup-sandbox-to-operator-dashboard-details.md (Lines 91-113)
* [x] Step 2.2: Implement timeline, phase status, and accuracy summary panels from Node contracts
  * Details: .copilot-tracking/details/2026-05-31/mockup-sandbox-to-operator-dashboard-details.md (Lines 115-134)
* [x] Step 2.3: Port reusable visual primitives from mockup-sandbox without importing preview runtime logic
  * Details: .copilot-tracking/details/2026-05-31/mockup-sandbox-to-operator-dashboard-details.md (Lines 136-157)
* [x] Step 2.4: Validate phase changes
  * Run component-level tests and route rendering tests in new package
  * Skip realtime integration assertions until Phase 3 completes
* [x] Step 2.5: Add package test runner and static import-boundary lint rule
  * Details: .copilot-tracking/details/2026-05-31/mockup-sandbox-to-operator-dashboard-details.md (Step 2.5)

### [x] Implementation Phase 3: Realtime Reconciliation and Resilience UX (Milestone M3)

<!-- parallelizable: false -->

* [x] Step 3.1: Implement websocket stream client for /api/ws/incidents with sequence handling
  * Details: .copilot-tracking/details/2026-05-31/mockup-sandbox-to-operator-dashboard-details.md (Lines 171-189)
* [x] Step 3.2: Add resync/reconnect behavior and stale-data recovery path with user-visible status
  * Details: .copilot-tracking/details/2026-05-31/mockup-sandbox-to-operator-dashboard-details.md (Lines 191-212)
* [x] Step 3.3: Normalize mixed backend error payloads into a single frontend error adapter
  * Details: .copilot-tracking/details/2026-05-31/mockup-sandbox-to-operator-dashboard-details.md (Lines 214-232)
* [x] Step 3.4: Validate phase changes
  * Run websocket/reconcile integration tests and failure-path tests

### [x] Implementation Phase 4: Testing, Acceptance, and Documentation Alignment (Milestone M4)

<!-- parallelizable: false -->

* [x] Step 4.1: Implement test suite coverage for phase-2-7 behaviors and frontend constraints
  * Details: .copilot-tracking/details/2026-05-31/mockup-sandbox-to-operator-dashboard-details.md (Lines 246-264)
* [x] Step 4.2: Add acceptance/performance verification harness for feed and rendering thresholds
  * Details: .copilot-tracking/details/2026-05-31/mockup-sandbox-to-operator-dashboard-details.md (Lines 266-287)
* [x] Step 4.3: Update SRE-Command-Center docs to run sandbox and operator-dashboard in parallel
  * Details: .copilot-tracking/details/2026-05-31/mockup-sandbox-to-operator-dashboard-details.md (Lines 289-306)
* [x] Step 4.4: Align Node API validation errors to structured 4xx contract behavior
  * Details: .copilot-tracking/details/2026-05-31/mockup-sandbox-to-operator-dashboard-details.md (Lines 308-327)
* [x] Step 4.5: Publish websocket endpoint contract alongside existing REST OpenAPI artifacts
  * Details: .copilot-tracking/details/2026-05-31/mockup-sandbox-to-operator-dashboard-details.md (Lines 329-349)
* [x] Step 4.6: Harmonize OpenSpec phase-2-7 stack and terminology wording to repository implementation reality
  * Details: .copilot-tracking/details/2026-05-31/mockup-sandbox-to-operator-dashboard-details.md (Lines 351-370)
* [x] Step 4.7: Add websocket reconnect lifecycle acceptance tests and environment documentation
  * Details: .copilot-tracking/details/2026-05-31/mockup-sandbox-to-operator-dashboard-details.md (Step 4.7)

### [x] Implementation Phase 5: Validation

<!-- parallelizable: false -->

* [x] Step 5.1: Run full project validation
  * Execute all lint commands for affected packages
  * Execute build scripts for fullstackapp/SRE-Command-Center affected workspace packages
  * Run frontend unit/integration and e2e suites covering dashboard scenarios
* [x] Step 5.2: Fix minor validation issues
  * Iterate on lint errors, warnings, and small test failures within scoped package changes
* [x] Step 5.3: Report blocking issues
  * Document unresolved contract or acceptance mismatches requiring additional research
  * Provide next-step planning recommendations when issues exceed minor corrections
* [x] Step 5.4: Add api-server test script and minimal 4xx validation contract test coverage
  * Details: .copilot-tracking/details/2026-05-31/mockup-sandbox-to-operator-dashboard-details.md (Step 5.4)

## Planning Log

See .copilot-tracking/plans/logs/2026-05-31/mockup-sandbox-to-operator-dashboard-log.md for discrepancy tracking, implementation paths considered, and suggested follow-on work.

## Dependencies

* pnpm workspace tooling in fullstackapp/SRE-Command-Center
* Existing generated contracts in fullstackapp/SRE-Command-Center/lib/api-client-react
* Node.js API server runtime endpoints in fullstackapp/SRE-Command-Center/artifacts/api-server
* Phase-2-7 OpenSpec acceptance definitions

## Success Criteria

* Production dashboard implementation path is fully decomposed into milestones and executable steps — Traces to: User requirement for task breakdown and milestones
* Plan enforces strict backend-only frontend integration to Node.js API contracts — Traces to: User backend constraint
* Plan sequencing includes realtime recovery, resilience UX, and validation gates for phase-2-7 behavior — Traces to: openspec/changes/phase-2-7-operator-dashboard/specs/dashboard-mvp/spec.md
* Contract and specification mismatches from research are explicitly remediated in-scope via milestone tasks — Traces to: research findings on API and spec mismatches
