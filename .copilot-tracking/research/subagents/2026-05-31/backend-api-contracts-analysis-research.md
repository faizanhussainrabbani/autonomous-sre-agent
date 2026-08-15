<!-- markdownlint-disable-file -->

## Research Scope

- Topic: Node.js backend endpoint contracts for fullstackapp/SRE-Command-Center/lib, including OpenAPI and implementation surface required by frontend.
- Constraint: Frontend integration model must target Node.js backend API only.

## Research Status

- Status: Complete
- Date: 2026-05-31
- Backend target: Node.js API server under fullstackapp/SRE-Command-Center/artifacts/api-server with contracts sourced from fullstackapp/SRE-Command-Center/lib

## Research Questions

- What endpoints are required for an operator dashboard, and what are exact request/response contracts?
- How do OpenAPI contracts compare to actual Node.js route behavior?
- What validation, auth, CORS, and error schema behavior is implemented?
- What pagination, filtering, polling, or realtime mechanisms are available?
- What API stability and compatibility gaps exist for frontend integration?
- What typed client generation, caching, retry, and error-boundary implications should frontend adopt?

## Findings (In Progress)

- Pending detailed extraction from OpenAPI, api-server routes/handlers, and shared generated clients/schemas.

## Findings

### 1) Implemented endpoint surface required by operator dashboard

Runtime base path:

- OpenAPI server URL is /api: fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:8
- Express mounts API router at /api: fullstackapp/SRE-Command-Center/artifacts/api-server/src/app.ts:109

REST endpoints documented and implemented:

1. GET /api/healthz
- Spec operation: healthCheck (fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:20)
- Handler: returns {"status":"ok"} validated by zod (fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/health.ts:6)
- Response schema: HealthStatus with required status string (fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:143)

2. GET /api/v1/incidents
- Spec operation: listIncidents (fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:33)
- Query params in spec: limit (1..200 default 50), offset (min 0 default 0), status string (fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:38)
- Runtime validation/coercion: ListIncidentsQueryParams uses zod.coerce and same defaults/bounds (fullstackapp/SRE-Command-Center/lib/api-zod/src/generated/api.ts:32)
- Handler behavior: status equality filter if provided, otherwise no filter; sort by openedAt desc; offset pagination (fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/incidents.ts:154)
- Response shape: items,total,limit,offset (fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/incidents.ts:175)

3. GET /api/v1/incidents/:id
- Spec operation: getIncidentById with uuid path parameter and 404 ErrorResponse (fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:64)
- Runtime validation: GetIncidentByIdParams.parse(req.params) enforces uuid (fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/incidents.ts:184)
- Response shape built from incident + latestDiagnosis + remediationActions, then validated (fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/incidents.ts:226)
- Not found response shape: { code: "not_found", message: "Incident <id> not found" } (fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/response-helpers.ts:24)

4. GET /api/v1/incidents/:id/timeline
- Spec operation: getIncidentTimeline with 404 ErrorResponse (fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:85)
- Runtime validation: GetIncidentTimelineParams.parse(req.params) uuid (fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/incidents.ts:244)
- Ordered timeline events ascending by occurredAt then eventId (fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/incidents.ts:257)
- Payload mapped from payloadJson to payload and validated (fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/incidents.ts:263)

5. GET /api/v1/phases/status
- Spec operation: getPhaseStatus (fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:106)
- Runtime computes rollout criteria over a 7-day window and derives phase OBSERVE/ASSIST/AUTONOMOUS (fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/phases.ts:35)
- Response is validated by GetPhaseStatusResponse zod schema (fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/phases.ts:168)

6. GET /api/v1/accuracy/summary
- Spec operation: getAccuracySummary (fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:119)
- Runtime uses mixed windows: 7-day diagnostic and 24-hour operational metrics (fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/accuracy.ts:23)
- Response validated by GetAccuracySummaryResponse (fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/accuracy.ts:85)

Non-REST but frontend-relevant endpoint:

7. WebSocket /api/ws/incidents
- Implemented via ws server path /api/ws/incidents (fullstackapp/SRE-Command-Center/artifacts/api-server/src/ws/incidents.ts:14)
- Runtime started at server bootstrap (fullstackapp/SRE-Command-Center/artifacts/api-server/src/index.ts:22)
- Message shapes: initial_state and incident_update (fullstackapp/SRE-Command-Center/artifacts/api-server/src/ws/incidents.ts:20)
- Polling-based change detection with default 750ms and minimum 250ms via env var validation (fullstackapp/SRE-Command-Center/artifacts/api-server/src/ws/incidents.ts:95)

### 2) Validation, auth, CORS, and error contracts

Validation:

- All route responses pass through zod validation using sendValidated (fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/response-helpers.ts:7)
- Query/path validation is zod parse on request inputs, but thrown parse errors are not mapped to 400/422 (fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/incidents.ts:155)

