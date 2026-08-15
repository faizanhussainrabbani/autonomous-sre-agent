<!-- markdownlint-disable-file -->
# Task Research: SRE Command Center Progress Update So Far

Repository-grounded progress summary for the SRE-Command-Center dashboard workstream as of 2026-07-05.

## Task Implementation Requests

* Summarize what is already implemented in the command center workstream.
* Identify what is partially implemented or still open.
* Capture the most relevant evidence, risks, and next research decisions.

## Scope and Success Criteria

* Scope: current progress on the SRE-Command-Center backend, dashboard package, realtime path, schema/client generation, validation coverage, and planning artifacts.
* Assumptions: the progress request refers to the fullstackapp/SRE-Command-Center workstream, not the broader SREAgent backend.
* Success Criteria:
  * A reader can tell what has been implemented versus what remains incomplete.
  * The document points to concrete repository evidence and flags the main risks.
  * The remaining decision points are reduced to a short, actionable follow-up list.

## Outline

1. Current status summary.
2. Evidence of implementation progress.
3. Partial implementation and open risks.
4. Recommended next research.

## Research Executed

### File Analysis

* .copilot-tracking/plans/2026-05-31/mockup-sandbox-to-operator-dashboard-plan.instructions.md
  * The plan is already marked complete across all five implementation phases, including package foundation, UI porting, realtime reconciliation, testing, and validation.
  * The remaining log references call out follow-on work rather than core MVP blockers.
* .copilot-tracking/research/subagents/2026-07-05/sre-command-center-progress-status-research.md
  * Subagent findings confirm a production-oriented operator-dashboard package, contract-first API server, generated client/schema packages, and websocket runtime are present.
  * The same research note identifies static UI placeholders, polling-based websocket delivery, and incomplete websocket artifact publication as the main gaps.
* /memories/repo/validation.md
  * pnpm validation in the command center can be brittle in this environment, so compile checks often need the local binary fallback or verify-deps disabled.
  * Swagger UI is already served from /docs and the OpenAPI YAML from /openapi.yaml in the api-server artifacts.

## Key Discoveries

### Current Status

The workstream is no longer at the mockup stage. The implementation path has been pushed into a production-oriented dashboard package with backend-only contract integration, generated React Query hooks, and an Express API surface that serves incidents, phases, accuracy, remediation, and websocket runtime support.

The overall picture is: core platform and contract wiring are done, UI functionality is largely in place, and the remaining work is mostly hardening, contract publication, and replacing placeholder operational copy with live state.

### Implemented Surface

* README documentation describes the command center as a pnpm monorepo with incident APIs, websocket streaming, and a separate operator dashboard runtime.
* The api-server boot path serves `/api`, `/docs`, and `/openapi.yaml`, and launches the websocket runtime with the HTTP server.
* Route mounting covers health, incidents, phases, accuracy, and remediation.
* Incidents endpoints already implement list, detail, and timeline behavior using Drizzle-backed queries.
* Phase status and accuracy dashboards are implemented server-side, including graduation criteria and KPI rollups.
* Remediation decisions update incident versioning so websocket clients can observe state changes.
* The websocket runtime exists at `/api/ws/incidents` and publishes `initial_state` and `incident_update` messages.
* Shared schema packages define incident, event, diagnosis, remediation, and coordination-audit tables.
* The generated React Query client exposes hooks for incidents, timeline, phase status, accuracy summary, and remediation decisions.
* The operator-dashboard package exists, is tied to Node backend endpoints, and includes routing, layout, API client configuration, and feature panels.
* Realtime client logic already reconnects, marks stale feeds, and resynchronizes from `/api/v1/incidents`.
* Backend-boundary tests exist to prevent unsafe imports, and the api-server includes at least one structured 400 validation test for incidents routes.

### Partially Implemented Surface

