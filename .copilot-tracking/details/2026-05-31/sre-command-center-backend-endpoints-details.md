---
description: "Implementation details for SRE Command Center operator dashboard backend endpoints"
---
<!-- markdownlint-disable-file -->
# Implementation Details: SRE Command Center Backend Operator Dashboard Endpoints

## Context Reference

Sources:
* .copilot-tracking/research/2026-05-31/sre-command-center-backend-endpoints-research.md
* .copilot-tracking/research/subagents/2026-05-31/deep-schema-and-ws-research.md
* .copilot-tracking/research/subagents/2026-05-31/dashboard-backend-surface-research.md
* openspec/changes/phase-2-7-operator-dashboard/tasks.md
* openspec/changes/phase-2-7-operator-dashboard/specs/dashboard-mvp/spec.md

## Implementation Phase 1: Contract and schema foundation

<!-- parallelizable: false -->

### Step 1.1: Extend the Drizzle read schema

Add read-only table definitions that mirror the Postgres tables already owned by the Python SRE Agent. The schema should cover the dashboard read model first and stay aligned to the current migrations rather than inventing a new shape.

Files:
* fullstackapp/SRE-Command-Center/lib/db/src/schema/index.ts - define incidents, incident_events, diagnosis_results, remediation_actions, and coordination_audit tables.

Discrepancy references:
* DR-01 - The current schema file is empty, so the dashboard backend cannot query typed tables yet.
* DD-01 - The plan uses the Express backend as the read surface rather than consuming the Python API directly.

Success criteria:
* incidents.version is present in the Drizzle schema.
* incident_events keeps the canonical columns from the persistence migrations.
* coordination_audit is available for a later audit timeline or operator history view.

Context references:
* src/sre_agent/adapters/persistence/migrations/001_incident_lifecycle.sql (Lines 1-92) - canonical incident/event tables.
* src/sre_agent/adapters/persistence/migrations/003_coordination_audit.sql (Lines 1-34) - audit columns and indexes.
* src/sre_agent/adapters/persistence/migrations/006_schema_improvements.sql (Lines 1-80) - incidents.version and reasoning trace tables.
* src/sre_agent/adapters/persistence/migrations/007_partition_readiness_and_status_fidelity.sql (Lines 1-120) - partition/cutover and remediation status fidelity.
* src/sre_agent/adapters/persistence/migrations/010_incident_events_partition_cutover.sql (Lines 1-150) - canonical incident_events cutover behavior.

Dependencies:
* None beyond the shared db package and the verified migration shapes.

### Step 1.2: Expand the OpenAPI contract for the dashboard surface

Add the dashboard endpoint shapes to the OpenAPI document and keep the Api title unchanged so the codegen import paths remain stable.

Files:
* fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml - add incident, phase, accuracy, and websocket-related schemas and paths.

Discrepancy references:
* DR-02 - The generated contract currently only describes GET /healthz.
* DD-02 - The plan adds the dashboard endpoints to the command-center API rather than to the Python API.

Success criteria:
* GET /api/v1/incidents is represented with pagination fields and incident summary data.
* GET /api/v1/incidents/:id and /timeline have explicit response schemas.
* GET /api/v1/phases/status and GET /api/v1/accuracy/summary have dashboard-ready response bodies.
* The OpenAPI title remains Api.

Context references:
* lib/api-spec/openapi.yaml (Lines 1-24) - current one-route contract.
* .copilot-tracking/research/2026-05-31/sre-command-center-backend-endpoints-research.md (Lines 1-40) - scope correction and evidence summary.
* .copilot-tracking/research/2026-05-31/sre-command-center-backend-endpoints-research.md (Lines 120-220) - dashboard data requirements and endpoint scenarios.

Dependencies:
* Step 1.1 completion.

### Step 1.3: Regenerate generated API artifacts

Regenerate the Zod response schemas and React Query hooks from the updated OpenAPI file. This keeps the dashboard backend contract-first and avoids hand-written schema drift.

