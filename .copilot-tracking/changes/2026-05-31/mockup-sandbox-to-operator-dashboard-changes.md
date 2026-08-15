<!-- markdownlint-disable-file -->
# Release Changes: Mockup Sandbox to Operator Dashboard

**Related Plan**: mockup-sandbox-to-operator-dashboard-plan.instructions.md
**Implementation Date**: 2026-05-31

## Summary

Implement a production operator dashboard package and supporting contract/spec updates while preserving the mockup sandbox for design workflows.

Phase 1 completed: production package foundation, Node-backend-only boundary setup, baseline app shell/routes, and package-scoped lint/typecheck/build validation.
Phase 2 completed: API-backed incidents/phase/accuracy surfaces, timeline module, shared UI primitive porting, and package test/boundary lint command hardening.
Phase 3 completed: websocket streaming/reconcile implementation, stale/reconnect UX, unified error adapter/retry policy, and realtime validation tests.
Phase 4 completed: dashboard behavior/performance tests, CI workflow, docs updates, Node API 4xx validation contract alignment, websocket contract publication artifacts, and OpenSpec wording harmonization.
Phase 5 completed: full validation gates executed, api-server test script added, and minimal 4xx contract tests introduced and passing.

## Changes

### Added

* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/package.json - New production dashboard package manifest and scripts
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/tsconfig.json - TypeScript configuration for operator dashboard package
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/vite.config.ts - Vite config without mockup preview plugin coupling
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/index.html - Dashboard app HTML entry
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/scripts/lint-import-boundaries.mjs - Boundary guardrail script for import path enforcement
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/env.d.ts - Typed environment declarations
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/main.tsx - Application bootstrap
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/lib/api/client.ts - Node API bootstrap and guardrail checks
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/lib/api/guardrails.ts - Backend-only boundary helpers
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/app/routes.ts - Route constants for operator workflows
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/app/layout.tsx - Base layout shell
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/app/providers.tsx - Query/error provider wiring
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/app/router.tsx - Route topology for incidents, phases, and accuracy pages
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/features/incidents/incident-feed-page.tsx - Incidents feed placeholder page
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/features/incidents/incident-detail-page.tsx - Incident detail placeholder page
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/features/phases/phase-status-page.tsx - Phase status placeholder page
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/features/accuracy/accuracy-summary-page.tsx - Accuracy summary placeholder page
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/styles/index.css - Baseline styles for dashboard shell
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/test/route-rendering.test.tsx - Added explicit route and shell rendering assertions for dashboard navigation topology

### Modified

* fullstackapp/SRE-Command-Center/pnpm-lock.yaml - Workspace lockfile updated after adding operator dashboard package dependencies
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/features/incidents/incident-feed-page.tsx - Replaced placeholder with API-backed incidents feed and mapped rendering
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/features/incidents/incident-detail-page.tsx - Replaced placeholder with contract-backed incident detail rendering
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/features/incidents/timeline-panel.tsx - Added API-backed timeline view rendering behavior
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/features/phases/phase-status-panel.tsx - Added phase status panel with backend contract mapping
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/features/accuracy/accuracy-summary-panel.tsx - Added accuracy summary panel with backend contract mapping
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/features/incidents/selectors.ts - Added selector/view-model mapping logic for incident surfaces
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/lib/api/mappers/incidents.ts - Added incident response mapping and normalization logic for feed/detail/timeline views
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/lib/api/mappers/phases.ts - Added phase mapping and normalization logic
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/shared/ui/card.tsx - Ported reusable card primitive
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/shared/ui/badge.tsx - Ported reusable badge primitive
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/shared/ui/table.tsx - Ported reusable table primitive
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/shared/ui/empty-state.tsx - Added reusable empty state primitive
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/styles/index.css - Updated styles for production surface primitives
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/package.json - Added concrete package test command wiring
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/scripts/run-tests.ts - Added package test entry script and explicit route-rendering suite execution
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/scripts/lint-import-boundaries.mjs - Aligned static boundary lint behavior with package flow
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/features/incidents/realtime-status-banner.tsx - Added reconnect/stale status banner component
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/features/incidents/realtime-controller.ts - Added websocket/cache reconciliation controller
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/lib/realtime/types.ts - Added typed websocket contract models
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/lib/realtime/reducer.ts - Added sequence-aware state reducer
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/lib/realtime/incidents-socket.ts - Added websocket client and message parsing
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/lib/realtime/reconcile.ts - Added reconnect/backoff and resync orchestration
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/lib/api/error-adapter.ts - Added error shape normalization
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/lib/api/retry-policy.ts - Added normalized retry behavior mapping
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/app/error-fallback.tsx - Added unified error fallback UI
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/test/realtime.test.ts - Added realtime behavior tests
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/test/error-adapter.test.ts - Added error adapter tests
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/app/providers.tsx - Wired app providers for updated realtime/error behavior
* fullstackapp/SRE-Command-Center/.github/workflows/operator-dashboard-ci.yml - Added package-scoped CI workflow
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/README.md - Added package runtime and environment documentation
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/test/incidents-feed.test.tsx - Added incidents feed behavior tests
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/test/incident-detail.test.tsx - Added incident detail behavior tests
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/test/backend-boundary.test.ts - Added backend-only import/usage boundary tests
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/test/perf/dashboard-perf.test.ts - Added performance harness tests
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/test/e2e/dashboard-realtime.e2e.ts - Added realtime acceptance tests
* fullstackapp/SRE-Command-Center/lib/api-spec/README.md - Added websocket contract publication guidance
* fullstackapp/SRE-Command-Center/lib/api-spec/asyncapi-incidents.yaml - Added companion async websocket contract artifact
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/response-helpers.ts - Added structured client validation response helper behavior
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/incidents.ts - Added explicit validation error handling for incidents endpoints
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/middlewares/error-handler.ts - Preserved 500 behavior for server exceptions with validation path separation
* fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml - Added validation error response docs and websocket publication metadata
* openspec/changes/phase-2-7-operator-dashboard/proposal.md - Harmonized stack wording
* openspec/changes/phase-2-7-operator-dashboard/design.md - Harmonized stack wording
* openspec/changes/phase-2-7-operator-dashboard/tasks.md - Harmonized framework/testing wording
* openspec/changes/phase-2-7-operator-dashboard/specs/dashboard-mvp/spec.md - Harmonized terminology wording
* fullstackapp/SRE-Command-Center/README.md - Updated workflow docs for sandbox and operator-dashboard parallel usage
* fullstackapp/SRE-Command-Center/artifacts/api-server/package.json - Added executable test script with test-time DATABASE_URL default
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/__tests__/incidents.validation.test.ts - Added minimal validation contract tests for structured 400 responses

