<!-- markdownlint-disable-file -->
# Implementation Details: Mockup Sandbox to Operator Dashboard

## Context Reference

Sources: .copilot-tracking/research/2026-05-31/mockup-sandbox-to-operator-dashboard-research.md, .copilot-tracking/research/subagents/2026-05-31/mockup-sandbox-analysis-research.md, .copilot-tracking/research/subagents/2026-05-31/backend-api-contracts-analysis-research.md, .copilot-tracking/research/subagents/2026-05-31/openspec-phase-2-7-analysis-research.md, .copilot-tracking/research/subagents/2026-05-31/migration-alternatives-analysis-research.md

## Implementation Phase 1: Package Foundation and Boundary Setup (Milestone M1)

<!-- parallelizable: false -->

### Step 1.1: Create new production package scaffold under artifacts/operator-dashboard

Create a new workspace package for production runtime without modifying mockup-sandbox preview behavior. Include package scripts for dev, build, lint, typecheck, and tests. Ensure workspace registration and dependency wiring are explicit.

Files:
* fullstackapp/SRE-Command-Center/pnpm-workspace.yaml - Add artifacts/operator-dashboard package path if missing
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/package.json - New package manifest
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/tsconfig.json - TypeScript config aligned with workspace
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/vite.config.ts - Runtime build config without preview plugin
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/main.tsx - Entry point bootstrap

Discrepancy references:
* Addresses DR-02 from planning log (spec technology wording drift vs existing workspace stack)

Success criteria:
* New package builds and starts independently
* No changes required to mockup-sandbox routes or preview file discovery

Context references:
* .copilot-tracking/research/2026-05-31/mockup-sandbox-to-operator-dashboard-research.md (Lines 226-232) - Foundation step rationale
* .copilot-tracking/research/subagents/2026-05-31/migration-alternatives-analysis-research.md (Lines 136-177) - Selected architecture path

Dependencies:
* pnpm workspace scripts operational in fullstackapp/SRE-Command-Center

### Step 1.2: Add runtime boundary configuration for Node.js backend-only API consumption

Initialize API client bootstrap and environment wiring so all HTTP and realtime traffic targets the Node.js app only. Explicitly prohibit direct imports from src/sre_agent domain runtime modules.

Files:
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/lib/api/client.ts - Configure generated fetch/client base URL and token/cookie handling
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/lib/api/guardrails.ts - Runtime guardrail helpers and import-boundary assertions
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/env.d.ts - Typed env declarations for API/WS endpoints

Success criteria:
* All data-access modules resolve to Node API base path /api
* Lint/import rules fail if non-contract backend internals are imported

Context references:
* .copilot-tracking/research/subagents/2026-05-31/backend-api-contracts-analysis-research.md (Lines 29-108) - API and app mount path
* .copilot-tracking/research/2026-05-31/mockup-sandbox-to-operator-dashboard-research.md (Lines 8-10) - Hard constraint

Dependencies:
* Step 1.1 completion

### Step 1.3: Add baseline app shell and route skeleton for operator workflows

Create production route topology for incidents list/detail, phase status, and accuracy summary. Add root providers for query cache and global error boundary.

Files:
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/app/router.tsx - App routes
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/app/providers.tsx - Query/error providers
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/app/layout.tsx - Shared shell layout
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/app/routes.ts - Route constants

Success criteria:
* App launches and navigates between placeholder pages for all MVP surfaces
* Query client and global error boundary are initialized once

Context references:
* openspec/changes/phase-2-7-operator-dashboard/tasks.md (Lines 10-40) - Feature sequence
* .copilot-tracking/research/2026-05-31/mockup-sandbox-to-operator-dashboard-research.md (Lines 190-205) - Proposed production package tree

Dependencies:
* Step 1.2 completion

### Step 1.4: Validate phase changes

Run lint, typecheck, and build for artifacts/operator-dashboard only.

Validation commands:
* pnpm --filter @workspace/operator-dashboard lint - lint scope: new package
* pnpm --filter @workspace/operator-dashboard typecheck - type scope: new package
* pnpm --filter @workspace/operator-dashboard build - build scope: new package

