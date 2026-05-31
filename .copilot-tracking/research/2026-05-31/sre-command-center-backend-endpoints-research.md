<!-- markdownlint-disable-file -->
# Task Research: SRE Command Center Backend — Operator Dashboard Endpoints

Research covering what endpoints the TypeScript/Express `fullstackapp/SRE-Command-Center` backend
must implement to support the Operator Dashboard MVP defined in `openspec/changes/phase-2-7-operator-dashboard`.

## Scope Correction

The openspec change set targets the Python SRE Agent API surface, while the code under
`fullstackapp/SRE-Command-Center/artifacts/api-server` is a separate Express backend that
currently exposes only a health check. The research below treats the Express service as a
read-only dashboard backend / BFF candidate that can read the shared PostgreSQL schema,
while also documenting the Python SRE Agent endpoints that already exist and the gaps that
the dashboard still needs.

## Task Implementation Requests

* Implement all REST endpoints in `artifacts/api-server` required by the dashboard (DASH-001.1–1.5)
* Implement WebSocket endpoint for real-time incident event stream (DASH-001.6)
* Wire Drizzle ORM schema for the tables that power dashboard queries
* Update `lib/api-spec/openapi.yaml` and regenerate Zod/React-Query artifacts
* Add route files under `artifacts/api-server/src/routes/`
* Maintain contract compatibility with the Python SRE Agent persistence layer (shared PostgreSQL DB)

## Scope and Success Criteria

* Scope: `fullstackapp/SRE-Command-Center` TypeScript Express server and `lib/` shared packages; `openspec/changes/phase-2-7-operator-dashboard`; `src/sre_agent/` Python domain/persistence read-only (data source mapping)
* Assumptions:
  * The Express backend reads from the same PostgreSQL database written by the Python SRE Agent
  * The Express server does NOT call the Python FastAPI server — it queries the DB directly via Drizzle ORM
  * No authentication/RBAC in this phase (deferred per design doc)
  * WebSocket transport over native Node.js `ws` library (not Socket.IO)
* Success Criteria:
  * All 6 DASH-001 tasks have a corresponding route in `artifacts/api-server/src/routes/`
  * `lib/api-spec/openapi.yaml` updated with all endpoint definitions
  * `lib/db/src/schema/index.ts` has Drizzle table definitions matching migration 001 schema
  * Zod validators (`lib/api-zod`) and React-Query hooks (`lib/api-client-react`) regenerated via Orval
  * Response shapes match what the mockup dashboard components consume
  * All new routes validated with Zod before sending responses
  * TypeScript strict mode compiles without errors

## Evidence Summary

### Express Backend Surface Today

  * `artifacts/api-server/src/index.ts` calls `app.listen(...)` directly; there is no raw `http.Server` wrapper for WebSocket attachment.
  * `artifacts/api-server/src/app.ts` exports the Express app only and mounts `/api` routes plus the global error handler.
  * `artifacts/api-server/src/routes/index.ts` only mounts the health router.
  * `artifacts/api-server/src/routes/health.ts` is the only implemented route: `GET /api/healthz`.
  * `lib/api-spec/openapi.yaml` still defines only `GET /healthz` and `HealthStatus`.
  * `lib/api-zod` and `lib/api-client-react` are still generated from that health-only contract.

### Shared Schema and Dependency Evidence

  * `lib/db/package.json` already includes `drizzle-orm`, `drizzle-zod`, `pg`, and `zod`; no extra ORM dependency is needed for schema typing.
  * `artifacts/api-server/package.json` does not include `ws` or `@types/ws`, so WebSocket support is not yet installed.
  * `lib/db/src/schema/index.ts` remains a scaffold only; dashboard queries have no typed table definitions yet.

## Outline

1. Architecture Mapping — Python → Express → Frontend data flow
2. Database Schema Alignment — migration 001 tables → Drizzle definitions
3. Endpoint Specifications — each DASH-001 endpoint with precise request/response shapes
4. WebSocket Architecture — connection lifecycle, event types, reconnect protocol
5. OpenAPI Spec Design — complete YAML additions for all endpoints
6. Route File Structure — recommended file layout for `artifacts/api-server/src/routes/`
7. Dependencies — additional npm packages needed
8. Accuracy/Phase Endpoint Strategy — where these metrics come from

---

## Research Executed

### File Analysis