* Some UI copy is still static, including kill switch, current phase gate, blast radius, manual approval mode, and rollback readiness text.
* Websocket delivery is functional but still uses a poll-and-broadcast model rather than notification-backed push.
* The dashboard client compensates for polling with reconnect and resync behavior, but that does not remove the underlying transport limitation.
* The OpenAPI file references an AsyncAPI companion for websocket transport, but the companion artifact is not visible in the current workspace tree.

### Open Risks

* Realtime delivery is observable and recoverable, but latency and scalability remain bounded by polling.
* The dashboard still mixes live contract-backed data with canned operational text, which can make the UI feel more complete than the underlying runtime actually is.
* Validation coverage exists, but it is narrow relative to the endpoint surface already exposed.
* Websocket contract publication appears incomplete, which risks documentation drift between runtime behavior and published API expectations.

## Technical Scenarios

### Scenario 1: Assessing implementation completeness

The safest interpretation is that the command center is in a late implementation and hardening stage, not a prototype stage. The production package, backend endpoints, generated client, and websocket runtime are already present, so the remaining work is refinement rather than initial buildout.

**Requirements:**

* Distinguish completed work from remaining polish.
* Identify the smallest set of open items that still matter.

**Preferred Approach:**

* Treat the workstream as functionally implemented with known hardening gaps, not as an unfinished dashboard rewrite.

```text
Implemented: backend routes, generated client, operator dashboard package, websocket runtime
Partial: static operational labels, polling transport, websocket artifact publication
Open: broader validation, contract polishing, optional push delivery upgrade
```

**Implementation Details:**

This framing matches the plan artifact, which marks all implementation phases complete, and the subagent evidence, which shows the remaining work is concentrated in a few contract and UX areas rather than the whole stack.

#### Considered Alternatives

* Label the workstream as unfinished end-to-end. Rejected because the repository already contains the production dashboard package, backend routes, generated hooks, and operational websocket path.
* Label the workstream as fully complete. Rejected because static UI placeholders, polling-based transport, and incomplete websocket artifact publication are still unresolved.

### Scenario 2: Deciding what should be researched next

The remaining research should focus on the websocket contract and the validation surface, because those are the items most likely to influence implementation sequencing and release confidence.

**Requirements:**

* Reduce ambiguity around transport publication.
* Reduce ambiguity around test coverage and runtime confidence.

**Preferred Approach:**

* Research websocket artifact publication, then expand endpoint validation coverage if the command center is being prepared for broader rollout.

```text
Priority 1: websocket contract publication
Priority 2: transport model decision, polling vs notification-backed push
Priority 3: validation expansion for remaining routes
```

**Implementation Details:**

The current code path already compensates for polling with client-side resync, so the main unanswered question is whether that model is sufficient for the intended release stage or whether the runtime should be upgraded before more dashboard expansion.

#### Considered Alternatives

* Move straight to new feature work. Rejected because the transport and contract publication questions are still unresolved and can affect downstream dashboard behavior.
* Freeze the command center as done. Rejected because the evidence shows follow-on hardening and contract work still exists.

## Recommended Next Research

1. Confirm whether `/api/ws/incidents` should be published as a first-class AsyncAPI artifact or as an OpenAPI extension plus companion schema.
2. Decide whether websocket delivery should remain poll-based for now or move to notification-backed delivery before further dashboard expansion.
3. Expand backend route validation coverage beyond incidents so the rest of the exposed contract surface gets the same level of confidence.
4. Resolve the remaining phase-label wording drift before finalizing user-facing labels and documentation.

## Summary Table

| Field | Value |
|---|---|
| Research Document | .copilot-tracking/research/2026-07-05/sre-command-center-progress-update-so-far-research.md |
| Current Status | Production dashboard and backend contract surface are implemented; remaining work is hardening and contract polish |
| Key Discoveries | Core routes, schema, generated client, operator dashboard package, and websocket runtime are already in place |
| Open Risks | Polling-based realtime model, static UI placeholders, incomplete websocket artifact publication, narrow validation coverage |
| Follow-Up Research | AsyncAPI publication, transport model decision, validation expansion, phase-label cleanup |