Auth:

- No server-side auth middleware or security guard in API server route/app surface; routes are mounted directly (fullstackapp/SRE-Command-Center/artifacts/api-server/src/app.ts:109)
- OpenAPI spec has no securitySchemes or operation security requirements in current file (fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:1)

CORS:

- Allowed origins from CORS_ORIGIN env var, comma-separated (fullstackapp/SRE-Command-Center/artifacts/api-server/src/app.ts:13)
- Dev fallback allows http://localhost:3000 and http://localhost:5173 (fullstackapp/SRE-Command-Center/artifacts/api-server/src/app.ts:21)
- credentials: true is enabled (fullstackapp/SRE-Command-Center/artifacts/api-server/src/app.ts:105)
- Runtime probe: allowed origin receives Access-Control-Allow-Origin; disallowed origin omits it (curl verification on localhost:8081)

Error schemas:

- OpenAPI defines ErrorResponse as {code,message} (fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:150)
- 404 for incident detail/timeline follows ErrorResponse contract via sendNotFound (fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/response-helpers.ts:24)
- Global unhandled error response is {"error":"Internal server error"}, which does not match ErrorResponse (fullstackapp/SRE-Command-Center/artifacts/api-server/src/middlewares/error-handler.ts:11)

### 3) OpenAPI vs runtime consistency checks

Verified live behavior against localhost:8081 Node backend:

- GET /api/healthz -> 200, body {"status":"ok"} (matches spec)
- GET /api/v1/incidents?limit=2&offset=0 -> 200, body contains items,total,limit,offset (matches spec)
- GET /api/v1/incidents/00000000-0000-0000-0000-000000000000 -> 404 with {code,message} (matches documented 404 ErrorResponse)
- GET /api/v1/incidents/not-a-uuid -> 500 with {"error":"Internal server error"} (spec gap: no 500 documented; validation error not mapped)
- GET /api/v1/incidents?limit=0 -> 500 with {"error":"Internal server error"} (spec gap: invalid query becomes 500, not client error)

Consistency conclusions:

- Core happy-path REST contracts are consistent between OpenAPI and handlers.
- Invalid input behavior is inconsistent with common API expectations and current ErrorResponse schema.
- WebSocket contract exists in schema components and implementation, but is not published in OpenAPI paths, so generated clients cannot consume it from spec alone.

### 4) Pagination, filtering, polling/realtime capabilities

Pagination/filtering (incidents list):

- Offset-based pagination only: limit + offset (fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:38)
- Filter: single status string equality, no sort/filter operators (fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/incidents.ts:156)
- Database status/severity are free-text columns, not enum-constrained in schema, increasing risk of inconsistent values (fullstackapp/SRE-Command-Center/lib/db/src/schema/index.ts:18)

Realtime/polling:

- WebSocket uses server-side polling of DB snapshots and emits only changed incidents by version comparison (fullstackapp/SRE-Command-Center/artifacts/api-server/src/ws/incidents.ts:212)
- Initial snapshot capped at 200 incidents (MAX_SNAPSHOT_SIZE) and includes pollIntervalMs guidance (fullstackapp/SRE-Command-Center/artifacts/api-server/src/ws/incidents.ts:16)
- Sequence + resyncToken semantics are documented in schemas for reconnect handling (fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:466)

### 5) API stability and compatibility gaps

High-impact gaps:

1. Validation failures currently bubble to 500 with non-spec error shape
- Evidence: zod parse at route entrypoints plus generic 500 middleware payload (fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/incidents.ts:155, fullstackapp/SRE-Command-Center/artifacts/api-server/src/middlewares/error-handler.ts:11)
- Frontend impact: invalid filter/id can be mistaken for server outage; typed ErrorResponse assumptions break.

2. WebSocket contract is implemented but not path-documented in OpenAPI
- Evidence: ws path in implementation only (fullstackapp/SRE-Command-Center/artifacts/api-server/src/ws/incidents.ts:14) while openapi paths omit any ws endpoint (fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:17)
- Frontend impact: no generated SDK/hook for realtime channel from current codegen path.

3. Global error shape divergence
- Evidence: 404 uses {code,message}; 500 uses {error} (fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/response-helpers.ts:24, fullstackapp/SRE-Command-Center/artifacts/api-server/src/middlewares/error-handler.ts:11)
- Frontend impact: shared error parsing must support both shapes or normalize centrally.

4. Status filter semantics are underspecified
- Evidence: status is plain string in OpenAPI + DB text column + equality filter only (fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:52, fullstackapp/SRE-Command-Center/lib/db/src/schema/index.ts:19, fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/incidents.ts:156)
- Frontend impact: cannot safely build enum-driven filter UX without runtime/metadata guardrails.

