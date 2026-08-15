<!-- markdownlint-disable-file -->
# Research: OpenSpec Phase 2.7 Operator Dashboard Requirements Analysis

## Research Topics and Questions

- Analyze proposal, design, tasks, and spec deltas for openspec/changes/phase-2-7-operator-dashboard.
- Extract mandatory versus optional deliverables, dependency order, and risk controls.
- Map requirements to likely implementation surfaces in fullstackapp/SRE-Command-Center.
- Identify ambiguities, missing acceptance tests, and contradictions.
- Preserve hard architectural constraint: frontend must only consume Node.js backend contracts and must not depend on direct SRE-Agent internals.

## Primary Evidence Sources

- openspec/changes/phase-2-7-operator-dashboard/.openspec.yaml:1-4
- openspec/changes/phase-2-7-operator-dashboard/proposal.md:1-25
- openspec/changes/phase-2-7-operator-dashboard/design.md:1-38
- openspec/changes/phase-2-7-operator-dashboard/tasks.md:1-46
- openspec/changes/phase-2-7-operator-dashboard/specs/dashboard-mvp/spec.md:1-64
- openspec/changes/autonomous-sre-agent/specs/operator-dashboard/spec.md:1-61
- fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:1-132
- fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:430-517
- fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/incidents.ts:154-280
- fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/phases.ts:35-179
- fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/accuracy.ts:23-95
- fullstackapp/SRE-Command-Center/artifacts/api-server/src/ws/incidents.ts:14-337
- fullstackapp/SRE-Command-Center/artifacts/api-server/src/index.ts:21-37
- fullstackapp/SRE-Command-Center/artifacts/api-server/src/app.ts:109-114
- fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/src/App.tsx:99-144
- fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/src/main.tsx:1-5
- fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/src/components/mockups/sre-dashboard/Dashboard.tsx:21-241
- fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/src/components/mockups/sre-dashboard/IncidentDetail.tsx:30-242
- fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/src/components/mockups/sre-dashboard/AgentStatus.tsx:29-260
- .copilot-tracking/research/2026-05-31/mockup-sandbox-to-operator-dashboard-research.md:4
- .copilot-tracking/research/2026-05-31/mockup-sandbox-to-operator-dashboard-research.md:96-98

## Major Findings

### 1) Phase 2.7 Scope Is Explicitly MVP and Spec-Driven

- The change is explicitly Phase 2.7, titled "Operator Dashboard MVP".
  - openspec/changes/phase-2-7-operator-dashboard/.openspec.yaml:3-4
- Proposal positions this as concrete implementation of previously abstract operator-dashboard capability.
  - openspec/changes/phase-2-7-operator-dashboard/proposal.md:5
  - openspec/changes/phase-2-7-operator-dashboard/proposal.md:24

### 2) Deliverables Are Split Across API Surface, Realtime Channel, and Dashboard UI

- Required API and WS endpoints are enumerated in critical-path task block DASH-001.
  - openspec/changes/phase-2-7-operator-dashboard/tasks.md:1-8
- UI work is explicitly sequenced after API work (DASH-002 onward).
  - openspec/changes/phase-2-7-operator-dashboard/tasks.md:10-40
- Test expectations are listed in DASH-007.
  - openspec/changes/phase-2-7-operator-dashboard/tasks.md:42-46

### 3) Current SRE Command Center Backend Already Implements Core DASH-001 Surface

- REST routes implemented:
  - GET /v1/incidents in fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/incidents.ts:154-181
  - GET /v1/incidents/:id in fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/incidents.ts:183-241
  - GET /v1/incidents/:id/timeline in fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/incidents.ts:243-280
  - GET /v1/phases/status in fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/phases.ts:35-173
  - GET /v1/accuracy/summary in fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/accuracy.ts:23-93