## Implementation Phase 2: Core Data Surfaces and UI Porting (Milestone M2)

<!-- parallelizable: false -->

### Step 2.1: Implement incidents list and detail views using generated API client hooks

Build feed and detail pages using generated hooks from lib/api-client-react. Add DTO-to-view-model mappers to isolate rendering from transport contracts.

Files:
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/features/incidents/incident-feed-page.tsx - Incident list page
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/features/incidents/incident-detail-page.tsx - Incident detail page
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/lib/api/mappers/incidents.ts - Contract-to-view mapping
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/features/incidents/selectors.ts - Query selectors and memoization

Discrepancy references:
* Addresses DR-01 from planning log (API validation error behavior mismatch handling at frontend adapter layer)

Success criteria:
* Incident feed/detail renders data from Node endpoints only
* No hardcoded mock incident payloads remain in production package feature files

Context references:
* fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml (Lines 31-103) - Incidents contracts
* .copilot-tracking/research/subagents/2026-05-31/mockup-sandbox-analysis-research.md (Lines 53-104) - Static mock data replacement need

Dependencies:
* Phase 1 completion

### Step 2.2: Implement timeline, phase status, and accuracy summary panels from Node contracts

Implement timeline and status modules wired to incident timeline, phase status, and accuracy summary endpoints. Ensure the UI labels use mapped phase taxonomy from backend payloads.

Files:
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/features/incidents/timeline-panel.tsx - Incident timeline module
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/features/phases/phase-status-panel.tsx - Graduation phase status
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/features/accuracy/accuracy-summary-panel.tsx - Accuracy metrics
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/lib/api/mappers/phases.ts - Phase normalization logic

Success criteria:
* Timeline, phase status, and accuracy panels render from live contracts
* Phase labels are consistent with backend API response values

Context references:
* fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml (Lines 85-132) - Timeline, phase, accuracy contracts
* .copilot-tracking/research/subagents/2026-05-31/openspec-phase-2-7-analysis-research.md (Lines 126-180) - Requirement mapping and taxonomy drift

Dependencies:
* Step 2.1 completion

### Step 2.3: Port reusable visual primitives from mockup-sandbox without importing preview runtime logic

Copy or extract presentational primitives and style tokens needed by production surfaces. Do not import mockup preview/gallery runtime files from App.tsx or mockupPreviewPlugin.ts.

Files:
* fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/src/components/ui - Source primitives inventory
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/shared/ui - Ported/curated primitives
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/styles/index.css - Tokenized style entry

Discrepancy references:
* Deviates from reuse-all recommendation by intentionally excluding preview runtime internals (DD-01 in planning log)

Success criteria:
* Production package uses reusable primitives without runtime dependency on mockup preview shell
* Visual parity exists for core dashboard cards, tables, status chips, and incident metadata display

Context references:
* .copilot-tracking/research/subagents/2026-05-31/mockup-sandbox-analysis-research.md (Lines 106-157) - Reuse/refactor/replace matrix
* fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/src/App.tsx (Lines 99-144) - Excluded preview runtime

Dependencies:
* Step 2.1 completion

### Step 2.4: Validate phase changes

Run UI rendering tests and route-level integration tests for incidents/timeline/phase/accuracy features.

Validation commands:
* pnpm --filter @workspace/operator-dashboard test -- incidents - test scope: incidents/timeline features
* pnpm --filter @workspace/operator-dashboard test -- phase accuracy - test scope: status and accuracy features

### Step 2.5: Add package test runner and static import-boundary lint rule

Establish a concrete package test command and static import-boundary enforcement to complement runtime guardrails introduced in Phase 1.

Files:
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/package.json - Add stable test script and related command wiring
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/eslint.config.* - Add static rules to block imports from src/sre_agent and non-contract backend internals
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/scripts/lint-import-boundaries.mjs - Keep as secondary guardrail and align messaging with static lint behavior

