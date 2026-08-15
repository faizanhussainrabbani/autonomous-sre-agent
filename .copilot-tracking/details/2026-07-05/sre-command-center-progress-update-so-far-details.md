<!-- markdownlint-disable-file -->
# Implementation Details: SRE Command Center Progress Update So Far

## Context Reference

Sources: .copilot-tracking/research/2026-07-05/sre-command-center-progress-update-so-far-research.md, .copilot-tracking/research/subagents/2026-07-05/sre-command-center-progress-status-research.md, .copilot-tracking/plans/2026-05-31/mockup-sandbox-to-operator-dashboard-plan.instructions.md, .copilot-tracking/plans/logs/2026-05-31/mockup-sandbox-to-operator-dashboard-log.md, /home/faizan-hussain/Documents/PersonalProjects/SREAgent/CLAUDE.md, /home/faizan-hussain/Documents/PersonalProjects/SREAgent/AGENTS.md

## Implementation Phase 1: Publish the remaining contract surface and normalize dashboard state copy

<!-- parallelizable: true -->

### Step 1.1: Publish the websocket contract as a stable artifact

Clarify and publish the websocket contract surface so the dashboard no longer depends on runtime source inspection for transport semantics. Keep the current poll-and-resync behavior for now, but make the contract explicit in repository artifacts.

Files:
* fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml - Add explicit websocket reference metadata or extension notes for /api/ws/incidents
* fullstackapp/SRE-Command-Center/lib/api-spec/asyncapi-incidents.yaml - Optional companion artifact if OpenAPI extension metadata is insufficient
* fullstackapp/SRE-Command-Center/lib/api-spec/README.md - Contract publication guidance and frontend consumption notes
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/ws/incidents.ts - Align in-code comments or exported constants with the published contract wording

Discrepancy references:
* Addresses DD-01 in the planning log by stabilizing the current contract surface while deferring a transport rewrite

Success criteria:
* The websocket path and message semantics are documented in a stable artifact
* Frontend integration can reference the published contract without reading server implementation files

Context references:
* .copilot-tracking/research/2026-07-05/sre-command-center-progress-update-so-far-research.md (Lines 67-70) - Contract publication gap
* .copilot-tracking/research/2026-07-05/sre-command-center-progress-update-so-far-research.md (Lines 111-130) - Transport decision context

Dependencies:
* Current operator-dashboard and api-server runtime artifacts
* Selected contract publication strategy recorded in the planning log

### Step 1.2: Normalize static operational copy and phase wording in the dashboard package

Replace or clearly label the remaining static operational copy so the UI does not imply live state that is not yet sourced from backend data. Normalize the phase wording and fallback copy to match the implemented runtime behavior.

Files:
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/features/incidents/incident-feed-page.tsx - Static status copy cleanup
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/features/incidents/incident-detail-page.tsx - Secondary incident detail copy cleanup
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/features/phases/phase-status-panel.tsx - Phase wording and live-state alignment
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/README.md - Document any intentionally static fallback language

Discrepancy references:
* Addresses DD-02 in the planning log by separating live state from placeholder status text

Success criteria:
* Static operational claims are removed, replaced, or explicitly labeled as fallback
* Phase labels and operator-facing copy match the current dashboard runtime model

Context references:
* .copilot-tracking/research/2026-07-05/sre-command-center-progress-update-so-far-research.md (Lines 67-77) - Static copy and open risk summary
* .copilot-tracking/research/2026-07-05/sre-command-center-progress-update-so-far-research.md (Lines 137-142) - Phase-label cleanup follow-up

Dependencies:
* Step 1.1 completion or a confirmed contract publication decision

### Step 1.3: Expand validation coverage around the exposed API and dashboard boundaries

Add or widen tests so the exposed command center contract and dashboard boundary behavior are covered beyond the existing incidents validation check. Focus on the surfaces already implemented rather than adding new product scope.

Files:
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/__tests__/incidents.validation.test.ts - Extend structured 4xx coverage where missing
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/__tests__/phases.test.ts - Add route coverage if currently absent
* fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/__tests__/accuracy.test.ts - Add route coverage if currently absent
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/test/backend-boundary.test.ts - Keep backend-only import and endpoint assertions current
* fullstackapp/SRE-Command-Center/artifacts/operator-dashboard/src/test/realtime.test.ts - Cover reconnect and stale-state recovery behavior

Discrepancy references:
* Addresses DD-03 in the planning log by broadening validation confidence without changing the implementation architecture

Success criteria:
* Validation covers the exposed endpoint surface at a level consistent with the dashboard contract
* Dashboard boundary tests continue to fail on unsafe backend imports or endpoint drift

Context references:
* .copilot-tracking/research/2026-07-05/sre-command-center-progress-update-so-far-research.md (Lines 74-77) - Validation coverage risk
* .copilot-tracking/research/2026-07-05/sre-command-center-progress-update-so-far-research.md (Lines 55-63) - Existing endpoint and boundary coverage

Dependencies:
* Step 1.1 and Step 1.2 completion or explicit scoping decisions

### Step 1.4: Validate phase changes

Run targeted validation for the touched command center surfaces before moving to final validation.

Validation commands:
* pnpm --config.verify-deps-before-run=false --filter @workspace/api-server test - api-server route and contract checks
* pnpm --config.verify-deps-before-run=false --filter @workspace/operator-dashboard test - dashboard and boundary checks
* pnpm --config.verify-deps-before-run=false --filter @workspace/operator-dashboard typecheck - dashboard type safety

## Implementation Phase 2: Final validation and handoff

<!-- parallelizable: false -->

### Step 2.1: Run full project validation

Execute the broader validation set for the command center surfaces that changed during planning follow-up.

Validation commands:
* pnpm --config.verify-deps-before-run=false --filter @workspace/api-server lint
* pnpm --config.verify-deps-before-run=false --filter @workspace/operator-dashboard lint
* pnpm --config.verify-deps-before-run=false --filter @workspace/api-server build
* pnpm --config.verify-deps-before-run=false --filter @workspace/operator-dashboard build
* pnpm --config.verify-deps-before-run=false --filter @workspace/api-server test
* pnpm --config.verify-deps-before-run=false --filter @workspace/operator-dashboard test

### Step 2.2: Fix minor validation issues

Repair isolated lint, type, or test issues introduced by the scoped follow-up work. Keep fixes local to the command center surfaces.

### Step 2.3: Report blocking issues

Document any unresolved transport, contract, or validation gaps that require future planning instead of forcing a broader rewrite into this plan.

## Dependencies

* Command center workspace tooling and package scripts
* The validation fallback documented in /memories/repo/validation.md

## Success Criteria

* The current contract and dashboard state are documented in repository artifacts
* Validation expands beyond the incidents route without changing the architecture direction
* Deferred transport rewrite work is clearly separated from the present plan