Files:
* fullstackapp/SRE-Command-Center/lib/api-zod/src/generated/* - regenerated Zod response schemas.
* fullstackapp/SRE-Command-Center/lib/api-client-react/src/generated/* - regenerated React Query hooks.

Discrepancy references:
* DR-03 - The generated artifacts currently expose only the health check helpers.

Success criteria:
* The generated API package exports the new dashboard response schemas.
* The React client exports query helpers for the new endpoints.
* No manual edits are needed in generated files after codegen.

Context references:
* fullstackapp/SRE-Command-Center/lib/api-spec/orval.config.ts (Lines 1-60) - title transformer and output wiring.
* fullstackapp/SRE-Command-Center/lib/api-zod/src/generated/api.ts (Lines 1-40) - current health-only schema.
* fullstackapp/SRE-Command-Center/lib/api-client-react/src/generated/api.ts (Lines 1-60) - current health-only query helper.

Dependencies:
* Step 1.2 completion.

## Implementation Phase 2: Dashboard REST endpoints

<!-- parallelizable: true -->

### Step 2.1: Implement incident query routes

Create route modules for the incident list, incident detail, and timeline views. These routes should query the shared Postgres data directly and return schemas that the dashboard components can consume without extra transformation.

Files:
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/incidents.ts - GET /api/v1/incidents, GET /api/v1/incidents/:id, GET /api/v1/incidents/:id/timeline.
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/index.ts - mount the new incident router.

Discrepancy references:
* DR-04 - The Express router barrel currently mounts only health.
* DD-03 - The research recommends an Express BFF over shared Postgres instead of proxying the Python service.

Success criteria:
* Incident list responses include service, severity, status, opened_at, updated_at, provider, compute_mechanism, resource_id, elapsed_seconds, and latest confidence.
* Incident detail responses include the latest diagnosis summary, evidence citations, and remediation actions.
* Timeline responses are ordered chronologically from the incident_events table.

Context references:
* artifacts/api-server/src/routes/health.ts (Lines 1-20) - current Zod-validated route pattern.
* src/sre_agent/adapters/persistence/incident_store.py (Lines 1-120) - incident projection and event persistence contract.
* src/sre_agent/adapters/persistence/diagnosis_store.py (Lines 1-100) - diagnosis result persistence contract.
* src/sre_agent/adapters/persistence/remediation_store.py (Lines 1-120) - remediation action persistence contract.
* artifacts/mockup-sandbox/src/components/mockups/sre-dashboard/Dashboard.tsx (Lines 1-200) - incident feed and remediation table requirements.
* artifacts/mockup-sandbox/src/components/mockups/sre-dashboard/IncidentDetail.tsx (Lines 1-200) - detail panel and timeline requirements.

Dependencies:
* Step 1.1 completion.
* Step 1.3 completion for response schema imports.

### Step 2.2: Implement phase and accuracy routes

Create routes for phase status and dashboard accuracy summary. Compute the values from the same tables used by the Python backend so the dashboard reflects live state rather than duplicated counters.

Files:
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/phases.ts - GET /api/v1/phases/status.
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/accuracy.ts - GET /api/v1/accuracy/summary.

Discrepancy references:
* DR-05 - The backend currently has no phase or accuracy endpoints.
* DD-04 - The plan derives metrics from SQL aggregates because no precomputed accuracy materialized view exists yet.

Success criteria:
* Phase status includes the current operational phase and graduation criteria values.
* Accuracy summary includes 7-day accuracy, auto-resolved count, pending approvals, and MTTR.
* The route implementations use the shared tables and not ad hoc in-memory counters.

Context references:
* src/sre_agent/domain/safety/phase_gate.py (Lines 1-40) - graduation criteria thresholds.
* src/sre_agent/domain/models/diagnosis.py (Lines 1-200) - confidence thresholds and severity semantics.
* src/sre_agent/adapters/persistence/migrations/009_metric_baselines_continuous_aggregate.sql (Lines 1-60) - no accuracy aggregate exists yet.
* artifacts/mockup-sandbox/src/components/mockups/sre-dashboard/AgentStatus.tsx (Lines 1-200) - phase and graduation tracker requirements.
* artifacts/mockup-sandbox/src/components/mockups/sre-dashboard/Dashboard.tsx (Lines 1-200) - KPI bar requirements.

Dependencies:
* Step 1.1 completion.
* Step 1.3 completion for response schema imports.

### Step 2.3: Register dashboard routers and response helpers

Wire the new routes into the router barrel and preserve the existing middleware order and health check behavior.

Files:
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/index.ts - import and mount the new dashboard routers.
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/app.ts - keep the current middleware ordering intact if any request/response helpers need to be shared.

Discrepancy references:
* DR-06 - The router barrel currently exposes only the health endpoint.

Success criteria:
* The new dashboard routes are mounted under /api.
* The health route still responds exactly as before.
* Response helper behavior is consistent across all new route handlers.

Context references:
* artifacts/api-server/src/app.ts (Lines 1-55) - current middleware and route mounting order.
* artifacts/api-server/src/routes/index.ts (Lines 1-20) - current router barrel.
* artifacts/api-server/src/routes/health.ts (Lines 1-20) - route style to preserve.

Dependencies:
* Step 2.1 and Step 2.2 completion.

## Implementation Phase 3: WebSocket runtime and polling feed

<!-- parallelizable: false -->

### Step 3.1: Add websocket runtime dependencies and HTTP server bootstrap

Add websocket support to the api-server package and refactor the startup path so the Express app is attached to a raw Node HTTP server.

Files:
* fullstackapp/SRE-Command-Center/artifacts/api-server/package.json - add ws and @types/ws.
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/index.ts - create the HTTP server wrapper and wire websocket startup.

Discrepancy references:
* DR-07 - WebSocket support is missing from the backend package today.
* DD-05 - The plan uses an Express HTTP wrapper instead of introducing a separate Python WebSocket endpoint.

Success criteria:
* The backend can attach a websocket server to the existing Express app.
* The process still enforces PORT validation and logs startup failures.
* The build output remains a single entrypoint that can launch the new runtime shape.

Context references:
* artifacts/api-server/src/index.ts (Lines 1-25) - current direct app.listen bootstrap.
* artifacts/api-server/build.mjs (Lines 1-120) - current single-entry build path.
* .copilot-tracking/research/subagents/2026-05-31/deep-schema-and-ws-research.md (Lines 1-120) - http.Server and ws availability findings.

Dependencies:
* Step 2.3 completion.

### Step 3.2: Implement the incidents websocket stream

Add a websocket module that emits an initial incident snapshot and subsequent updates to connected dashboard clients. Use polling against the incidents projection for the MVP transport and keep reconnect logic explicit.

Files:
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/ws/incidents.ts - websocket server implementation.

Discrepancy references:
* DR-08 - The backend has no websocket route or subscription mechanism today.
* DD-06 - The implementation uses polling because the Python persistence layer has no pg_notify channel yet.

Success criteria:
* Clients receive an initial_state message on connect.
* Clients receive incident update messages on a bounded polling interval.
* Disconnect and reconnect behavior is documented in the message protocol.

Context references:
* .copilot-tracking/research/subagents/2026-05-31/deep-schema-and-ws-research.md (Lines 1-120) - no pg_notify and polling fallback guidance.
* openspec/changes/phase-2-7-operator-dashboard/specs/dashboard-mvp/spec.md (Lines 1-120) - realtime update requirements.

Dependencies:
* Step 3.1 completion.
* Step 2.1 completion for the incident data source.

### Step 3.3: Define websocket message contracts

Make the websocket payload contracts explicit so the dashboard can reconcile missed events and render connection status cleanly.

Files:
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/ws/incidents.ts - server/client message shapes or shared runtime types.
* fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml - document the websocket-related event schemas if they are modeled alongside REST schemas.

Discrepancy references:
* DR-09 - No current message contract exists for websocket clients.

Success criteria:
* Initial snapshot and update message types are clear and versionable.
* The dashboard can detect reconnects and merge missed incident updates.

Context references:
* artifacts/mockup-sandbox/src/components/mockups/sre-dashboard/Dashboard.tsx (Lines 1-200) - live incident feed needs.
* artifacts/mockup-sandbox/src/components/mockups/sre-dashboard/IncidentDetail.tsx (Lines 1-200) - drill-down and state reconciliation needs.

Dependencies:
* Step 3.2 completion.

## Implementation Phase 4: Final validation

<!-- parallelizable: false -->

### Step 4.1: Run code generation and type validation

Run the codegen and type checks after the edits land. Keep the scope narrow and repair only local mismatches caused by the contract or schema changes.

Validation commands:
* pnpm --filter @workspace/api-spec run codegen - regenerate lib/api-zod and lib/api-client-react.
* pnpm --filter @workspace/api-server run typecheck - verify the backend package.
* pnpm run typecheck - verify the workspace-level TypeScript build path.

### Step 4.2: Run build validation

Validate the packaged backend startup path and confirm the new runtime shape compiles in the build output.

Validation commands:
* pnpm --filter @workspace/api-server run build - verify the Express + websocket entrypoint builds.
* pnpm run build - verify the workspace build pipeline still succeeds.

### Step 4.3: Record residual risks

If validation surfaces a problem that would require broad new scope, capture it in the planning log instead of expanding this plan in place.

Success criteria:
* Validation completes or produces only narrow, isolated fixes.
* Any unresolved cross-cutting issues are documented as follow-on work.

## Implementation Phase 5: Review findings remediation

<!-- parallelizable: true -->

### Step 5.1: Fix incident detail evidence compatibility

Normalize persisted diagnosis evidence payloads before validating the incident detail response body so older and current writer shapes are both accepted.

Files:
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/incidents.ts - map evidence objects to required EvidenceReference fields with resilient defaults.

Discrepancy references:
* DD-07 - Review identified a critical mismatch between persisted evidence shape and OpenAPI EvidenceReference requirements.

Success criteria:
* GET /api/v1/incidents/:id response validation succeeds when evidence entries only include source/snippet/score fields.
* Mapped evidence keeps source and snippet fidelity while safely defaulting title and uri.

Context references:
* .copilot-tracking/reviews/2026-05-31/sre-command-center-backend-endpoints-plan-review.md (Implementation Quality Findings section)
* src/sre_agent/api/rest/diagnose_router.py (Lines 251-253) - persisted evidence writer fields.
* fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml (Lines 216-246) - required EvidenceReference fields.

Dependencies:
* None.

### Step 5.2: Align accuracy summary semantics to the approved KPI contract

Align route calculations with research-defined KPI semantics: preserve diagnostic accuracy as a 7-day metric, and compute auto-resolved and MTTR as 24-hour metrics.

Files:
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/accuracy.ts - split window semantics and align response mapping.
* fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml - update field names/description only if needed for explicit 24-hour semantics.

Discrepancy references:
* DD-08 - Review identified a major semantic mismatch between research KPI contract and route implementation.

Success criteria:
* Response semantics for auto-resolved and MTTR are 24-hour.
* 7-day diagnostic accuracy remains available and correctly named.
* Generated artifacts remain aligned after codegen.

Context references:
* .copilot-tracking/research/2026-05-31/sre-command-center-backend-endpoints-research.md (Lines 433-435) - expected KPI windows.
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/accuracy.ts - current seven-day implementation.

Dependencies:
* Step 1.3 contract regeneration flow available.

### Step 5.3: Tighten websocket realtime and reconnect protocol clarity

Reduce default update interval for near-realtime dashboard behavior and codify reconnect/resync semantics so client recovery is explicit.

Files:
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/ws/incidents.ts - lower default polling interval and emit explicit reconnect baseline semantics.
* fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml - document reconnect/resync fields for websocket message schemas.

Discrepancy references:
* DD-09 - Review identified critical default-latency gap and major reconnect protocol ambiguity.

Success criteria:
* Default polling interval is reduced to satisfy near-realtime expectation.
* Stream contract includes explicit reconnect/resync guidance fields that client logic can consume.

Context references:
* .copilot-tracking/reviews/2026-05-31/sre-command-center-backend-endpoints-plan-review.md (High-severity summary)
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/ws/incidents.ts - current runtime message model and interval handling.

Dependencies:
* Step 5.2 if websocket schema changes require codegen refresh.

### Step 5.4: Resolve workspace validation blocker in mockup-sandbox

Fix the `indicatorClassName` prop typing mismatch by extending the shared Progress component props to support indicator styling overrides used by mockup pages.

Files:
* fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/src/components/ui/progress.tsx - accept and apply `indicatorClassName`.

Discrepancy references:
* DD-10 - Review identified workspace-wide typecheck/build failure due missing prop type.

Success criteria:
* Existing mockup usages compile without prop type errors.
* No visual regression risk for current consumers that do not provide `indicatorClassName`.

Context references:
* fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/src/components/mockups/sre-dashboard/AgentStatus.tsx (Lines 100, 107, 114, 223, 230)
* fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/src/components/mockups/sre-dashboard/Dashboard.tsx (Line 254)
* fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/src/components/mockups/sre-dashboard/IncidentDetail.tsx (Lines 301, 308, 315)

Dependencies:
* None.

### Step 5.5: Remove workspace build-time PORT hard requirement

Adjust the mockup-sandbox Vite configuration so workspace builds do not fail when `PORT` is unset. Preserve explicit environment override support and keep local dev behavior stable.

Files:
* fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/vite.config.ts - replace hard error with safe default/fallback parsing.

Discrepancy references:
* DD-11 - Phase 5 validation exposed a new workspace build blocker requiring PORT at build time.

Success criteria:
* `pnpm --config.verify-deps-before-run=false run build` no longer fails due missing PORT.
* Explicit `PORT` values still override the fallback when provided.

Context references:
* fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/vite.config.ts - current hard requirement and thrown errors.

Dependencies:
* Step 5.4 completion.

### Step 5.6: Remove workspace build-time BASE_PATH hard requirement

Adjust mockup-sandbox Vite base path handling so workspace builds do not fail when `BASE_PATH` is unset. Keep root path default and preserve explicit override behavior for deployment-specific routing.

Files:
* fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/vite.config.ts - default `base` to `/` when `BASE_PATH` is absent.

Discrepancy references:
* DD-12 - Post-remediation validation exposed a second environment hard requirement (`BASE_PATH`) unrelated to backend endpoint correctness.

Success criteria:
* `pnpm --config.verify-deps-before-run=false run build` no longer fails due missing `BASE_PATH`.
* Explicit `BASE_PATH` values still override the fallback when provided.

Context references:
* fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/vite.config.ts - current base path requirement.

Dependencies:
* Step 5.5 completion.

## Implementation Phase 6: Revalidation and closure

<!-- parallelizable: false -->

### Step 6.1: Regenerate contracts and run type validation

Validation commands:
* pnpm --config.verify-deps-before-run=false --filter @workspace/api-spec run codegen
* pnpm --config.verify-deps-before-run=false --filter @workspace/api-server run typecheck
* pnpm --config.verify-deps-before-run=false run typecheck

### Step 6.2: Run build validation

Validation commands:
* pnpm --config.verify-deps-before-run=false --filter @workspace/api-server run build
* pnpm --config.verify-deps-before-run=false run build

### Step 6.3: Update tracking artifacts

Success criteria:
* Plan steps 5.x and 6.x are marked complete with evidence.
* Changes log includes remediation deltas and validation outcomes.
* Review log status is updated from Needs Rework to pass-equivalent only when critical findings are closed.

## Dependencies

* pnpm workspace tooling
* TypeScript 5.9 workspace compilation
* PostgreSQL access through DATABASE_URL
* Orval code generation for lib/api-zod and lib/api-client-react
* ws and @types/ws for websocket support

## Success Criteria

* The dashboard backend exposes the new incident, timeline, phase, and accuracy surface needed by the Operator Dashboard MVP.
* The shared schema covers the current persistence tables and the migration 006 OCC addition.
* The OpenAPI contract and generated artifacts match the implemented route modules.
* The websocket runtime is attached to the Express server and uses the polling MVP transport.
* Final validation passes with no unresolved type or build blockers.