Success criteria:
* Package test command executes deterministically in local and CI flows
* Static lint checks fail on disallowed backend/internal import paths

Context references:
* Phase 1 subagent suggested additional steps - test runner and static analysis boundary enforcement

Dependencies:
* Step 2.4 completion

## Implementation Phase 3: Realtime Reconciliation and Resilience UX (Milestone M3)

<!-- parallelizable: false -->

### Step 3.1: Implement websocket stream client for /api/ws/incidents with sequence handling

Add websocket client module and message reducer supporting initial_state and incident_update contracts. Store last sequence and resync token to detect stream continuity.

Files:
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/lib/realtime/incidents-socket.ts - WS connection and event parsing
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/lib/realtime/reducer.ts - Sequence-aware state reducer
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/lib/realtime/types.ts - WS message types

Success criteria:
* Initial snapshot and updates merge into feed state deterministically
* Sequence and resync token are tracked per stream session

Context references:
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/ws/incidents.ts (Lines 14-337) - Runtime WS behavior
* fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml (Lines 460-517) - WS message schemas

Dependencies:
* Phase 2 completion

### Step 3.2: Add resync/reconnect behavior and stale-data recovery path with user-visible status

Implement reconnect policy with capped backoff, stale indicator, and automatic resync fallback to incidents list endpoint when sequence gaps or token mismatch are detected.

Files:
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/lib/realtime/reconcile.ts - Gap detection and recovery orchestration
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/features/incidents/realtime-status-banner.tsx - Reconnect and stale-state UI
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/features/incidents/realtime-controller.ts - Controller glue between WS and query cache

Discrepancy references:
* Addresses DR-03 from planning log (OpenAPI path-level WS contract omission handled through implementation-contract fallback)

Success criteria:
* On gap/mismatch the app refetches incidents and restores coherent state
* UI shows reconnect progress and post-recovery status

Context references:
* openspec/changes/phase-2-7-operator-dashboard/specs/dashboard-mvp/spec.md (Lines 37-42) - Reconnect/reconcile acceptance
* .copilot-tracking/research/subagents/2026-05-31/backend-api-contracts-analysis-research.md (Lines 154-183) - WS documentation gap

Dependencies:
* Step 3.1 completion

### Step 3.3: Normalize mixed backend error payloads into a single frontend error adapter

Create a shared adapter that maps {code,message} and {error} responses into one typed frontend error model for retry strategy and error boundary display.

Files:
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/lib/api/error-adapter.ts - Error normalization logic
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/lib/api/retry-policy.ts - Retry policy by normalized error type
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/app/error-fallback.tsx - Unified error fallback UI

Success criteria:
* Frontend error handling is deterministic across all endpoint failures
* Validation-like failures do not trigger aggressive retry loops

Context references:
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/response-helpers.ts (Lines 24-29) - Not-found error shape
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/middlewares/error-handler.ts (Lines 11-15) - Generic 500 error shape

Dependencies:
* Step 3.2 completion

### Step 3.4: Validate phase changes

Run realtime integration tests and resilience-path assertions.

Validation commands:
* pnpm --filter @workspace/operator-dashboard test -- realtime - test scope: WS/reconcile
* pnpm --filter @workspace/operator-dashboard test -- error-adapter - test scope: error normalization

## Implementation Phase 4: Testing, Acceptance, and Documentation Alignment (Milestone M4)

<!-- parallelizable: false -->

### Step 4.1: Implement test suite coverage for phase-2-7 behaviors and frontend constraints

Add unit/integration tests for feed freshness, detail drill-down, timeline correctness, and backend-only data source boundaries.

Files:
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/test/incidents-feed.test.tsx - Feed behavior
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/test/incident-detail.test.tsx - Detail/timeline behavior
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/test/backend-boundary.test.ts - Import boundary and endpoint targeting assertions

Success criteria:
* Test suite verifies no direct SRE-Agent runtime coupling in frontend package
* Incidents and detail workflows are validated end-to-end at component integration level

