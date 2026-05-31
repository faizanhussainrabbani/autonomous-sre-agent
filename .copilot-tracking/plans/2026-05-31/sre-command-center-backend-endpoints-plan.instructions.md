---
description: "Implementation plan for SRE Command Center operator dashboard backend endpoints"
applyTo: 'fullstackapp/SRE-Command-Center/**'
---
<!-- markdownlint-disable-file -->
# Implementation Plan: SRE Command Center Backend Operator Dashboard Endpoints

## Overview

Deliver the dashboard-facing backend surface for the SRE Command Center by extending the Express app into a read-only dashboard BFF over the shared PostgreSQL schema, adding the missing incident/summary/phase endpoints, and wiring a polling-based WebSocket feed until PostgreSQL notifications exist.

## Objectives

### User Requirements

* Deliver an implementation plan with milestones and task breakdown — Source: user request in this conversation.
* Focus on the backend application, database migrations, and schema — Source: user request in this conversation.
* Support the Operator Dashboard MVP endpoints from openspec/changes/phase-2-7-operator-dashboard — Source: user request plus research file .copilot-tracking/research/2026-05-31/sre-command-center-backend-endpoints-research.md.

### Derived Objectives

* Treat fullstackapp/SRE-Command-Center as the owner of the dashboard read surface, not the Python API server — Derived from: research showed the Express backend currently exposes only healthz while the Python SRE Agent already owns operational endpoints.
* Model the dashboard read paths against the existing Postgres persistence tables and later migrations — Derived from: migration 001 plus migration 006 OCC and migration 003 coordination audit evidence.
* Keep the API contract contract-first with OpenAPI -> Orval -> generated Zod/React Query artifacts — Derived from: current repo conventions in lib/api-spec and lib/api-zod.
* Use polling for WebSocket MVP delivery because the Python SRE Agent currently emits no pg_notify/NOTIFY events — Derived from: deep schema and websocket research.

## Context Summary

### Project Files

* fullstackapp/SRE-Command-Center/artifacts/api-server/src/app.ts - current Express middleware stack and route mounting.
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/index.ts - current app.listen bootstrap that must become websocket-capable.
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/index.ts - current router barrel that only mounts health.
* fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml - current one-route contract to extend.
* fullstackapp/SRE-Command-Center/lib/db/src/schema/index.ts - empty schema scaffold that must become the typed read model.
* fullstackapp/SRE-Command-Center/lib/db/package.json - already includes drizzle-orm, drizzle-zod, pg, and zod.
* fullstackapp/SRE-Command-Center/artifacts/api-server/package.json - missing ws and @types/ws.
* src/sre_agent/adapters/persistence/migrations/001_incident_lifecycle.sql - canonical incident and event table shape.
* src/sre_agent/adapters/persistence/migrations/003_coordination_audit.sql - coordination audit table shape for operator history.
* src/sre_agent/adapters/persistence/migrations/006_schema_improvements.sql - incidents.version and trace tables.
* src/sre_agent/adapters/persistence/migrations/007_partition_readiness_and_status_fidelity.sql - incident_events partition/cutover and remediation status fidelity.
* src/sre_agent/adapters/persistence/migrations/010_incident_events_partition_cutover.sql - final incident_events cutover behavior.
* artifacts/mockup-sandbox/src/components/mockups/sre-dashboard/Dashboard.tsx - KPI and feed data requirements.
* artifacts/mockup-sandbox/src/components/mockups/sre-dashboard/IncidentDetail.tsx - detail, timeline, and remediation data requirements.
* artifacts/mockup-sandbox/src/components/mockups/sre-dashboard/AgentStatus.tsx - phase and graduation tracker data requirements.

### References

* .copilot-tracking/research/2026-05-31/sre-command-center-backend-endpoints-research.md - primary research synthesis and selected architecture path.
* .copilot-tracking/research/subagents/2026-05-31/deep-schema-and-ws-research.md - verified schema drift, pg_notify absence, and websocket runtime constraints.
* .copilot-tracking/research/subagents/2026-05-31/dashboard-backend-surface-research.md - generated client and runtime surface confirmation.
* openspec/changes/phase-2-7-operator-dashboard/tasks.md - dashboard MVP endpoint scope.
* openspec/changes/phase-2-7-operator-dashboard/specs/dashboard-mvp/spec.md - dashboard requirements and realtime behavior.

### Standards References