* fullstackapp/SRE-Command-Center/artifacts/api-server/src/app.ts
  * Express 5 app; uses pino-http, cors, JSON body-parser; mounts router at `/api`
  * CORS: dev defaults localhost:3000, localhost:5173; prod controlled by `CORS_ORIGIN` env
  * Global error handler registered last (correct)
  * `cookie-parser` listed in package.json but NOT registered (dead dependency)

* fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/index.ts
  * Only `healthRouter` mounted — no other routers

* fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/health.ts
  * Single `GET /healthz` that returns `{ status: "ok" }` validated through Zod

* fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml
  * OpenAPI 3.1.0; single path `GET /healthz`; single schema `HealthStatus { status: string }`
  * Server base: `/api`

* fullstackapp/SRE-Command-Center/lib/api-zod/src/generated/api.ts
  * Generated by Orval v8.5.3; exports `HealthCheckResponse` Zod schema only

* fullstackapp/SRE-Command-Center/lib/db/src/schema/index.ts
  * COMPLETELY EMPTY — only scaffold comments, no Drizzle table definitions

* fullstackapp/SRE-Command-Center/lib/db/src/index.ts
  * `drizzle(pool, { schema })` wired with node-postgres Pool; requires `DATABASE_URL`

* fullstackapp/SRE-Command-Center/artifacts/api-server/package.json
  * Dependencies: `@workspace/api-zod`, `@workspace/db`, `cors`, `express ^5.2.1`, `pino`, `pino-http`
  * Dev: `tsx`, `esbuild`, types
  * No `ws` (WebSocket) library present — must be added

### Code Search Results

* Python persistence tables (migration 001):
  * `incidents` — projection table: `incident_id`, `service`, `severity`, `status`, `opened_at`, `updated_at`, `closed_at`, `latest_event_id`, `provider`, `compute_mechanism`, `resource_id`, `version`
  * `incident_events` — append-only event log: `event_id`, `incident_id`, `event_type`, `occurred_at`, `provider`, `compute_mechanism`, `resource_id`, `payload_json`, `idempotency_key`, `correlation_key`
  * `diagnosis_results` — `diagnosis_id`, `incident_id`, `diagnosis_summary`, `confidence_score`, `evidence_refs` (JSONB), `generated_at`, `model_name`
  * `remediation_actions` — `action_id`, `incident_id`, `action_type`, `action_status`, `approval_mode`, `requested_at`, `started_at`, `completed_at`, `rollback_action_id`, `execution_result` (JSONB)
  * `event_outbox` — transactional outbox (internal, not needed by dashboard)
  * `coordination_audit` — lock/cooldown audit trail (from migration 003)
  * `agent_runs`, `tool_calls`, `retrieved_contexts` — trace tables added by migration 006 for reasoning visibility
  * `metric_baselines` — rolling telemetry aggregate with `avg_value` and `p95_value` only; no accuracy or resolution metrics
  * `incident_events_partitioned` / legacy cutover trigger path — migration 007/010 introduces a partitioned mirror and then promotes it to canonical `incident_events`

* Python FastAPI existing endpoints:
  * `GET  /health`                                     — liveness (always 200)
  * `GET  /healthz`                                    — deep readiness (checks vector/embedding/LLM)
  * `GET  /metrics`                                    — Prometheus text exposition
  * `GET  /api/v1/status`                              — agent version, phase, halt state, uptime
  * `POST /api/v1/system/halt`                         — kill switch (soft/hard)
  * `POST /api/v1/system/resume`                       — resume after halt (dual-approver)
  * `POST /api/v1/diagnose`                            — trigger RAG pipeline
  * `POST /api/v1/diagnose/ingest`                     — ingest runbook into vector DB
  * `POST /api/v1/events/aws`                          — receive AWS EventBridge events
  * `GET  /api/v1/events/aws/recent`                   — recent AWS events for correlation
  * `POST /api/v1/incidents/{alert_id}/severity-override`  — apply human severity override
  * `GET  /api/v1/incidents/{alert_id}/severity-override`  — get current override
  * `DELETE /api/v1/incidents/{alert_id}/severity-override` — revoke override

  * `GET  /api/v1/status` and `POST /api/v1/system/halt|resume` are already useful to a dashboard header/footer, but they are not yet exposed by the Express backend.