Context references:
* openspec/changes/phase-2-7-operator-dashboard/tasks.md (Lines 42-46) - Testing expectations
* .copilot-tracking/research/2026-05-31/mockup-sandbox-to-operator-dashboard-research.md (Lines 218-225) - Constraint and acceptance linkage

Dependencies:
* Phase 3 completion

### Step 4.2: Add acceptance/performance verification harness for feed and rendering thresholds

Implement lightweight measurement harness for FCP/feed/50-incident responsiveness assertions and include these checks in CI workflow for the new package.

Files:
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/test/perf/dashboard-perf.test.ts - Performance checks
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/test/e2e/dashboard-realtime.e2e.ts - Realtime acceptance scenario
* fullstackapp/SRE-Command-Center/.github/workflows/operator-dashboard-ci.yml - Package-scoped CI validation pipeline

Discrepancy references:
* Addresses DR-05 from planning log (performance acceptance instrumentation missing in OpenSpec task details)

Success criteria:
* Measurable pass/fail criteria exist for phase-2-7 responsiveness thresholds
* Realtime acceptance flow includes reconnect and reconciliation validation

Context references:
* openspec/changes/phase-2-7-operator-dashboard/specs/dashboard-mvp/spec.md (Lines 13-20) - Performance targets
* openspec/changes/phase-2-7-operator-dashboard/specs/dashboard-mvp/spec.md (Lines 22-42) - Realtime behavior targets

Dependencies:
* Step 4.1 completion

### Step 4.3: Update SRE-Command-Center docs to run sandbox and operator-dashboard in parallel

Document parallel developer workflows and commands for both design sandbox and production dashboard package.

Files:
* fullstackapp/SRE-Command-Center/README.md - Run instructions and package role clarification
* fullstackapp/SRE-Command-Center/docs - Optional package-specific runbook references if introduced

Success criteria:
* Developer instructions clearly separate sandbox versus production dashboard usage
* Startup and test commands are reproducible for both packages

Context references:
* fullstackapp/SRE-Command-Center/README.md (Lines 76-86) - Current artifact roles
* .copilot-tracking/research/subagents/2026-05-31/migration-alternatives-analysis-research.md (Lines 188-212) - Selected path rationale

Dependencies:
* Step 4.2 completion

### Step 4.4: Align Node API validation errors to structured 4xx contract behavior

Implement explicit validation error mapping so invalid path/query payloads return structured 4xx responses matching shared error schema instead of generic 500 responses.

Files:
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/incidents.ts - Wrap zod parse failures with explicit client-error response mapping
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/response-helpers.ts - Add reusable validation error responder
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/middlewares/error-handler.ts - Preserve generic 500 for true server exceptions only
* fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml - Document 400/422 style validation error responses for affected endpoints

Discrepancy references:
* Addresses DR-01 from planning log

Success criteria:
* Invalid id/query inputs return structured client errors and not generic internal errors
* API spec and runtime behavior are aligned for validation failure responses

Context references:
* .copilot-tracking/research/subagents/2026-05-31/backend-api-contracts-analysis-research.md (Lines 112-133) - Validation mismatch finding

Dependencies:
* Step 4.1 completion

### Step 4.5: Publish websocket endpoint contract alongside existing REST OpenAPI artifacts

Add explicit websocket contract publication strategy so frontend integration and validation do not rely solely on runtime source inspection.

Files:
* fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml - Add extension/reference metadata for websocket endpoint and handshake notes
* fullstackapp/SRE-Command-Center/lib/api-spec/asyncapi-incidents.yaml - Optional companion async contract if OpenAPI extension is insufficient
* fullstackapp/SRE-Command-Center/lib/api-spec/README.md - Contract publication guidance for frontend consumption

Discrepancy references:
* Addresses DR-03 from planning log

Success criteria:
* Websocket endpoint path and message semantics are published in a stable contract artifact
* Frontend integration can reference documentation/contracts without reading server implementation files

Context references:
* .copilot-tracking/research/subagents/2026-05-31/backend-api-contracts-analysis-research.md (Lines 154-171) - WS contract publication gap