- WebSocket runtime implemented at path /api/ws/incidents:
  - path constant in fullstackapp/SRE-Command-Center/artifacts/api-server/src/ws/incidents.ts:14
  - runtime startup in fullstackapp/SRE-Command-Center/artifacts/api-server/src/index.ts:22
- API router mounted under /api:
  - fullstackapp/SRE-Command-Center/artifacts/api-server/src/app.ts:109

### 4) Current Frontend Is Still a Mockup Preview Sandbox, Not a Production Dashboard App

- App entry renders either preview route or gallery, not a dashboard application shell.
  - fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/src/App.tsx:99-144
  - fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/src/main.tsx:1-5
- Dashboard, IncidentDetail, AgentStatus components are static mockups with hardcoded values and no data-fetching integration.
  - fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/src/components/mockups/sre-dashboard/Dashboard.tsx:21-241
  - fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/src/components/mockups/sre-dashboard/IncidentDetail.tsx:30-242
  - fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/src/components/mockups/sre-dashboard/AgentStatus.tsx:29-260

## Mandatory vs Optional Deliverables

### Mandatory (Normative via SHALL scenarios and critical-path tasks)

- Performance SLO-like UI behavior:
  - FCP <= 200ms, feed populated <= 500ms, 50+ incident load <= 1s, no frozen frame >100ms.
  - openspec/changes/phase-2-7-operator-dashboard/specs/dashboard-mvp/spec.md:7-20
- Realtime feed behavior:
  - New/updated incidents reflected <= 1s, no manual refresh.
  - openspec/changes/phase-2-7-operator-dashboard/specs/dashboard-mvp/spec.md:22-35
- WS recovery behavior:
  - reconnect <= 5s, reconnected notification, missed-event reconciliation.
  - openspec/changes/phase-2-7-operator-dashboard/specs/dashboard-mvp/spec.md:37-42
- Responsive behavior:
  - desktop split layout and tablet single-column accessibility.
  - openspec/changes/phase-2-7-operator-dashboard/specs/dashboard-mvp/spec.md:44-56
- API/WS endpoint set in DASH-001:
  - openspec/changes/phase-2-7-operator-dashboard/tasks.md:1-8
- Core dashboard feature areas from original capability spec still extended by phase 2.7:
  - realtime status, confidence decomposition, accuracy views, timeline drill-down, graduation tracker.
  - openspec/changes/autonomous-sre-agent/specs/operator-dashboard/spec.md:3-61

### Optional or Deferred (Explicit non-goals or implementation choices)

- Explicitly deferred (non-goals): auth/RBAC, custom alert config UI, historical export, multi-tenant.
  - openspec/changes/phase-2-7-operator-dashboard/design.md:15-19
- Technology choices appear as design decisions, not SHALL requirements:
  - Next.js 15 App Router.
  - Tailwind CSS.
  - WebSocket over SSE/polling.
  - openspec/changes/phase-2-7-operator-dashboard/design.md:23-30
- Docker Compose dashboard service is listed in proposal, but not represented as scenario-level acceptance criteria.
  - openspec/changes/phase-2-7-operator-dashboard/proposal.md:13

## Sequencing Dependencies