* Python domain models relevant to dashboard:
  * `IncidentPhase` enum: DETECTED, CLASSIFIED, DIAGNOSING, DIAGNOSED, VALIDATING, AUTHORIZING, REMEDIATING, VERIFYING, RESOLVED, ESCALATED, FAILED
  * `Severity` enum: SEV1, SEV2, SEV3, SEV4
  * `IncidentStatus` (persistence): open, investigating, mitigating, resolved, closed
  * `DiagnosticState`: PENDING, RETRIEVING, REASONING, VALIDATING, CLASSIFYING, COMPLETE, FAILED, ESCALATED, RETRIEVAL_MISS, FALLBACK_REASONING, ROOT_CAUSE_UNRESOLVED
  * `ConfidenceLevel` thresholds: BLOCK < 0.70, PROPOSE 0.70–0.85, AUTONOMOUS ≥ 0.85
  * `PhaseGate` graduation criteria: diagnostic_accuracy ≥ 0.90, destructive_fp = 0, sev34_autonomous_resolution ≥ 0.95, remediation_coverage ≥ 0.30, soak_days ≥ 7

  * `coordination_audit` columns from migration 003: `actor_type`, `actor_id`, `action`, `provider`, `compute_mechanism`, `resource_id`, `lock_priority`, `fencing_token`, `created_at`, `details_json`.
    This table is sufficient for a dashboard audit log or coordination timeline view.

* SRE-Command-Center mockup components:
  * Dashboard.tsx — KPI bar (MTTR 24h, auto-resolved count, pending approvals, accuracy 7D); live incident feed (severity, id, description, phase pipeline, confidence, elapsed time); recent remediation actions table
  * IncidentDetail.tsx — phase pipeline stepper; AI reasoning trace (timestamped steps from RAG pipeline); proposed remediation plan with approval/reject actions; blast radius
  * AgentStatus.tsx — graduation gate tracker with phase (OBSERVE/ASSIST/AUTONOMOUS) and per-criterion progress bars
  * These mockups also imply backend support for: latest diagnosis confidence, evidence citations, remediation status, lock/cooldown status, and operator-visible audit history.

### Project Conventions

* Standards referenced: Engineering Standards §6.1 (REST API Conventions), hexagonal architecture
* Express server uses contract-first approach: OpenAPI → Orval → Zod/React-Query
* All response bodies must pass through Zod `.parse()` before being sent (as health route demonstrates)
* Drizzle ORM for DB access — not raw SQL in routes

---

## Key Discoveries

### Architecture: Express Server as Database-Direct API Layer

The Express server connects directly to the PostgreSQL database that the Python SRE Agent writes to.
It does NOT proxy the Python FastAPI server. This means:

1. The Drizzle schema in `lib/db/src/schema/index.ts` must mirror the tables from `migration 001` (and subsequent migrations)
2. Query logic runs in the Express routes via Drizzle ORM
3. Read-only access for dashboard endpoints — the Python SRE Agent owns all writes
4. The Express server needs to know the same `DATABASE_URL` connection string

Architecture flow:
```
Python SRE Agent (FastAPI) ──writes──► PostgreSQL ◄──reads── Express Server ──► React Frontend
                                                                    ↑
                                              WebSocket (real-time incident updates)
```

### Architecture Decision Pressure: BFF vs Python Proxy

The repository currently suggests two possible endpoints owners:

1. The Python SRE Agent, which already owns operational endpoints and persistence writes.
2. The Express command-center server, which already depends on the shared DB package but exposes no dashboard data yet.

For the dashboard work in this repository, the least disruptive path is to make the Express service a
read-only dashboard BFF over the shared PostgreSQL schema. That avoids duplicating the Python API surface
and keeps the dashboard contract close to the frontend mockups.

The alternative is to consume the Python SRE Agent APIs directly and keep the Express app as a thin scaffold.
That is consistent with the current Python code, but it does not advance `fullstackapp/SRE-Command-Center`
as a backend product surface.

### Required Drizzle Schema Definitions

The `lib/db/src/schema/index.ts` must define read-only Drizzle table references that
mirror the Python-owned tables. The key tables for dashboard endpoints are:

```typescript
// incidents table (mutable projection)
export const incidentsTable = pgTable("incidents", {
  incident_id: uuid("incident_id").primaryKey(),
  service: text("service").notNull(),
  severity: text("severity").notNull(),
  status: text("status").notNull(),
  opened_at: timestamp("opened_at", { withTimezone: true }).notNull(),
  updated_at: timestamp("updated_at", { withTimezone: true }).notNull(),
  closed_at: timestamp("closed_at", { withTimezone: true }),
  latest_event_id: uuid("latest_event_id").notNull(),
  provider: text("provider").notNull(),
  compute_mechanism: text("compute_mechanism").notNull(),
  resource_id: text("resource_id").notNull(),
  version: integer("version").notNull().default(0),
});

// incident_events table (append-only)
export const incidentEventsTable = pgTable("incident_events", {
  event_id: uuid("event_id").primaryKey(),
  incident_id: uuid("incident_id").notNull(),
  event_type: text("event_type").notNull(),
  occurred_at: timestamp("occurred_at", { withTimezone: true }).notNull(),
  provider: text("provider").notNull(),
  compute_mechanism: text("compute_mechanism").notNull(),
  resource_id: text("resource_id").notNull(),
  payload_json: jsonb("payload_json").$type<Record<string, unknown>>().notNull(),
  correlation_key: text("correlation_key"),
  idempotency_key: text("idempotency_key").notNull(),
});

// diagnosis_results table
export const diagnosisResultsTable = pgTable("diagnosis_results", {
  diagnosis_id: uuid("diagnosis_id").primaryKey(),
  incident_id: uuid("incident_id").notNull(),
  diagnosis_summary: text("diagnosis_summary").notNull(),
  confidence_score: numeric("confidence_score", { precision: 5, scale: 4 }).notNull(),
  evidence_refs: jsonb("evidence_refs").$type<EvidenceRef[]>().notNull(),
  generated_at: timestamp("generated_at", { withTimezone: true }).notNull(),
  model_name: text("model_name").notNull(),
});

// remediation_actions table
export const remediationActionsTable = pgTable("remediation_actions", {
  action_id: uuid("action_id").primaryKey(),
  incident_id: uuid("incident_id").notNull(),
  action_type: text("action_type").notNull(),
  action_status: text("action_status").notNull(),
  approval_mode: text("approval_mode").notNull(),
  requested_at: timestamp("requested_at", { withTimezone: true }).notNull(),
  started_at: timestamp("started_at", { withTimezone: true }),
  completed_at: timestamp("completed_at", { withTimezone: true }),
  rollback_action_id: uuid("rollback_action_id"),
  execution_result: jsonb("execution_result").$type<Record<string, unknown>>(),
});
```

---

## Technical Scenarios

### Scenario 1: GET /incidents — Incident List with Pagination

**Requirements:**
* List active and recent incidents (DASH-001.1)
* Support pagination (cursor or offset)
* Dashboard KPI bar needs: count of active incidents, count auto-resolved today, count pending approvals
* Each incident card needs: service, severity, status, IncidentPhase (from event log), opened_at, elapsed time, latest confidence score

**Preferred Approach:**
Query the `incidents` projection table with a JOIN to `diagnosis_results` (latest by `generated_at DESC`) for confidence score.
IncidentPhase is derived from the latest `event_type` in `incident_events`.

```typescript
// routes/incidents.ts
router.get("/incidents", async (req, res) => {
  const { status, limit = 50, offset = 0 } = req.query;
  const rows = await db
    .select({
      incident_id: incidentsTable.incident_id,
      service: incidentsTable.service,
      severity: incidentsTable.severity,
      status: incidentsTable.status,
      opened_at: incidentsTable.opened_at,
      updated_at: incidentsTable.updated_at,
      provider: incidentsTable.provider,
      compute_mechanism: incidentsTable.compute_mechanism,
      resource_id: incidentsTable.resource_id,
    })
    .from(incidentsTable)
    .where(status ? eq(incidentsTable.status, status) : undefined)
    .orderBy(desc(incidentsTable.opened_at))
    .limit(Number(limit))
    .offset(Number(offset));
  res.json(IncidentListResponse.parse({ incidents: rows, total: rows.length }));
});
```

**Response shape:**
```json
{
  "incidents": [
    {
      "incident_id": "uuid",
      "service": "payments-service",
      "severity": "SEV1",
      "status": "investigating",
      "opened_at": "2026-05-31T10:00:00Z",
      "updated_at": "2026-05-31T10:04:17Z",
      "provider": "kubernetes",
      "compute_mechanism": "KUBERNETES",
      "resource_id": "deployment/payments-service",
      "latest_confidence": 0.914,
      "elapsed_seconds": 257
    }
  ],
  "total": 42,
  "offset": 0,
  "limit": 50
}
```

---

### Scenario 2: GET /incidents/:id — Incident Detail

**Requirements:**
* DASH-001.2 — Full detail with diagnosis and evidence
* Dashboard IncidentDetail.tsx needs: service, severity, incident phase pipeline, root cause hypothesis, confidence decomposition, evidence citations, proposed remediation

**Preferred Approach:**
Join `incidents` + latest `diagnosis_results` + all `remediation_actions` for this incident_id.
Parse `evidence_refs` JSONB to extract evidence citations.