Dependencies:
* Step 4.4 completion

### Step 4.6: Harmonize OpenSpec phase-2-7 stack and terminology wording to repository implementation reality

Update phase-2-7 proposal/design/tasks wording for stack and testing references to align with current Node.js/Express plus Vite frontend implementation and normalize phase terminology usage.

Files:
* openspec/changes/phase-2-7-operator-dashboard/proposal.md - Stack and component references
* openspec/changes/phase-2-7-operator-dashboard/design.md - Implementation stack decisions
* openspec/changes/phase-2-7-operator-dashboard/tasks.md - Testing framework wording and task language
* openspec/changes/phase-2-7-operator-dashboard/specs/dashboard-mvp/spec.md - Phase terminology consistency updates where needed

Discrepancy references:
* Addresses DR-02 and DR-04 from planning log

Success criteria:
* OpenSpec wording reflects actual implementation stack and test framework
* Phase terminology is consistent across dashboard phase artifacts and UI mapping assumptions

Context references:
* .copilot-tracking/research/subagents/2026-05-31/openspec-phase-2-7-analysis-research.md (Lines 181-236) - Contradictions and terminology drift

Dependencies:
* Step 4.5 completion

### Step 4.7: Add websocket reconnect lifecycle acceptance tests and environment documentation

Add acceptance-level coverage for websocket disconnect/reconnect lifecycle timing and stale/reconnected UI indicators. Document realtime endpoint environment variables for local and proxied runs.

Files:
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/test/e2e/dashboard-realtime.e2e.ts - Include lifecycle disconnect/reconnect assertions
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/test/realtime.test.ts - Extend fake-timer reconnect timing and banner transition assertions
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/README.md - Document VITE_NODE_WS_ORIGIN and realtime behavior notes

Success criteria:
* Reconnect timing and stale/reconnected status behavior are covered by acceptance and integration tests
* Realtime environment variables are documented for developers and CI

Context references:
* Phase 3 implementation suggested additional steps - reconnect lifecycle acceptance tests and runtime env documentation

Dependencies:
* Step 4.2 completion

## Implementation Phase 5: Validation

<!-- parallelizable: false -->

### Step 5.1: Run full project validation

Execute all validation commands for affected packages and integration surfaces:
* pnpm --filter @workspace/operator-dashboard lint
* pnpm --filter @workspace/operator-dashboard typecheck
* pnpm --filter @workspace/operator-dashboard test
* pnpm --filter @workspace/operator-dashboard build
* pnpm --filter @workspace/api-server test (if test script exists by implementation time)

### Step 5.2: Fix minor validation issues

Iterate on lint/test/build failures when fixes are isolated and low risk. Keep corrections scoped to dashboard package and directly related shared contracts.

### Step 5.3: Report blocking issues

When failures require significant API contract changes or OpenSpec re-baselining:
* Document exact blockers and impacted files.
* Capture whether the blocker is contract, tooling, or acceptance ambiguity.
* Recommend follow-on research/planning for non-trivial refactors.

### Step 5.4: Add api-server test script and minimal 4xx validation contract test coverage

Introduce a runnable api-server test script and minimal route-level tests that assert structured 4xx validation behavior introduced in Phase 4.

Files:
* fullstackapp/SRE-Command-Center/artifacts/api-server/package.json - Add test script
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/__tests__/incidents.validation.test.ts - Add validation error contract tests
* fullstackapp/SRE-Command-Center/artifacts/api-server/vitest.config.* - Add or update test runner config if needed

Success criteria:
* pnpm --filter @workspace/api-server test runs successfully
* Validation failures for incidents route parse errors assert structured 4xx response contract

Context references:
* Phase 4 validation issue - missing api-server test script

Dependencies:
* Step 5.1 initiation

## Dependencies

* Node.js and pnpm workspace tooling
* API contract generation stack in fullstackapp/SRE-Command-Center/lib

## Success Criteria

* Milestones M1 through M4 each map to executable, testable implementation units
* Final validation phase defines full quality gates before completion
