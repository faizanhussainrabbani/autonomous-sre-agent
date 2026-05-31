---
title: Dashboard Backend Surface Research
description: Research notes on the SRE Command Center backend surface, generated clients, server runtime, dashboard mockup data needs, and Python API coverage.
ms.date: 2026-05-31
---

## Research Topics

* Confirm the current generated API surface and naming conventions.
* Identify backend dependencies in the Express server and DB package.
* Determine runtime shape and build output support for a WebSocket-capable backend.
* Extract the data contract implied by the SRE dashboard mockups.
* Map existing Python SRE Agent routes and persistence adapters to dashboard needs.
* Decide whether the dashboard should consume Python APIs, the Express backend, or both.

## Findings

* The generated OpenAPI surface is currently only a health check. lib/api-spec/openapi.yaml defines one server base path (/api), one tag, and one operation: GET /healthz with operationId healthCheck. The generated Zod and React clients mirror that single endpoint only.
* Naming is conventionally operation-driven. The generated React client exposes getHealthCheckUrl, healthCheck, getHealthCheckQueryKey, getHealthCheckQueryOptions, and useHealthCheck, with the response type named HealthStatus. The OpenAPI info.title is Api, and the spec comment explicitly warns not to change it because import paths would break.
* The DB package already includes drizzle-zod and drizzle-orm plus pg and zod. The api-server package depends on express, cors, cookie-parser, pino, and pino-http. Neither lib/db/package.json nor artifacts/api-server/package.json declares ws or @types/ws as a direct dependency.
* The Express server is a thin HTTP wrapper, not a WebSocket-capable runtime today. artifacts/api-server/src/index.ts imports app from ./app and calls app.listen(port). artifacts/api-server/src/app.ts mounts /api routes, and the build script only bundles src/index.ts into dist/index.mjs. There is no current HTTP server wrapper abstraction or ws entry point.
* The mockup dashboard expects a much richer dataset than the current Express API exposes. Dashboard.tsx renders global SRE KPIs, a live incident feed, remediation history, safety guardrails, provider health, and lock status. IncidentDetail.tsx needs incident identity, service, affected resources, environment, phase progression, diagnostic trace steps, proposed remediation, approval countdown, confidence breakdown, and event timeline data. AgentStatus.tsx needs autonomy phase progression, accuracy metrics, LLM performance, replica health, coordination health, telemetry provider ingest/error stats, and recent autonomous decision history.
* The Python SRE Agent backend already exposes meaningful operational APIs and backing persistence surfaces. src/sre_agent/api/main.py mounts health, healthz, metrics, /api/v1/status, /api/v1/system/halt, and /api/v1/system/resume, and conditionally includes the diagnose, severity override, and events routers. Persistence adapters already cover incident events and projections, diagnosis results, remediation actions, reasoning traces, coordination audit, and event outbox/relay flows.
* The strongest current backend source for dashboard data is the Python SRE Agent API and its Postgres-backed stores, not the Express backend. The Express backend currently behaves like a health-check scaffold with the minimum generated client surface; the Python app contains the actual incident/diagnosis/event/coordination state the mockups are asking for.

## Evidence

* lib/api-spec/openapi.yaml: one path only, GET /healthz, with info.title Api and a comment warning title changes will break imports.
* lib/api-zod/src/generated/api.ts and lib/api-client-react/src/generated/api.ts: only HealthCheckResponse / useHealthCheck-style exports are generated.
* lib/db/package.json: dependencies include drizzle-orm, drizzle-zod, pg, zod; no direct ws or @types/ws.
* artifacts/api-server/package.json: dependencies include express, cors, cookie-parser, pino, pino-http, and workspace packages; no direct ws or @types/ws.
* artifacts/api-server/src/app.ts and src/index.ts: Express app is created and listened to directly; no separate HTTP server wrapper.
* artifacts/api-server/build.mjs: bundles only src/index.ts to dist/index.mjs.
* artifacts/mockup-sandbox/src/components/mockups/sre-dashboard/Dashboard.tsx: KPIs, incident feed, remediation table, guardrails, provider health, lock status.
* artifacts/mockup-sandbox/src/components/mockups/sre-dashboard/IncidentDetail.tsx: incident summary, diagnostic trace, remediation plan, approval panel, confidence gauge, event timeline.
* artifacts/mockup-sandbox/src/components/mockups/sre-dashboard/AgentStatus.tsx: autonomy gates, diagnostic accuracy, LLM performance, agent coordination, telemetry provider health, recent decisions.
* src/sre_agent/api/main.py: FastAPI app includes /health, /healthz, /metrics, /api/v1/status, /api/v1/system/halt, /api/v1/system/resume, and conditionally includes diagnose/events/severity override routers.
* src/sre_agent/api/rest/diagnose_router.py: POST /api/v1/diagnose, POST /api/v1/diagnose/ingest, plus persistence writes into incident_events and diagnosis_results when available.
* src/sre_agent/api/rest/events_router.py: POST /api/v1/events/aws and GET /api/v1/events/aws/recent.
* src/sre_agent/api/rest/severity_override_router.py: POST/GET/DELETE /api/v1/incidents/{alert_id}/severity-override.
* src/sre_agent/adapters/persistence/incident_store.py, diagnosis_store.py, remediation_store.py, event_store.py, reasoning_trace_store.py, coordination_store.py: Postgres-backed read/write adapters for the incident, diagnosis, remediation, event, trace, and coordination domains.

## Open Questions

* Whether the dashboard will eventually be fronted by the Express service as a BFF is still undecided, but nothing in the current code suggests it is already doing that work.
* No dashboard-specific incident list, lock list, agent health, or websocket/subscription endpoint exists yet; those would need to be added either to the Python API or to a new Express aggregation layer.