```typescript
router.get("/incidents/:id", async (req, res) => {
  const incidentId = req.params.id;
  const incident = await db.query.incidentsTable.findFirst({
    where: eq(incidentsTable.incident_id, incidentId),
  });
  if (!incident) throw new HTTPError(404, "Incident not found");

  const diagnoses = await db.query.diagnosisResultsTable.findMany({
    where: eq(diagnosisResultsTable.incident_id, incidentId),
    orderBy: [desc(diagnosisResultsTable.generated_at)],
    limit: 1,
  });

  const actions = await db.query.remediationActionsTable.findMany({
    where: eq(remediationActionsTable.incident_id, incidentId),
    orderBy: [desc(remediationActionsTable.requested_at)],
  });

  res.json(IncidentDetailResponse.parse({ incident, diagnosis: diagnoses[0] ?? null, actions }));
});
```

---

### Scenario 3: GET /incidents/:id/timeline — Chronological Event Timeline

**Requirements:**
* DASH-001.3 — Ordered list of all events for an incident
* Timeline entries in IncidentDetail.tsx mockup: alert trigger, telemetry queries, RAG retrieval, hypotheses, remediation steps, post-action metrics
* Source: `incident_events` table ordered by `occurred_at ASC`, JSONB payload contains step details

**Preferred Approach:**
Direct query of `incident_events` by `incident_id` with ASC ordering.
Map `event_type` to a human-readable stage label for the frontend.

```typescript
router.get("/incidents/:id/timeline", async (req, res) => {
  const events = await db
    .select()
    .from(incidentEventsTable)
    .where(eq(incidentEventsTable.incident_id, req.params.id))
    .orderBy(asc(incidentEventsTable.occurred_at));

  const timeline = events.map((e) => ({
    event_id: e.event_id,
    event_type: e.event_type,
    occurred_at: e.occurred_at,
    payload: e.payload_json,
  }));

  res.json(IncidentTimelineResponse.parse({ incident_id: req.params.id, events: timeline }));
});
```

---

### Scenario 4: GET /phases/status — Phase and Graduation Gate Progress

**Requirements:**
* DASH-001.4 — Current operational phase and graduation criteria progress
* AgentStatus.tsx mockup shows: current phase (OBSERVE/ASSIST/AUTONOMOUS), per-criterion progress bars
* PhaseGate criteria: diagnostic_accuracy ≥ 0.90, destructive_fp = 0, sev34_resolution ≥ 0.95, remediation_coverage ≥ 0.30, soak_days ≥ 7

**Preferred Approach:**
Compute metrics from the database:
* `diagnostic_accuracy` — ratio of `diagnosis_results` where `confidence_score ≥ 0.70` to total, within last 7 days
* `sev34_autonomous_resolution_rate` — ratio of SEV3/SEV4 incidents reaching `resolved/closed` status autonomously
* `destructive_false_positives` — count of `remediation_actions` with `action_status = 'rolled_back'` and SEV1/SEV2 incidents (proxy)
* `remediation_coverage` — count of distinct `action_type` values / known total action types
* `soak_days` — days since last destructive false positive

For now (Phase 2.7), these can be computed with SQL aggregates. Phase 3+ can move to materialized views.

```typescript
router.get("/phases/status", async (_req, res) => {
  const [accuracyRow] = await db.execute(sql`
    SELECT
      COUNT(*) FILTER (WHERE confidence_score >= 0.70)::float / NULLIF(COUNT(*), 0) AS accuracy
    FROM diagnosis_results
    WHERE generated_at >= NOW() - INTERVAL '7 days'
  `);
  // ... additional queries ...
  res.json(PhaseStatusResponse.parse({ current_phase: "assist", criteria: [...] }));
});
```

---

### Scenario 5: GET /accuracy/summary — Aggregate Accuracy Metrics

**Requirements:**
* DASH-001.5 — Dashboard KPI bar: agent accuracy (7D), auto-resolved count, pending approvals, MTTR
* Source: aggregated from `incidents` and `diagnosis_results`

**Preferred Approach:**
Single SQL query with window functions or multiple CTEs to compute:
* `accuracy_7d` — diagnosis confidence rate in last 7 days
* `auto_resolved_24h` — incidents reaching `resolved` status in last 24h
* `pending_approvals` — `remediation_actions` in `planned` or `approved` status
* `mttr_seconds_24h` — average of `(closed_at - opened_at)` for incidents closed in last 24h