* AGENTS.md - coordination, safety, and shared schema expectations.
* CLAUDE.md - architecture, contract-first, and validation conventions.
* fullstackapp/SRE-Command-Center/lib/api-spec/orval.config.ts - title transformer and codegen conventions.

## Implementation Checklist

### [x] Implementation Phase 1: Contract and schema foundation

<!-- parallelizable: false -->

* [x] Step 1.1: Extend the Drizzle read schema
  * Add typed table definitions in fullstackapp/SRE-Command-Center/lib/db/src/schema/index.ts for incidents, incident_events, diagnosis_results, remediation_actions, and coordination_audit.
  * Include incidents.version and the partition-cutover-safe incident_events shape.
  * Details: .copilot-tracking/details/2026-05-31/sre-command-center-backend-endpoints-details.md (Lines 22-47)
* [x] Step 1.2: Expand the OpenAPI contract for the dashboard surface
  * Add incident list/detail/timeline, phase status, accuracy summary, and websocket-related schemas to fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml.
  * Preserve the Api title transformer assumption.
  * Details: .copilot-tracking/details/2026-05-31/sre-command-center-backend-endpoints-details.md (Lines 50-73)
* [x] Step 1.3: Regenerate generated API artifacts
  * Run the Orval codegen path for lib/api-zod and lib/api-client-react after the OpenAPI update.
  * Confirm generated exports remain aligned with the new endpoint names and response models.
  * Details: .copilot-tracking/details/2026-05-31/sre-command-center-backend-endpoints-details.md (Lines 75-97)

### [x] Implementation Phase 2: Dashboard REST endpoints

<!-- parallelizable: true -->

* [x] Step 2.1: Implement incident query routes
  * Add GET /api/v1/incidents, GET /api/v1/incidents/:id, and GET /api/v1/incidents/:id/timeline route modules under fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/.
  * Query against the Drizzle schema and validate response bodies before sending them.
  * Details: .copilot-tracking/details/2026-05-31/sre-command-center-backend-endpoints-details.md (Lines 103-127)
* [x] Step 2.2: Implement phase and accuracy routes
  * Add GET /api/v1/phases/status and GET /api/v1/accuracy/summary route modules.
  * Compute metrics from incidents, diagnosis_results, remediation_actions, and coordination data using SQL aggregates.
  * Details: .copilot-tracking/details/2026-05-31/sre-command-center-backend-endpoints-details.md (Lines 128-154)
* [x] Step 2.3: Register dashboard routers and response helpers
  * Update fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/index.ts to mount the new dashboard routers under /api.
  * Keep the existing health router in place and preserve the global error handling order.
  * Details: .copilot-tracking/details/2026-05-31/sre-command-center-backend-endpoints-details.md (Lines 156-178)

### [x] Implementation Phase 3: WebSocket runtime and polling feed

<!-- parallelizable: false -->

* [x] Step 3.1: Add websocket runtime dependencies and HTTP server bootstrap
  * Add ws and @types/ws to fullstackapp/SRE-Command-Center/artifacts/api-server/package.json.
  * Refactor fullstackapp/SRE-Command-Center/artifacts/api-server/src/index.ts to create a raw HTTP server around the Express app so the websocket server can attach.
  * Details: .copilot-tracking/details/2026-05-31/sre-command-center-backend-endpoints-details.md (Lines 183-206)
* [x] Step 3.2: Implement the incidents websocket stream
  * Add a websocket module that publishes incident snapshots and update events on /api/ws/incidents.
  * Use polling against the incidents projection as the MVP transport and keep reconnect behavior explicit.
  * Details: .copilot-tracking/details/2026-05-31/sre-command-center-backend-endpoints-details.md (Lines 208-230)
* [x] Step 3.3: Define websocket message contracts
  * Add server message shapes for initial state and incident updates in the OpenAPI-backed schema or adjacent runtime types.
  * Keep the payload minimal enough for the dashboard feed to reconcile missed updates.
  * Details: .copilot-tracking/details/2026-05-31/sre-command-center-backend-endpoints-details.md (Lines 232-252)

### [x] Implementation Phase 4: Final validation

<!-- parallelizable: false -->

* [x] Step 4.1: Run code generation and type validation
  * Run the OpenAPI codegen path, workspace typecheck, and api-server typecheck after the file edits land.
  * Fix only local type or schema mismatches in this phase.