1. API contract stabilization and endpoint readiness first (DASH-001).
   - openspec/changes/phase-2-7-operator-dashboard/tasks.md:1-8
   - Implementation surface: fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/*.ts and fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml
2. Dashboard runtime foundation second (DASH-002): app shell + WS client + reconnect status.
   - openspec/changes/phase-2-7-operator-dashboard/tasks.md:10-16
   - Candidate surface: fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/src/App.tsx and a new feature-oriented dashboard app shell under artifacts/mockup-sandbox/src
3. Incident feed/detail (DASH-003) depends on both list and detail/timeline APIs.
   - openspec/changes/phase-2-7-operator-dashboard/tasks.md:17-23
   - Candidate surfaces: incidents route contract and dashboard feed/detail mockups
4. Confidence/timeline/tracker modules (DASH-004/005/006) depend on enriched backend payload semantics.
   - openspec/changes/phase-2-7-operator-dashboard/tasks.md:24-40
   - Candidate surfaces: accuracy + phases endpoints, incident detail model, websocket update payloads
5. Testing (DASH-007) should gate completion and acceptance.
   - openspec/changes/phase-2-7-operator-dashboard/tasks.md:42-46

## Risk Controls Required by Spec and Current Backend Support

### Required Controls from Design

- WS disconnect resilience with auto-reconnect and user-visible status.
  - openspec/changes/phase-2-7-operator-dashboard/design.md:36
  - openspec/changes/phase-2-7-operator-dashboard/specs/dashboard-mvp/spec.md:37-42
- Staleness controls: timestamps, last-updated indication, forced refresh.
  - openspec/changes/phase-2-7-operator-dashboard/design.md:37

### Existing Backend Mechanisms Supporting Control Objectives

- WS initial snapshot + incremental updates with sequence and resync token semantics.
  - fullstackapp/SRE-Command-Center/artifacts/api-server/src/ws/incidents.ts:265-277
  - fullstackapp/SRE-Command-Center/artifacts/api-server/src/ws/incidents.ts:227-233
  - fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:465-473
  - fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:497-505
- Configurable WS poll interval with floor validation.
  - fullstackapp/SRE-Command-Center/artifacts/api-server/src/ws/incidents.ts:95-109
- Route-level typed response validation via shared zod contracts.
  - fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/incidents.ts:175-180
  - fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/phases.ts:168-172
  - fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/accuracy.ts:85-92

## Requirement-to-Implementation Surface Mapping

### API and Contracts

- Requirement: Incident feed list and sorting/filter support.
  - Spec/tasks source: openspec/changes/phase-2-7-operator-dashboard/tasks.md:3,19-21
  - Current surface: fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/incidents.ts:154-181
  - Contract: fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:31-61
- Requirement: Incident detail + evidence + timeline drill-down.
  - Spec/tasks source: openspec/changes/phase-2-7-operator-dashboard/tasks.md:4-5,22,32-34
  - Current surface: fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/incidents.ts:183-280
  - Contract: fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:62-103
- Requirement: Graduation phase status.
  - Spec/tasks source: openspec/changes/phase-2-7-operator-dashboard/tasks.md:6,38-40
  - Current surface: fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/phases.ts:35-173
  - Contract: fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:104-116
- Requirement: Accuracy summary KPIs.
  - Spec/tasks source: openspec/changes/phase-2-7-operator-dashboard/tasks.md:7
  - Current surface: fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/accuracy.ts:23-93
  - Contract: fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:117-132,430-459
- Requirement: Realtime incident stream.
  - Spec/tasks source: openspec/changes/phase-2-7-operator-dashboard/tasks.md:8
  - Current surface: fullstackapp/SRE-Command-Center/artifacts/api-server/src/ws/incidents.ts:14-337
  - Contract note: OpenAPI currently documents WS message schemas only, not the WS path itself.
  - Evidence: fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:460-517

### Frontend Conversion Surfaces (from mockup to operator dashboard)

- App shell and routing conversion point:
  - fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/src/App.tsx:99-144
- Incident feed UX skeleton:
  - fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/src/components/mockups/sre-dashboard/Dashboard.tsx:56-158
- KPI and graduation/status visual elements:
  - fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/src/components/mockups/sre-dashboard/Dashboard.tsx:27-54
  - fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/src/components/mockups/sre-dashboard/AgentStatus.tsx:60-131
- Incident drill-down/timeline skeleton:
  - fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/src/components/mockups/sre-dashboard/IncidentDetail.tsx:81-122
  - fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/src/components/mockups/sre-dashboard/IncidentDetail.tsx:129-190

## Ambiguities, Missing Acceptance Tests, and Contradictions

### Contradictions

- Framework/runtime mismatch in artifacts:
  - Proposal/design/tasks target FastAPI and Next.js dashboard path (`dashboard/`).
    - openspec/changes/phase-2-7-operator-dashboard/proposal.md:9-12
    - openspec/changes/phase-2-7-operator-dashboard/design.md:23-25
    - openspec/changes/phase-2-7-operator-dashboard/tasks.md:12
  - Actual SRE Command Center implementation is Express + ws in artifacts/api-server, and frontend is Vite mockup-sandbox.
    - fullstackapp/SRE-Command-Center/artifacts/api-server/src/index.ts:5,22
    - fullstackapp/SRE-Command-Center/artifacts/mockup-sandbox/package.json:7-10
- Testing stack contradiction:
  - Task asks for FastAPI TestClient endpoint unit tests.
    - openspec/changes/phase-2-7-operator-dashboard/tasks.md:44
  - Current backend is Node/Express and has no test script in api-server package.
    - fullstackapp/SRE-Command-Center/artifacts/api-server/package.json:6-11

### Ambiguities

- WebSocket endpoint contract is not path-documented in OpenAPI, only message schemas are defined.
  - fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:460-517
- Recovery acceptance says show "Reconnected" notification and reconcile missed events, but payload protocol defines sequence/resync semantics without explicit replay API or catch-up endpoint.
  - openspec/changes/phase-2-7-operator-dashboard/specs/dashboard-mvp/spec.md:40-42
  - fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:469-473
  - fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:501
- Phase taxonomy mismatch:
  - Base operator-dashboard includes Observe/Assist/Autonomous/Predictive.
    - openspec/changes/autonomous-sre-agent/specs/operator-dashboard/spec.md:8
  - Current phases endpoint emits OBSERVE/ASSIST/AUTONOMOUS only.
    - fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/phases.ts:161-166

### Missing Acceptance Tests / Gaps

- No visible test files for API-server endpoint/WS behavior under SRE Command Center package.
  - fullstackapp/SRE-Command-Center/artifacts/api-server/package.json:6-11
- DASH-007 acceptance asks for endpoint unit tests, component tests, and E2E scenario; no explicit implementation artifacts located in current package tree.
  - openspec/changes/phase-2-7-operator-dashboard/tasks.md:42-46
- Performance acceptance criteria (200ms FCP, <=1s rendering at 50 incidents) lack explicit instrumentation method and reproducible benchmark harness in phase artifact set.
  - openspec/changes/phase-2-7-operator-dashboard/specs/dashboard-mvp/spec.md:13-20

## Decoupling Constraint Compliance (Hard Requirement)

Constraint source requires frontend to consume only Node.js backend and avoid direct SRE-Agent internal coupling.

- .copilot-tracking/research/2026-05-31/mockup-sandbox-to-operator-dashboard-research.md:4
- .copilot-tracking/research/2026-05-31/mockup-sandbox-to-operator-dashboard-research.md:96-98

Implication for implementation recommendations:

- Frontend data layer must bind to fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml contracts and /api routes only.
- No direct calls from dashboard UI to src/sre_agent/* services or internals.
- Use contract-generated client types from lib/api-zod/lib/api-spec and WS message schemas for realtime.

## Recommended Requirement Clarifications Before Build Execution

1. Confirm canonical backend for phase 2.7 in this repo context: FastAPI (proposal text) or Express api-server (existing implementation reality).
2. Replace FastAPI TestClient requirement with Node/Express testing equivalent for this workspace, or split spec by implementation target.
3. Add explicit WS path and handshake/reconnect contract documentation in OpenAPI (or companion async spec).
4. Define objective measurement method for FCP and 50-incident responsiveness acceptance.
5. Resolve phase naming consistency across specs and UI labels (AUTONOMOUS vs AUTOMATE vs PREDICTIVE presence).
6. Clarify whether kill-switch metadata (timestamp, actor, reason) is in MVP scope for phase 2.7 since base spec requires it.

## Research Status

Complete for requested phase-2-7 requirement extraction and implementation mapping scope.