```json
{
  "accuracy_7d": 0.943,
  "auto_resolved_24h": 14,
  "pending_approvals": 2,
  "mttr_seconds_24h": 252
}
```

---

### Scenario 6: WebSocket /api/ws/incidents — Real-Time Incident Stream

**Requirements:**
* DASH-001.6 — Clients connect once; server pushes incident create/update events
* < 1 second update latency
* Dashboard reconnects automatically within 5 seconds on drop

**Architecture Decision: PostgreSQL LISTEN/NOTIFY vs Polling**

**Option A: PostgreSQL LISTEN/NOTIFY (Recommended)**
* Python SRE Agent fires `NOTIFY incident_events_channel, payload_json` after each INSERT to `incident_events`
* Express server maintains a dedicated `pg` client (not pool) subscribed via `LISTEN incident_events_channel`
* On NOTIFY, parse payload and broadcast to all connected WebSocket clients

Benefits:
* Zero polling overhead
* Sub-100ms notification latency after DB write
* No dependency on Redis or Kafka

Drawbacks:
* Requires the Python SRE Agent to add `pg_notify()` calls to migration trigger or application code
* Long-lived `pg` connection (manageable with reconnect logic)

**Option B: Polling the incidents table every 1s (Fallback)**
* Express server polls `SELECT * FROM incidents WHERE updated_at > $last_check` every 1 second
* Broadcasts changes to WebSocket clients

Benefits: No changes needed to Python SRE Agent
Drawbacks: 1s polling lag, higher DB load

**Selected approach: Start with Option B (polling) for Phase 2.7 MVP; migrate to LISTEN/NOTIFY in Phase 3**

Rationale: Option B can be implemented entirely within the Express server with no Python-side changes.
The 1s polling meets the DASH spec requirement of `< 1 second update delay` at MVP scale.

However, the Python SRE Agent currently emits no PostgreSQL `NOTIFY`/`pg_notify` calls at all, so LISTEN/NOTIFY is not available without net-new backend work.
If low-latency push is required later, that notification path must be added either in the Python persistence adapter or via a database trigger.

```typescript
// src/ws/incidents.ts
import { WebSocketServer } from "ws";
import type { IncomingMessage, Server } from "http";
import { db, incidentsTable } from "@workspace/db";
import { desc, gt } from "drizzle-orm";

export function attachIncidentsWebSocket(server: Server): void {
  const wss = new WebSocketServer({ server, path: "/api/ws/incidents" });
  let lastCheck = new Date();

  const broadcast = (data: unknown) => {
    const msg = JSON.stringify(data);
    wss.clients.forEach((client) => {
      if (client.readyState === client.OPEN) client.send(msg);
    });
  };

  // Poll for updates
  const interval = setInterval(async () => {
    if (wss.clients.size === 0) return; // Skip if no clients
    const now = new Date();
    const updated = await db.select().from(incidentsTable)
      .where(gt(incidentsTable.updated_at, lastCheck))
      .orderBy(desc(incidentsTable.updated_at));
    lastCheck = now;
    if (updated.length > 0) {
      broadcast({ type: "incidents_updated", incidents: updated, timestamp: now.toISOString() });
    }
  }, 1000);

  wss.on("close", () => clearInterval(interval));
  wss.on("connection", (ws) => {
    // Send current state on connect
    db.select().from(incidentsTable).orderBy(desc(incidentsTable.opened_at)).limit(50)
      .then((incidents) => {
        ws.send(JSON.stringify({ type: "initial_state", incidents, timestamp: new Date().toISOString() }));
      });
    ws.on("error", (err) => logger.error({ err }, "ws_client_error"));
  });
}
```

**Message Protocol:**
```typescript
// Client-bound messages
type ServerMessage =
  | { type: "initial_state"; incidents: Incident[]; timestamp: string }
  | { type: "incidents_updated"; incidents: Incident[]; timestamp: string }
  | { type: "ping"; timestamp: string };

// Server-bound messages (client → server)
type ClientMessage =
  | { type: "pong" }
  | { type: "subscribe"; filters?: { severity?: string; status?: string } };
```

---

## Complete Endpoint Table

