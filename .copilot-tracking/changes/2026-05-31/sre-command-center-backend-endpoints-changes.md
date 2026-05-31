<!-- markdownlint-disable-file -->
# Release Changes: SRE Command Center Backend Operator Dashboard Endpoints

**Related Plan**: sre-command-center-backend-endpoints-plan.instructions.md
**Implementation Date**: 2026-05-31

## Summary

Implemented the Operator Dashboard backend surface in fullstackapp/SRE-Command-Center, then completed a remediation pass to close review findings on evidence compatibility, KPI semantics, websocket reconnect protocol clarity, and workspace-level build validation blockers.

## Changes

### Added

* fullstackapp/SRE-Command-Center/lib/api-zod/src/generated/types/accuracySummaryResponse.ts - Generated Zod schema for accuracy summary response.
* fullstackapp/SRE-Command-Center/lib/api-zod/src/generated/types/diagnosisSnapshot.ts - Generated Zod schema for diagnosis snapshot.
* fullstackapp/SRE-Command-Center/lib/api-zod/src/generated/types/errorResponse.ts - Generated Zod schema for API error response envelope.
* fullstackapp/SRE-Command-Center/lib/api-zod/src/generated/types/evidenceReference.ts - Generated Zod schema for diagnosis evidence references.
* fullstackapp/SRE-Command-Center/lib/api-zod/src/generated/types/incidentDetailResponse.ts - Generated Zod schema for incident detail endpoint.
* fullstackapp/SRE-Command-Center/lib/api-zod/src/generated/types/incidentListResponse.ts - Generated Zod schema for incident list endpoint.
* fullstackapp/SRE-Command-Center/lib/api-zod/src/generated/types/incidentStreamInitialState.ts - Generated websocket initial-state schema.
* fullstackapp/SRE-Command-Center/lib/api-zod/src/generated/types/incidentStreamUpdate.ts - Generated websocket update schema.
* fullstackapp/SRE-Command-Center/lib/api-zod/src/generated/types/incidentSummary.ts - Generated schema for incident summary records.
* fullstackapp/SRE-Command-Center/lib/api-zod/src/generated/types/incidentTimelineResponse.ts - Generated schema for incident timeline response.
* fullstackapp/SRE-Command-Center/lib/api-zod/src/generated/types/listIncidentsParams.ts - Generated query-parameter schema for incidents list.
* fullstackapp/SRE-Command-Center/lib/api-zod/src/generated/types/phaseCriterion.ts - Generated schema for graduation criteria entry.
* fullstackapp/SRE-Command-Center/lib/api-zod/src/generated/types/phaseStatusResponse.ts - Generated schema for phase status endpoint.
* fullstackapp/SRE-Command-Center/lib/api-zod/src/generated/types/remediationActionSummary.ts - Generated schema for remediation action summaries.
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/incidents.ts - Added incident list/detail/timeline REST routes with DB-backed queries and response-schema validation.
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/phases.ts - Added phase status REST route with graduation criteria projections.
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/accuracy.ts - Added accuracy summary REST route for dashboard KPI consumption.
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/response-helpers.ts - Added shared response helpers for JSON success/error handling and consistent status codes.
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/ws/incidents.ts - Added websocket runtime for /api/ws/incidents with initial snapshot and polling update stream.

### Modified

* fullstackapp/SRE-Command-Center/lib/db/src/schema/index.ts - Added typed Drizzle read schema definitions for incidents, incident_events, diagnosis_results, remediation_actions, and coordination_audit including incidents.version.
* fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml - Expanded API contract with incidents, timeline, phase status, and accuracy summary endpoints plus supporting schemas.
* fullstackapp/SRE-Command-Center/lib/api-client-react/src/generated/api.ts - Regenerated React Query client for the expanded contract.
* fullstackapp/SRE-Command-Center/lib/api-client-react/src/generated/api.schemas.ts - Regenerated TypeScript schema types for API client package.
* fullstackapp/SRE-Command-Center/lib/api-zod/src/generated/api.ts - Regenerated root Zod export definitions.
* fullstackapp/SRE-Command-Center/lib/api-zod/src/generated/types/healthStatus.ts - Regenerated shared health type export.
* fullstackapp/SRE-Command-Center/lib/api-zod/src/generated/types/index.ts - Regenerated type barrel exports including new endpoint schemas.
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/index.ts - Registered incidents, phases, and accuracy routers while preserving health route behavior.
* fullstackapp/SRE-Command-Center/artifacts/api-server/package.json - Added websocket runtime dependencies for api-server package.
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/index.ts - Refactored bootstrap to HTTP server wrapper with websocket attachment and graceful shutdown handling.
* fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/src/components/ui/progress.tsx - Added optional `indicatorClassName` prop support to satisfy existing mockup usages and restore workspace typecheck compatibility.
* fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/vite.config.ts - Added safe `PORT` and `BASE_PATH` fallbacks so workspace builds succeed without shell-specific env requirements.
* fullstackapp/SRE-Command-Center/pnpm-lock.yaml - Updated lockfile to reflect websocket dependency graph changes.

### Removed

* None.

## Additional or Deviating Changes

* Validation command execution required `pnpm --config.verify-deps-before-run=false` because workspace preinstall guards blocked the default command path.
  * This is an execution-environment deviation only; generated outputs and library typecheck still completed successfully.
* During remediation validation, workspace build surfaced additional env-coupled blockers (`PORT`, then `BASE_PATH`) in mockup-sandbox Vite config.
  * Both were addressed with explicit fallback defaults while retaining explicit override behavior.

## Release Summary

Phase 1 complete: contract and schema foundation delivered.

Phase 2 complete: dashboard REST route surface delivered.

Phase 3 complete: websocket runtime and incident stream delivered.

Phase 4 complete: initial validation executed.

Phase 5 complete: review findings remediated.

Phase 6 complete: final revalidation and closure.

Files affected in this phase:
* Added: 19 files (14 generated Zod type files, 4 api-server route/helper modules, and 1 websocket module).
* Modified: 13 files including Drizzle schema, OpenAPI contract, regenerated API client/Zod artifacts, route registration, websocket bootstrap/dependencies, workspace mockup compatibility fixes, and lockfile.
* Removed: 0.

Validation summary:
* `pnpm --config.verify-deps-before-run=false --filter @workspace/api-spec run codegen` completed successfully.
* `pnpm --config.verify-deps-before-run=false --filter @workspace/api-server run typecheck` completed successfully.
* `pnpm --config.verify-deps-before-run=false run typecheck` completed successfully.
* `pnpm --config.verify-deps-before-run=false --filter @workspace/api-server run build` completed successfully.
* `pnpm --config.verify-deps-before-run=false run build` completed successfully.

Overall validation status for this change:
* Backend package scope (`@workspace/api-server` + contract/codegen): Passed.
* Full workspace scope: Passed.