### Removed

* None yet.

## Additional or Deviating Changes

* Added plan/detail Step 2.5 for package test runner and static import-boundary lint rule
	* Reason: Added from Phase 1 implementation feedback to improve enforcement and CI reliability

* Initial validation attempts were run from repository root before rerunning correctly from fullstackapp/SRE-Command-Center
	* Reason: pnpm workspace filter commands were package-root dependent for this new package setup

* Type issues were uncovered while moving incident detail rendering to mapped API contracts and were fixed during Phase 2
	* Reason: transport-level fields were used directly where mapped selectors were required for stable UI typing

* QueryKey import type mismatch in realtime controller was fixed during Phase 3 validation
	* Reason: QueryKey type source needed to align with @tanstack/react-query instead of API client package exports

* Added plan/detail Step 4.7 for websocket reconnect lifecycle acceptance coverage and env documentation
	* Reason: Added from Phase 3 implementation feedback to tighten acceptance behavior verification

* Added plan/detail Step 5.4 for api-server test script and minimal validation contract tests
	* Reason: Phase 4 validation identified missing api-server test script for required validation command

* pnpm --filter @workspace/api-server test could not run in Phase 4 because the script was not defined
	* Reason: Backend package had no test script entry at implementation time

* api-server tests initially failed due required DATABASE_URL at module load and were fixed in-package
	* Reason: test execution needed explicit environment defaults even for validation-only route tests

* Review remediation added explicit route rendering assertions and persisted validation evidence in tracking artifacts
	* Reason: Needed to close review major findings for Step 2.4 (route rendering tests) and Step 5.1 (command evidence persistence)

## Validation Evidence (Phase 5.1 Remediation)

* Command: pnpm --filter @workspace/operator-dashboard test
	* Result: Pass (includes PASS route-rendering)
* Command: pnpm --filter @workspace/operator-dashboard lint
	* Result: Pass (boundary lint + tsc noEmit)
* Command: pnpm --filter @workspace/operator-dashboard typecheck
	* Result: Pass
* Command: pnpm --filter @workspace/operator-dashboard build
	* Result: Pass (vite build succeeded)
* Command: pnpm --filter @workspace/api-server test
	* Result: Pass (2/2 incidents validation tests)

## Release Summary

Implementation completed across all planned phases.

Total files affected (tracked in this changes log):
* Added: operator-dashboard package foundation files, realtime/error modules, dashboard test suites, CI workflow, API-spec async contract docs, and api-server validation test file
* Modified: operator-dashboard feature implementations, styles/providers/test runner wiring, api-server route/error handling and package scripts, OpenAPI contract artifact, phase-2-7 OpenSpec docs, and SRE Command Center README
* Removed: None

Key delivery outcomes:
* New production frontend package at fullstackapp/SRE-Command-Center/artifacts/operator-dashboard with Node-backend-only integration boundary
* API-backed incidents, timeline, phase, and accuracy dashboard surfaces with selector/mapping architecture
* Realtime websocket sequencing, reconnect/reconcile handling, stale/reconnected UI states, and unified error adapter/retry policy
* Structured backend validation 4xx behavior for incidents routes with accompanying tests
* Published websocket contract artifacts (OpenAPI metadata + AsyncAPI companion)
* Harmonized OpenSpec phase-2-7 wording and terminology to match repository architecture
* End-to-end validation passed for operator-dashboard lint/typecheck/test/build and api-server test

Dependency and infrastructure notes:
* pnpm workspace lockfile changed due package/dependency updates in nested SRE Command Center workspace
* Added package-scoped CI workflow: fullstackapp/SRE-Command-Center/.github/workflows/operator-dashboard-ci.yml

Deployment/runtime notes:
* Operator dashboard runtime expects Node API at /api and websocket path /api/ws/incidents
* api-server tests use safe default DATABASE_URL for local/CI test bootstrap