| Method | Path | Handler File | DB Tables | DASH Task |
|---|---|---|---|---|
| `GET` | `/api/healthz` | `routes/health.ts` | — | existing |
| `GET` | `/api/v1/incidents` | `routes/incidents.ts` | `incidents`, `diagnosis_results` | DASH-001.1 |
| `GET` | `/api/v1/incidents/:id` | `routes/incidents.ts` | `incidents`, `diagnosis_results`, `remediation_actions` | DASH-001.2 |
| `GET` | `/api/v1/incidents/:id/timeline` | `routes/incidents.ts` | `incident_events` | DASH-001.3 |
| `GET` | `/api/v1/phases/status` | `routes/phases.ts` | `incidents`, `diagnosis_results`, `remediation_actions` | DASH-001.4 |
| `GET` | `/api/v1/accuracy/summary` | `routes/accuracy.ts` | `incidents`, `diagnosis_results`, `remediation_actions` | DASH-001.5 |
| `WS` | `/api/ws/incidents` | `ws/incidents.ts` | `incidents` (polled) | DASH-001.6 |

### Current Gap Summary

The Express backend has none of the above endpoints today. It only serves `GET /api/healthz`, so the entire dashboard surface remains to be built.
The Python SRE Agent already exposes several operational endpoints, but those are not wired into the command-center Express server.

---

## Required File Changes

### New Files

```text
artifacts/api-server/src/
  routes/
    incidents.ts         ← GET /v1/incidents, GET /v1/incidents/:id, GET /v1/incidents/:id/timeline
    phases.ts            ← GET /v1/phases/status
    accuracy.ts          ← GET /v1/accuracy/summary
  ws/
    incidents.ts         ← WebSocket /api/ws/incidents
  lib/
    http-error.ts        ← typed HTTPError helper for consistent 4xx handling
```

### Modified Files

```text
artifacts/api-server/src/
  routes/index.ts        ← add incidentsRouter, phasesRouter, accuracyRouter
  app.ts                 ← attach WebSocket server after httpServer creation (index.ts level)
  index.ts               ← create http.Server, then attach WebSocket before listen()

lib/db/src/
  schema/index.ts        ← define Drizzle table definitions for all 4 tables

lib/api-spec/
  openapi.yaml           ← add 5 new paths + 8+ new schemas

lib/api-zod/             ← regenerated by Orval (run codegen)
lib/api-client-react/    ← regenerated by Orval (run codegen)

artifacts/api-server/
  package.json           ← add `ws` and `@types/ws` dependencies
```

---

## Dependencies to Add

```json
{
  "dependencies": {
    "ws": "^8.18.0"
  },
  "devDependencies": {
    "@types/ws": "^8.5.14"
  }
}
```

Note: Express 5 does not upgrade to HTTP/2 natively. The `http.createServer(app)` pattern
is needed to pass the server to the WebSocket server constructor.

---

## OpenAPI Schema Additions (Summary)

New schemas to add to `lib/api-spec/openapi.yaml`:

```yaml
components:
  schemas:
    IncidentSummary:
      type: object
      required: [incident_id, service, severity, status, opened_at, updated_at, provider, compute_mechanism, resource_id]
      properties:
        incident_id: { type: string, format: uuid }
        service: { type: string }
        severity: { type: string, enum: [SEV1, SEV2, SEV3, SEV4] }
        status: { type: string, enum: [open, investigating, mitigating, resolved, closed] }
        opened_at: { type: string, format: date-time }
        updated_at: { type: string, format: date-time }
        closed_at: { type: string, format: date-time, nullable: true }
        provider: { type: string }
        compute_mechanism: { type: string }
        resource_id: { type: string }
        latest_confidence: { type: number, format: float, nullable: true }
        elapsed_seconds: { type: integer }

    IncidentListResponse:
      type: object
      required: [incidents, total, offset, limit]
      properties:
        incidents: { type: array, items: { $ref: "#/components/schemas/IncidentSummary" } }
        total: { type: integer }
        offset: { type: integer }
        limit: { type: integer }

    DiagnosisSummary:
      type: object
      properties:
        diagnosis_id: { type: string, format: uuid }
        diagnosis_summary: { type: string }
        confidence_score: { type: number }
        evidence_refs: { type: array, items: { type: object } }
        generated_at: { type: string, format: date-time }
        model_name: { type: string }

    RemediationAction:
      type: object
      properties:
        action_id: { type: string, format: uuid }
        action_type: { type: string }
        action_status: { type: string, enum: [planned, approved, running, completed, failed, rolled_back] }
        approval_mode: { type: string }
        requested_at: { type: string, format: date-time }
        started_at: { type: string, format: date-time, nullable: true }
        completed_at: { type: string, format: date-time, nullable: true }
        execution_result: { type: object, nullable: true }

    IncidentDetailResponse:
      type: object
      required: [incident]
      properties:
        incident: { $ref: "#/components/schemas/IncidentSummary" }
        diagnosis: { $ref: "#/components/schemas/DiagnosisSummary", nullable: true }
        actions: { type: array, items: { $ref: "#/components/schemas/RemediationAction" } }

    TimelineEvent:
      type: object
      required: [event_id, event_type, occurred_at]
      properties:
        event_id: { type: string, format: uuid }
        event_type: { type: string }
        occurred_at: { type: string, format: date-time }
        payload: { type: object }

    IncidentTimelineResponse:
      type: object
      required: [incident_id, events]
      properties:
        incident_id: { type: string, format: uuid }
        events: { type: array, items: { $ref: "#/components/schemas/TimelineEvent" } }

    GraduationCriterion:
      type: object
      required: [key, label, current_value, required_value, met]
      properties:
        key: { type: string }
        label: { type: string }
        current_value: { type: number }
        required_value: { type: number }
        met: { type: boolean }

    PhaseStatusResponse:
      type: object
      required: [current_phase, operational_phase, criteria]
      properties:
        current_phase: { type: string }
        operational_phase: { type: string, enum: [observe, assist, autonomous, predictive] }
        criteria: { type: array, items: { $ref: "#/components/schemas/GraduationCriterion" } }
        graduation_ready: { type: boolean }

    AccuracySummaryResponse:
      type: object
      required: [accuracy_7d, auto_resolved_24h, pending_approvals, mttr_seconds_24h]
      properties:
        accuracy_7d: { type: number, format: float }
        auto_resolved_24h: { type: integer }
        pending_approvals: { type: integer }
        mttr_seconds_24h: { type: number }
```