5. No explicit API versioning policy beyond /v1 path prefix
- Evidence: endpoints are under /v1 but no deprecation/sunset metadata in spec (fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:31)
- Frontend impact: upgrades require conservative compatibility assumptions.

### 6) Frontend integration implications (Node.js backend API only)

Typed client generation and usage model:

- OpenAPI is source of truth for generated React Query hooks and TypeScript schemas via Orval (fullstackapp/SRE-Command-Center/lib/api-spec/orval.config.ts:16)
- codegen pipeline: orval + typecheck:libs (fullstackapp/SRE-Command-Center/lib/api-spec/package.json:6)
- Generated hooks include query keys and enabled guards for id-based routes (fullstackapp/SRE-Command-Center/lib/api-client-react/src/generated/api.ts:231)

Important type nuance:

- api-zod responses coerce dates to Date objects (fullstackapp/SRE-Command-Center/lib/api-zod/src/generated/api.ts:56)
- api-client-react generated interfaces model timestamps as string (fullstackapp/SRE-Command-Center/lib/api-client-react/src/generated/api.schemas.ts:23)
- Recommendation: frontend should standardize on API client schema layer for transport types, then normalize date parsing in one adapter to avoid mixed Date/string assumptions.

Caching strategy implications:

- Query keys are deterministic and parameterized (fullstackapp/SRE-Command-Center/lib/api-client-react/src/generated/api.ts:153)
- For operator dashboard:
	- incidents list should be frequently refetched and/or websocket-patched
	- incident detail/timeline should invalidate on incident_update for same incidentId
	- phase/accuracy summary can use periodic polling with lower cadence

Retries and error boundary implications:

- customFetch throws ApiError with parsed error payload (fullstackapp/SRE-Command-Center/lib/api-client-react/src/custom-fetch.ts:174)
- ResponseParseError is thrown for malformed JSON in expected JSON flow (fullstackapp/SRE-Command-Center/lib/api-client-react/src/custom-fetch.ts:202)
- Because runtime can return both {code,message} and {error}, frontend error boundaries should normalize by checking ApiError.data fields and fallback to HTTP status text/message builder logic.
- Avoid aggressive retries on 4xx-like validation cases until backend maps zod issues to 400; currently these surface as 500 and can trigger noisy retry loops.

Auth integration implications:

- Server does not enforce auth today, but client mutator supports optional bearer token injection with setAuthTokenGetter for mobile/non-cookie contexts (fullstackapp/SRE-Command-Center/lib/api-client-react/src/custom-fetch.ts:43)
- Web frontend should generally rely on cookies/session if added later; custom-fetch comments explicitly caution against unnecessary bearer usage in browser contexts (fullstackapp/SRE-Command-Center/lib/api-client-react/src/custom-fetch.ts:40)

### 7) Exact contract reference index for key operator dashboard endpoints

1. GET /api/v1/incidents
- Request query contract: fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:37
- Runtime parser/defaults: fullstackapp/SRE-Command-Center/lib/api-zod/src/generated/api.ts:32
- Response contract: fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:214
- Runtime implementation: fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/incidents.ts:154

2. GET /api/v1/incidents/:id
- Path uuid contract: fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:135
- Response schema: fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:321
- Runtime implementation: fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/incidents.ts:183

3. GET /api/v1/incidents/:id/timeline
- Response schema: fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:377
- Runtime implementation: fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/incidents.ts:243

4. GET /api/v1/phases/status
- Response schema: fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:412
- Runtime implementation: fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/phases.ts:35

5. GET /api/v1/accuracy/summary
- Response schema: fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:428
- Runtime implementation: fullstackapp/SRE-Command-Center/artifacts/api-server/src/routes/accuracy.ts:23

6. WebSocket /api/ws/incidents (implementation only; not in openapi paths)
- Runtime path and message contracts: fullstackapp/SRE-Command-Center/artifacts/api-server/src/ws/incidents.ts:14
- Related schema components in openapi: fullstackapp/SRE-Command-Center/lib/api-spec/openapi.yaml:460

## Clarifying Questions Not Answerable from Current Research

- Should invalid query/path validation return 400 with a structured validation error schema, or is current 500 behavior intentional during early-stage backend hardening?
- Should websocket transport be promoted into a formal documented contract (OpenAPI extension/AsyncAPI) to enable generated realtime client support?
- Should incident status/severity/filter dimensions be enum-governed for stable dashboard UX and analytics consistency?

## Recommended Next Research (Not Completed Here)

- Compare this Node backend contract with any existing frontend consumption points in fullstackapp/SRE-Command-Center apps to identify drift in real usage patterns.
- Capture actual production-like payload exemplars for each endpoint to validate nullable/optional field assumptions at UI rendering boundaries.
- Evaluate introducing a unified Problem Details style error contract and measure generated client impact.
- Assess AsyncAPI or equivalent contract source for websocket channel and integrate codegen feasibility.