* [x] Step 4.2: Run build validation
  * Build the workspace and the api-server package to verify the HTTP + websocket startup path.
  * Confirm the new routes compile in the packaged output.
* [x] Step 4.3: Record residual risks
  * Capture any remaining follow-on work in the planning log instead of broadening the implementation scope.

### [x] Implementation Phase 5: Review findings remediation

<!-- parallelizable: true -->

* [x] Step 5.1: Fix incident detail evidence compatibility
  * Normalize persisted diagnosis evidence objects into the API EvidenceReference shape before response validation, with safe fallbacks for missing fields.
  * Ensure GET /api/v1/incidents/:id cannot fail when evidence rows contain source/snippet/score-only payloads.
  * Details: .copilot-tracking/details/2026-05-31/sre-command-center-backend-endpoints-details.md (Lines 268-289)
* [x] Step 5.2: Align accuracy summary semantics to the approved KPI contract
  * Move auto-resolved and MTTR metrics to 24-hour semantics while preserving 7-day diagnostic accuracy.
  * Keep response field names and OpenAPI schema aligned with route behavior.
  * Details: .copilot-tracking/details/2026-05-31/sre-command-center-backend-endpoints-details.md (Lines 291-315)
* [x] Step 5.3: Tighten websocket realtime and reconnect protocol clarity
  * Reduce default polling interval to satisfy near-realtime feed expectations.
  * Add explicit reconnect/resync protocol semantics in runtime and OpenAPI contract so clients can reconcile missed updates.
  * Details: .copilot-tracking/details/2026-05-31/sre-command-center-backend-endpoints-details.md (Lines 317-347)
* [x] Step 5.4: Resolve workspace validation blocker in mockup-sandbox
  * Fix `indicatorClassName` typing mismatch causing workspace-level typecheck/build failures.
  * Keep changes minimal and scoped to shared progress component typing.
  * Details: .copilot-tracking/details/2026-05-31/sre-command-center-backend-endpoints-details.md (Lines 349-365)
* [x] Step 5.5: Remove workspace build-time PORT hard requirement
  * Make mockup-sandbox build resilient when PORT is not provided in CI/local shell environments.
  * Keep dev-server behavior unchanged and allow explicit PORT override when present.
  * Details: .copilot-tracking/details/2026-05-31/sre-command-center-backend-endpoints-details.md (Lines 401-418)
* [x] Step 5.6: Remove workspace build-time BASE_PATH hard requirement
  * Make mockup-sandbox build resilient when BASE_PATH is not provided by defaulting to root base path.
  * Preserve explicit BASE_PATH override and keep production routing behavior configurable.
  * Details: .copilot-tracking/details/2026-05-31/sre-command-center-backend-endpoints-details.md (Lines 420-438)

### [x] Implementation Phase 6: Revalidation and closure

<!-- parallelizable: false -->

* [x] Step 6.1: Regenerate contracts and validate package/workspace typecheck
  * Run the OpenAPI codegen path and both api-server and workspace typechecks.
* [x] Step 6.2: Validate package/workspace build outputs
  * Run api-server build and workspace build.
* [x] Step 6.3: Update tracking artifacts for remediated findings
  * Update the changes log, planning log discrepancy section, and review log status.

## Planning Log

See .copilot-tracking/plans/logs/2026-05-31/sre-command-center-backend-endpoints-log.md for discrepancy tracking, implementation path selection, and follow-on work.

## Dependencies

* pnpm workspace tooling
* TypeScript 5.9 workspace compilation
* Drizzle ORM and drizzle-zod already present in lib/db/package.json
* ws and @types/ws for websocket support
* PostgreSQL database access through DATABASE_URL
* Orval code generation for lib/api-zod and lib/api-client-react

## Success Criteria

* The Express backend exposes all dashboard endpoints needed for the Operator Dashboard MVP — Traces to: openspec/changes/phase-2-7-operator-dashboard/tasks.md and the current research file.
* The shared database schema is typed for dashboard reads, including incidents.version and coordination_audit — Traces to: migrations 001, 003, 006, 007, and 010.
* The OpenAPI contract and generated client artifacts are aligned with the new routes — Traces to: lib/api-spec/openapi.yaml and the Orval config.
* The websocket feed is available on /api/ws/incidents with a polling fallback architecture — Traces to: the research finding that Python emits no pg_notify today.
* Final validation passes with no unresolved type or build blockers — Traces to: workspace validation commands and the api-server build path.