---

## Implementation Ordering (Critical Path)

The recommended implementation order follows the dependency chain and the DASH-001 critical path designation:

1. **Drizzle schema** (`lib/db/src/schema/index.ts`) — everything else depends on this
2. **OpenAPI spec additions** (`lib/api-spec/openapi.yaml`) — drives Zod and React-Query generation
3. **Orval codegen** (`pnpm --filter @workspace/api-spec run codegen`) — generates validators
4. **`GET /v1/incidents`** + **`GET /v1/incidents/:id`** — highest priority, feeds live feed view
5. **`GET /v1/incidents/:id/timeline`** — feeds incident detail drilldown
6. **`GET /v1/accuracy/summary`** — feeds KPI bar
7. **`GET /v1/phases/status`** — feeds graduation tracker
8. **WebSocket `/api/ws/incidents`** — real-time layer, built last (requires `ws` package + server refactor)

---

## Key Risks and Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Drizzle schema diverges from Python migrations | High | Keep schema definitions read-only (no `.default()` calls that generate DB-side defaults); pin schema to migration 001 table shapes |
| `numeric` Drizzle type returns string not number | Medium | Cast `confidence_score` with `.mapWith(Number)` or parse at Zod layer |
| WebSocket not supported by Express 5 directly | Medium | Attach `ws.WebSocketServer` to the raw `http.Server` instance, not the Express `app` |
| Python currently has no `pg_notify` flow | Medium | Add notification calls or DB triggers before relying on LISTEN/NOTIFY |
| `incident_events` table may have no partition on new deploys | Low | Routes query with proper `WHERE` on indexed columns (`incident_id`, `occurred_at`) |
| OpenAPI title must remain `"Api"` | Low | Orval config uses a titleTransformer that forces `"Api"` — do not change the yaml `info.title` |
| No auth on new endpoints | Low (accepted) | Documented as Phase 3 deferred item per design doc |

---

## Potential Next Research

* Confirm whether `metric_baselines` table (migration 009) has accuracy data suitable for `GET /accuracy/summary`
  * Reasoning: The continuous aggregate may already compute accuracy metrics
  * Reference: `src/sre_agent/adapters/persistence/migrations/009_metric_baselines_continuous_aggregate.sql`
* Confirm the `coordination_audit` table (migration 003) fields for potential audit log endpoint
  * Reasoning: AgentStatus.tsx mockup hints at lock/cooldown history display
  * Reference: `src/sre_agent/adapters/persistence/migrations/003_coordination_audit.sql`
* Research `drizzle-zod` integration for auto-generating insert/select schemas from table definitions
  * Reference: `lib/db/src/schema/index.ts` scaffold comment mentions `createInsertSchema` from drizzle-zod
* Investigate whether the Python SRE Agent already emits `pg_notify` calls after event writes
  * Reference: `src/sre_agent/adapters/persistence/incident_store.py` — check for pg_notify usage
