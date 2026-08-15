<!-- markdownlint-disable-file -->
# Release Changes: SRE Command Center Progress Update So Far

**Related Plan**: sre-command-center-progress-update-so-far-plan.instructions.md
**Implementation Date**: 2026-07-05

## Summary

Phase 1 hardening is complete for the SRE Command Center progress update workstream. The remaining websocket contract surface is now published, the last static dashboard copy is normalized to explicit fallback language, and validation coverage was expanded around the already-exposed API and dashboard boundaries.

## Changes

### Added

* [fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/__tests__/dashboard.contract.test.ts](../../../../fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/__tests__/dashboard.contract.test.ts) - Focused contract coverage for the published phase status and accuracy summary routes.

### Modified

* [fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml](../../../../fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml) - Clarified websocket publication metadata for the dashboard contract.
* [fullstackapp/SRE-Command-Center/lib/api-spec/README.md](../../../../fullstackapp/SRE-Command-Center/lib/api-spec/README.md) - Documented websocket contract publication and frontend consumption guidance.
* [fullstackapp/SRE-Command-Center/artifacts/api-server/src/ws/incidents.ts](../../../../fullstackapp/SRE-Command-Center/artifacts/api-server/src/ws/incidents.ts) - Aligned runtime wording with the published websocket contract.
* [fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/features/incidents/incident-feed-page.tsx](../../../../fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/features/incidents/incident-feed-page.tsx) - Replaced remaining operator-facing static claims with explicit fallback labels.
* [fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/features/incidents/incident-detail-page.tsx](../../../../fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/features/incidents/incident-detail-page.tsx) - Replaced remaining operator-facing static claims with explicit fallback labels.
* [fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/test/backend-boundary.test.ts](../../../../fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/test/backend-boundary.test.ts) - Expanded boundary assertions to cover websocket URL normalization and published stream message shapes.
* [fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/test/realtime.test.ts](../../../../fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/test/realtime.test.ts) - Expanded reconnect coverage for the recovering connection label used during stale-state recovery.

## Additional or Deviating Changes

* The notification-backed websocket transport rewrite remains explicitly deferred.
	* The current poll-and-resync recovery model is adequate for the present hardening pass, so the plan stays scoped to contract publication and validation.
* The validation step used workspace diagnostics after typecheck command resolution friction.
	* The package scripts resolve `tsc` in a way that is not fully available in this environment, so workspace diagnostics were used as the cheapest reliable check.

## Release Summary

Phase 1 touched 7 existing files and added 1 new test file. The changes publish the remaining websocket contract surface, normalize live-state copy in the dashboard, and extend validation around the shipped API and dashboard boundaries without expanding into the deferred transport rewrite.
