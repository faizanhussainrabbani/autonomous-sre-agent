# Phases 2.5 through 4.0 — Implementation Status Analysis

**Date:** 2026-05-30
**Scope:** openspec/changes phases 2.5 through 4.0 and integrate-alignment-report
**Method:** Full read of all proposal.md, design.md, tasks.md, and specs/ files for each phase.

---

## Research Questions

1. What specific features and tasks are defined in each phase?
2. Which tasks are checked (done) vs unchecked (pending)?
3. What design decisions are captured?

---

## Phase 2.5 — Slow Response Detection

### Purpose

Extends the existing latency spike detector with two new anomaly types: absolute-threshold-based `SLOW_RESPONSE` (no baseline required) and `TIMEOUT_PROXIMITY` for AWS Lambda. Adds deterministic arbitration so at most one alert fires per evaluation key. Delivered in two gates: 2.5A (K8s + AWS) ships first; 2.5B (Azure) is conditional on Azure adapter availability.

### Feature List

- Two new `AnomalyType` enum values: `SLOW_RESPONSE`, `TIMEOUT_PROXIMITY`
- Three new `DetectionConfig` fields: `slow_response_absolute_threshold_ms` (2000 ms default), `slow_response_duration_seconds` (60 s), `timeout_proximity_percent` (80%)
- `_detect_absolute_latency()` method — fires without established baseline
- `_detect_timeout_proximity()` method — serverless-only, graceful skip on missing metadata
- Candidate-rule arbitration: `TIMEOUT_PROXIMITY > SLOW_RESPONSE > LATENCY_SPIKE`, one alert max per evaluation key
- Cold-start suppression extended to cover timeout-proximity rule
- Per-service `slow_response_threshold_ms` override via `set_service_sensitivity()`
- ECS `ResponseTime` metric mapping to canonical `ecs_response_time_ms`
- Lambda `timeout_ms` metadata enrichment via `AWSResourceMetadataFetcher`
- Kubernetes `http_request_duration_p99` added to polling watchlist
- Azure App Service mapping `requests/duration` → `appservice_response_time_ms` (Phase 2.5B, conditional)
- Detection-to-alert latency SLO: <= 60 seconds
- Region-aware correlation safety (provider/region context preserved in alert payload)
- Prometheus counters and histograms for new rules (slow response fired, timeout proximity fired, fallback, dedup)
- E2E test covering K8s, Lambda cold-start, ECS deployment flag, SLO assertion

### Tasks (from tasks.md)

All tasks are unchecked — 0 done.

**Gate 0 — Preflight (~2 tasks)**
- [ ] 0.1 Confirm scope split in planning docs
- [ ] 0.2 Confirm Azure adapter dependency status

**Gate 1 — Core Domain Extensions (~4 tasks)**
- [ ] 1.1 Add `SLOW_RESPONSE` and `TIMEOUT_PROXIMITY` to `AnomalyType`
- [ ] 1.2 Extend `DetectionConfig` with three new fields
- [ ] 1.3 Wire config ingestion through settings and agent.yaml
- [ ] 1.4 Extend `set_service_sensitivity()` with `slow_response_threshold_ms`

**Gate 2 — Detector Rules and Arbitration (~4 tasks)**
- [ ] 2.1 Implement `_detect_absolute_latency()`
- [ ] 2.2 Implement `_detect_timeout_proximity()` with missing-metadata fallback
- [ ] 2.3 Refactor evaluation path to candidate-rule model with precedence arbitration
- [ ] 2.4 Apply cold-start suppression to timeout-proximity rule

**Gate 3 — Platform Metrics (~3 tasks)**
- [ ] 3.1 Add ECS `ResponseTime` → `ecs_response_time_ms` mapping
- [ ] 3.2 Enrich Lambda duration metrics with `timeout_ms` metadata
- [ ] 3.3 Add K8s p99 latency to polling watchlist

**Gate 4 — Observability (~2 tasks)**
- [ ] 4.1 Structured log events for new rules
- [ ] 4.2 Prometheus counters/histograms for new rules

**Gate 5 — Tests (~5 tasks)**
- [ ] 5.1 Unit tests: detection rules, arbitration, suppression, per-service override
- [ ] 5.2 Config defaults tests
- [ ] 5.3 CloudWatch metrics adapter unit tests (ECS mapping, Lambda enrichment)
- [ ] 5.4 Settings unit tests for new detection fields
- [ ] 5.5 E2E test covering all 2.5A scenarios and SLO assertion

**Gate 6 — Phase 2.5A Exit (~4 tasks)**
- [ ] 6.1 All Gate 1–5 tasks complete
- [ ] 6.2 New and existing tests pass
- [ ] 6.3 No regression in existing latency spike behavior
- [ ] 6.4 Coverage at or above threshold

**Gate 7 — Azure Extension / Phase 2.5B (~4 tasks, conditional)**
- [ ] 7.1 Implement/finalize `AzureMonitorMetricsAdapter`
- [ ] 7.2 Add `requests/duration` → `appservice_response_time_ms` mapping
- [ ] 7.3 Azure adapter unit tests
- [ ] 7.4 Azure scenario in slow-response E2E test

**Gate 8 — Documentation (~1 task)**
- [ ] 8.1 Update architecture docs for hybrid slow-response detection

**Summary:** ~29 tasks total, 0 done, 29 pending.

### Key Design Decisions

- Phased delivery (2.5A K8s/AWS required first; 2.5B Azure conditional on adapter availability)
- Single-alert arbitration per `(service, metric_name, timestamp)` with deterministic precedence order
- Absolute-threshold detection does NOT require established baseline (unlike sigma)
- Detector chooses anomaly type precedence only — does NOT assign incident severity
- Region-aware correlation: no `AlertCorrelationEngine` API change needed, but alert payloads must carry provider/region context

### Dependencies

- Phases prior to 2.5 complete (existing latency spike detection in place — confirmed)
- Phase 2.5B depends on `AzureMonitorMetricsAdapter` availability (currently blocked/unknown)

### Implementation Status

**Not started.** No source code changes detected. All 29 tasks remain unchecked.

---

## Phase 2.6 — Notification Integrations

### Purpose

Implements concrete `NotificationPort` and `EscalationPort` adapter classes for Slack, Teams, PagerDuty, and OpsGenie. Enables the Phase 2 Human-In-The-Loop approval workflow for Sev 1–2 incidents.

### Feature List

- `NotificationPort` ABC (`ports/notification.py`): `send_alert()`, `send_approval_request()`, `send_resolution_summary()`, `health_check()`
- `EscalationPort` ABC (`ports/escalation.py`): `create_incident()`, `update_incident()`, `resolve_incident()`, `health_check()`
- `NotificationMessage` and `EscalationPayload` domain models
- Slack adapter with Block Kit alerts, interactive Approve/Reject buttons, approval event dispatch to EventBus, circuit breaker
- Teams adapter with Adaptive Cards, webhook delivery, approval response handler
- PagerDuty adapter with Events API v2 (`trigger`, `resolve` with `dedup_key`), severity mapping, structured payload
- OpsGenie adapter with Alert API (create, update, resolve)
- Severity-based routing: Sev 1–2 → PagerDuty + Slack; Sev 3–4 → Slack only
- Fallback chain when primary channel fails
- `NotificationSettings` in config: channel config, routing rules, fallback order
- Adapter registration in `adapters/bootstrap.py`
- Unit, integration, and E2E tests including full HITL approval flow

### Tasks (from tasks.md)

All tasks are unchecked — 0 done.

**NOTIF-001 — Port Interfaces (~4 tasks)**
- [ ] 1.1 Create `NotificationPort` ABC
- [ ] 1.2 Create `EscalationPort` ABC
- [ ] 1.3 Define `NotificationMessage` domain model
- [ ] 1.4 Define `EscalationPayload` domain model

**NOTIF-002 — Slack Adapter (~7 tasks)**
- [ ] 2.1 Create `slack.py` implementing `NotificationPort`
- [ ] 2.2 Implement `send_alert()` with Block Kit
- [ ] 2.3 Implement `send_approval_request()` with interactive buttons
- [ ] 2.4 Implement button interaction handler (ack within 3s, dispatch event)
- [ ] 2.5 Implement `send_resolution_summary()`
- [ ] 2.6 Implement `health_check()`
- [ ] 2.7 Circuit breaker wrapping for Slack API calls

**NOTIF-003 — Teams Adapter (~4 tasks)**
- [ ] 3.1 Create `teams.py` implementing `NotificationPort`
- [ ] 3.2 Implement Adaptive Card templates
- [ ] 3.3 Implement webhook-based delivery
- [ ] 3.4 Implement approval/reject action handler

**NOTIF-004 — PagerDuty Adapter (~6 tasks)**
- [ ] 4.1 Create `pagerduty.py` implementing `EscalationPort`
- [ ] 4.2 Implement `create_incident()` via Events API v2 trigger
- [ ] 4.3 Structured payload with severity mapping and evidence links
- [ ] 4.4 Implement `update_incident()` with `dedup_key`
- [ ] 4.5 Implement `resolve_incident()`
- [ ] 4.6 Implement `health_check()`

**NOTIF-005 — OpsGenie Adapter (~3 tasks)**
- [ ] 5.1 Create `opsgenie.py` implementing `EscalationPort`
- [ ] 5.2 Implement create/update/resolve via OpsGenie Alert API
- [ ] 5.3 Severity mapping and diagnosis context

**NOTIF-006 — Configuration and Routing (~4 tasks)**
- [ ] 6.1 Add `NotificationSettings` to `config/settings.py`
- [ ] 6.2 Implement severity-based routing logic
- [ ] 6.3 Implement fallback chain
- [ ] 6.4 Register adapters in `adapters/bootstrap.py`

**NOTIF-007 — Testing (~4 tasks)**
- [ ] 7.1 Unit tests for all port interface methods
- [ ] 7.2 Integration tests for Slack adapter
- [ ] 7.3 Integration tests for PagerDuty adapter
- [ ] 7.4 E2E test: HITL approval flow end-to-end

**Summary:** 32 tasks total, 0 done, 32 pending.

### Key Design Decisions

- Slack Bolt SDK (not raw Web API) for interactive component handling
- PagerDuty Events API v2 (not REST API v2) — designed for automated integrations
- Approval state stored in EventStore as `DomainEvent` (Slack adapter does not own approval state)
- Microsoft Teams webhook may be deprecated; abstraction allows adapter swap

### Dependencies

- Phase 2 HITL approval flow infrastructure must be in place
- `slack-bolt`, `slack-sdk`, `pdpyras`, `opsgenie-sdk` as new dependencies

### Implementation Status

**Not started.** No source code changes detected. `ports/notification.py` and `ports/escalation.py` do not exist. 0/32 tasks done.

---

## Phase 2.7 — Operator Dashboard

### Purpose

Delivers a React/Next.js single-page application providing operators with real-time incident feed, confidence score visualization, incident timeline drill-down, and graduation gate progress tracking.

### Feature List

- FastAPI REST endpoints: `GET /api/v1/incidents`, `GET /api/v1/incidents/{id}`, `GET /api/v1/incidents/{id}/timeline`, `GET /api/v1/phases/status`, `GET /api/v1/accuracy/summary`
- WebSocket endpoint: `GET /api/ws/incidents` (real-time stream, < 1 s update delay)
- Next.js 15 SPA in `dashboard/` with TypeScript and Tailwind CSS
- Layout with sidebar navigation, header with phase indicator, kill-switch status badge
- WebSocket client with auto-reconnect and connection status indicator
- Incident list view: severity badge, stage indicator, confidence score, elapsed timer, real-time updates
- Severity-based filtering/sorting; incident detail modal with full diagnosis
- Confidence decomposition component (4 components, color-coded: green/yellow/red)
- Historical confidence trend chart (rolling average)
- Incident timeline with expandable entries: alert, queries, RAG docs, hypotheses, remediations, post-action metrics
- Phase status and graduation criteria checklist with progress bars (green met / red unmet)
- < 200 ms page load, mobile-responsive layout
- Unit tests (FastAPI TestClient), React component tests, E2E browser test

### Tasks (from tasks.md)

All tasks are unchecked — 0 done.

**DASH-001 — API Endpoints (~6 tasks)**
- [ ] 1.1 `GET /api/v1/incidents`
- [ ] 1.2 `GET /api/v1/incidents/{id}`
- [ ] 1.3 `GET /api/v1/incidents/{id}/timeline`
- [ ] 1.4 `GET /api/v1/phases/status`
- [ ] 1.5 `GET /api/v1/accuracy/summary`
- [ ] 1.6 `WebSocket /api/ws/incidents`

**DASH-002 — Dashboard Foundation (~4 tasks)**
- [ ] 2.1 Initialize Next.js 15 project in `dashboard/`
- [ ] 2.2 Configure Tailwind CSS
- [ ] 2.3 Create layout component
- [ ] 2.4 Implement WebSocket client with auto-reconnect

**DASH-003 — Incident Feed View (~4 tasks)**
- [ ] 3.1 Incident list component with real-time updates
- [ ] 3.2 Per-incident display fields
- [ ] 3.3 Severity-based filtering and sorting
- [ ] 3.4 Incident detail modal/page

**DASH-004 — Confidence Visualization (~3 tasks)**
- [ ] 4.1 Confidence decomposition component (4 components)
- [ ] 4.2 Color-code each component
- [ ] 4.3 Historical confidence trend chart

**DASH-005 — Incident Timeline (~3 tasks)**
- [ ] 5.1 Chronological timeline component
- [ ] 5.2 Timeline entry types
- [ ] 5.3 Evidence links to source docs

**DASH-006 — Phase and Graduation Tracker (~3 tasks)**
- [ ] 6.1 Phase status component
- [ ] 6.2 Graduation criteria checklist with progress bars
- [ ] 6.3 Color-code met/unmet criteria

**DASH-007 — Testing (~3 tasks)**
- [ ] 7.1 Unit tests for API endpoints
- [ ] 7.2 React component tests
- [ ] 7.3 E2E browser test

**Summary:** 26 tasks total, 0 done, 26 pending.

### Key Design Decisions

- Next.js 15 with App Router (SSR for page load performance, API route proxying)
- WebSocket over SSE/polling (bidirectional for future kill-switch activation from dashboard)
- Tailwind CSS for internal ops tool rapid prototyping
- Dashboard is a separate deployment unit from agent binary
- User auth/RBAC deferred to Phase 3

### Dependencies

- Phase 2.6 notification integrations (kill-switch status badge depends on HITL flow)
- Phase 2 Intelligence Layer complete (confidence scores, incident events available)
- `GET /api/v1/accuracy/summary` depends on accuracy tracking infrastructure

### Implementation Status

**Not started.** No `dashboard/` directory exists. No new API endpoints from this phase found. 0/26 tasks done.

---

## Phase 2.8 — Datadog Adapter

### Purpose

Adds Datadog as a selectable telemetry provider by implementing all four `provider-abstraction` query interfaces (metrics, traces, logs, dependency graph) using the official Datadog Python SDK, canonicalizing to the same data model as the Prometheus/OTel adapter.

### Feature List

- `adapters/telemetry/datadog/` directory with 5 files (`__init__.py`, `metrics.py`, `traces.py`, `logs.py`, `service_map.py`)
- Metrics adapter: `MetricsQuery` via Datadog Metrics API v2 `POST /api/v2/query/timeseries`, pagination, canonical `CanonicalMetric` output, multi-site support (US1/US3/US5/EU1/AP1), circuit breaker
- Traces adapter: `TraceQuery` via APM Trace Search API, cursor-based pagination, canonical `CanonicalTrace` output
- Logs adapter: `LogQuery` via Logs Search API, cursor-based pagination, canonical `CanonicalLog` output
- Service map adapter: `DependencyGraphQuery` from Service Map API, same node/edge format as OTel
- Extended `TelemetrySettings`: Datadog API key, application key, site
- Datadog provider registered in registry (`telemetry_provider: "datadog"`)
- API credential validation on startup
- Unit tests with mocked API responses + canonical parity test (same data → Prometheus == Datadog output)

### Tasks (from tasks.md)

All tasks are unchecked — 0 done.

**DD-001 — Metrics Adapter (~7 tasks)**
- [ ] 1.1 Create `__init__.py`
- [ ] 1.2 Create `metrics.py` implementing `MetricsQuery`
- [ ] 1.3 Implement `query_metrics()` via Metrics API v2
- [ ] 1.4 Implement pagination
- [ ] 1.5 Canonicalize to `CanonicalMetric`
- [ ] 1.6 Support multi-site configuration
- [ ] 1.7 Circuit breaker wrapping

**DD-002 — Traces Adapter (~4 tasks)**
- [ ] 2.1 Create `traces.py` implementing `TraceQuery`
- [ ] 2.2 Implement `query_traces()` via APM API
- [ ] 2.3 Canonicalize to `CanonicalTrace`
- [ ] 2.4 Handle cursor-based pagination

**DD-003 — Logs Adapter (~4 tasks)**
- [ ] 3.1 Create `logs.py` implementing `LogQuery`
- [ ] 3.2 Implement `query_logs()` via Logs Search API
- [ ] 3.3 Canonicalize to `CanonicalLog`
- [ ] 3.4 Handle cursor-based pagination and sort ordering

**DD-004 — Service Map Adapter (~3 tasks)**
- [ ] 4.1 Create `service_map.py` implementing `DependencyGraphQuery`
- [ ] 4.2 Build dependency graph from Service Map API
- [ ] 4.3 Canonicalize to same node/edge format

**DD-005 — Configuration and Registration (~3 tasks)**
- [ ] 5.1 Extend `TelemetrySettings` with Datadog credentials and site
- [ ] 5.2 Register in provider registry
- [ ] 5.3 Validate credentials on startup

**DD-006 — Testing (~3 tasks)**
- [ ] 6.1 Unit tests for all four adapters (mocked)
- [ ] 6.2 Canonical parity test
- [ ] 6.3 Integration test with Datadog API sandbox (if available)

**Summary:** 24 tasks total, 0 done, 24 pending.

### Key Design Decisions

- Official `datadog-api-client` SDK (handles auth, pagination, retries, multi-site)
- Separate files per query type (not monolithic adapter) — follows AWS adapter pattern
- Request coalescing and configurable metric query cache TTL to handle Datadog API rate limits (300 req/hr)
- `raw_metadata` passthrough for Datadog-specific fields not in canonical model

### Dependencies

- `provider-abstraction` spec and canonical data model (confirmed in place)
- `datadog-api-client` Python SDK (new dependency)
- Prometheus/OTel adapter structure as reference pattern

### Implementation Status

**Not started.** No `adapters/telemetry/datadog/` directory exists. 0/24 tasks done.

---

## Phase 2.9 — Log Fetching Gap Closure

### Purpose

Closes P1 gaps identified in the log fetching capabilities review: registers CloudWatch as a selectable telemetry provider (previously dead code), fixes a latent `AttributeError` in the enrichment-to-timeline path, enables bridge enrichment by default, adds a Kubernetes pod log fallback adapter (no Loki required), and adds New Relic log adapter contract tests.

### Feature List

- `CLOUDWATCH` added to `TelemetryProviderType` enum
- `_cloudwatch_factory()` registered in `adapters/bootstrap.py` (lazy boto3 imports, LocalStack endpoint support)
- `AlertEnricher._to_canonical_logs()` fixed: returns `list[CanonicalLogEntry]` instead of `list[dict]`
- `FeatureFlags.bridge_enrichment` default changed from `False` to `True`
- `BRIDGE_ENRICHMENT` env var default changed from `"0"` to `"1"`
- `KubernetesLogAdapter` at `adapters/telemetry/kubernetes/pod_log_adapter.py` implementing `LogQuery` (pod log access via `CoreV1Api`, `anyio.to_thread.run_sync()` wrapping, up to 5 pods, `tail_lines=1000`, severity inference)
- `FallbackLogAdapter` decorator at `adapters/telemetry/fallback_log_adapter.py` (primary + fallback `LogQuery`, transparent to domain, structured fallback logs)
- `kubernetes>=29.0.0` as optional dependency in `pyproject.toml`
- New Relic log adapter contract tests (`test_newrelic_log_adapter.py`) using `httpx.MockTransport`
- Full OTel runtime Loki primary + K8s fallback wired at bootstrap
- Hexagonal boundary guard test (`test_hexagonal_boundaries.py`)

### Tasks (from tasks.md)

Most tasks are checked — phase is largely complete.

**Gate 0 — Preflight (~4 tasks)**
- [x] 0.1 Verify source files referenced in implementation plan are current
- [x] 0.2 Run baseline test suite
- [x] 0.3 Confirm `CloudWatchProvider` constructor signature
- [x] 0.4 Confirm `CanonicalLogEntry` imports in `enrichment.py`

**Gate 1 — Critical Bug Fix: Enrichment Log Format (~4 tasks)**
- [x] 1.1 Fix `_to_canonical_logs()` return type
- [x] 1.2 Unit test: enrichment returns `CanonicalLogEntry` instances
- [x] 1.3 Unit test: `TimelineConstructor` processes enrichment output without error
- [x] 1.4 Run unit tests to confirm no regressions

**Gate 2 — Enable Enrichment by Default (~4 tasks)**
- [x] 2.1 Change `FeatureFlags.bridge_enrichment` default to `True`
- [x] 2.2 Change `BRIDGE_ENRICHMENT` env var default to `"1"`
- [x] 2.3 Unit test: `FeatureFlags` defaults to enrichment enabled
- [x] 2.4 Run unit tests

**Gate 3 — Register CloudWatch Provider (~7 tasks)**
- [x] 3.1 Add `CLOUDWATCH` to `TelemetryProviderType` enum
- [x] 3.2 Create `_cloudwatch_factory()` in bootstrap
- [x] 3.3 Register factory in `register_builtin_providers()`
- [x] 3.4 Unit test: CloudWatch factory registered
- [x] 3.5 Unit test: CloudWatch factory creates provider
- [x] 3.6 Integration test: CloudWatch provider bootstrap with LocalStack
- [x] 3.7 Run unit tests

**Gate 4 — Kubernetes Log Fallback (~6 tasks)**
- [x] 4.1 Add `kubernetes` as optional dependency
- [x] 4.2 Create `KubernetesLogAdapter`
- [x] 4.3 Create `FallbackLogAdapter` decorator
- [x] 4.4 Unit tests for `KubernetesLogAdapter`
- [x] 4.5 Unit tests for `FallbackLogAdapter`
- [x] 4.6 Run unit tests

**Gate 5 — New Relic Log Adapter Coverage (~2 tasks)**
- [x] 5.1 Add contract tests for `NewRelicLogAdapter`
- [x] 5.2 Run coverage report (92.6% on adapter scope)

**Gate 6 — Full Suite Verification (~5 tasks)**
- [x] 6.1 Run full unit test suite (857 passed)
- [x] 6.2 Run coverage report (90.02% global — meets 90% threshold)
- [ ] 6.3 Run linter and type checker — BLOCKED by pre-existing repository-wide Ruff violations (795 findings)
- [x] 6.4 Verify hexagonal architecture invariant
- [x] 6.5 Update `CHANGELOG.md`

**Summary:** 32 tasks total, 31 done, 1 pending (6.3 lint — pre-existing repo-wide issue, not introduced by this phase).

### Key Design Decisions

- Extend `TelemetryProviderType` enum (not string-based selection) to preserve compile-time validation
- Fix at adapter boundary (Anti-Corruption Layer): domain code must not handle adapter data formats
- Enable enrichment by default — both `FeatureFlags.bridge_enrichment` and `BRIDGE_ENRICHMENT` env var changed
- `KubernetesLogAdapter`: synchronous K8s client wrapped in `anyio.to_thread.run_sync()`; `kubernetes` is optional dependency
- `FallbackLogAdapter` as Decorator pattern — fallback logic isolated from both Loki and K8s adapters, wired only at bootstrap

### Dependencies

- Existing `CloudWatchProvider` and `CanonicalLogEntry` infrastructure (confirmed)
- `kubernetes>=29.0.0` optional dependency
- Loki adapter as primary log source in fallback chain

### Implementation Status

**Substantially complete.** 31/32 tasks done. Single open item (6.3 lint) is pre-existing repo-wide Ruff debt, not introduced by Phase 2.9. Confirmed by completion-state-report.md dated 2026-04-06.

---

## Phase 3.1 — Helm Deployment

### Purpose

Packages the SRE Agent as a production-quality Helm chart for standard Kubernetes deployment. Adds a Kubernetes Operator for lifecycle management (upgrades, backup, configuration reconciliation).

### Feature List

- `charts/sre-agent/Chart.yaml` with metadata, version, dependencies
- `charts/sre-agent/values.yaml` with all configurable settings
- `charts/sre-agent/values.schema.json` for JSON Schema validation and IDE autocompletion
- Deployment template, Service template, ConfigMap template, ServiceAccount + RBAC template, optional HPA template
- Phase-specific RBAC: Observe (read-only), Assist (read + limited write), Autonomous (read + write for remediations)
- RBAC selection via `values.yaml` `phase` setting
- values.yaml → environment variable + ConfigMap mapping; secret references (external-secrets-operator or K8s Secret)
- Provider-specific config blocks (telemetryProvider, cloudProvider)
- Artifact Hub metadata (`artifacthub-repo.yml`)
- Helm lint zero warnings; `helm template` validation for all provider combos; `ct install` on kind/k3d; health check passes after install
- Zero-downtime upgrades (rolling update, no inflight diagnosis interruption)
- Deployment healthy within 5 minutes of `helm install`

### Tasks (from tasks.md)

All tasks are unchecked — 0 done.

**HELM-001 — Chart Structure (~8 tasks)**
- [ ] 1.1 Create `Chart.yaml`
- [ ] 1.2 Create `values.yaml`
- [ ] 1.3 Create `values.schema.json`
- [ ] 1.4 Create `deployment.yaml` template
- [ ] 1.5 Create `service.yaml` template
- [ ] 1.6 Create `configmap.yaml` template
- [ ] 1.7 Create `serviceaccount.yaml` and `rbac.yaml`
- [ ] 1.8 Create `hpa.yaml` (optional)

**HELM-002 — RBAC Templates (~4 tasks)**
- [ ] 2.1 Observe phase RBAC (read-only ClusterRole)
- [ ] 2.2 Assist phase RBAC
- [ ] 2.3 Autonomous phase RBAC
- [ ] 2.4 RBAC selection via `phase` value

**HELM-003 — Configuration Injection (~3 tasks)**
- [ ] 3.1 Map values.yaml to env vars and ConfigMap
- [ ] 3.2 Secret references
- [ ] 3.3 Provider-specific config blocks

**HELM-004 — Testing (~4 tasks)**
- [ ] 4.1 `helm lint` passes
- [ ] 4.2 `helm template` renders valid YAML for all combos
- [ ] 4.3 `ct install` on kind/k3d
- [ ] 4.4 Health check passes after `helm install`

**Summary:** 19 tasks total, 0 done, 19 pending.

### Key Design Decisions

- Helm 3 (not Helm 2 or Kustomize) — standard for third-party distribution
- JSON Schema validation in `values.schema.json` for `helm lint` validation and IDE support
- Phase-specific RBAC templates: Observe has read-only; Autonomous adds write
- Operator is optional — Helm chart works standalone
- `charts/sre-agent/` directory (does not exist yet in workspace)

### Dependencies

- Docker multi-stage build (existing)
- Kubernetes 1.24+, Helm 3.x
- All cloud provider configurations (AWS/Azure/none) must be chartable

### Implementation Status

**Not started.** No `charts/` directory exists in workspace. 0/19 tasks done.

---

## Phase 3.2 — GCP Support

### Purpose

Extends the agent to a third cloud provider — GCP — by implementing `CloudOperatorPort` for GKE (via standard K8s API), Cloud Functions (concurrency), and Cloud Run (instance scaling), plus Google Secret Manager and Cloud Storage adapters.

### Feature List

- `adapters/cloud/gcp/__init__.py`
- `adapters/cloud/gcp/operator.py` implementing `CloudOperatorPort`: GKE workload restart/scale (standard K8s API), Cloud Functions concurrency via `google-cloud-functions`, Cloud Run min/max instance scaling via `google-cloud-run`
- `adapters/cloud/gcp/resource_metadata.py`: GKE cluster/workload discovery, Cloud Functions listing, Cloud Run service listing
- `adapters/cloud/gcp/secrets.py` implementing `SecretsPort` via Google Secret Manager
- `adapters/cloud/gcp/storage.py` implementing `ObjectStoragePort` via Cloud Storage (audit log persistence, Google-managed encryption)
- `CloudSettings` extended: GCP project ID, region, GKE cluster name, bucket name, secret prefix
- GCP registered as cloud provider (`cloud_provider: "gcp"`)
- GCP credential validation on startup
- Helm chart `values.yaml` updated with GCP config block
- Circuit breaker on all GCP API calls (reusing `resilience.py`)
- Workload Identity Federation authentication (no long-lived keys in GKE)
- Unit tests with mocked GCP APIs; behavioral parity tests vs AWS/Azure equivalents

### Tasks (from tasks.md)

All tasks are unchecked — 0 done.

**GCP-001 — Cloud Operator Adapter (~7 tasks)**
- [ ] 1.1 Create `__init__.py`
- [ ] 1.2 Create `operator.py` implementing `CloudOperatorPort`
- [ ] 1.3 GKE workload restart (K8s API)
- [ ] 1.4 GKE workload scaling (K8s API)
- [ ] 1.5 Cloud Functions concurrency management
- [ ] 1.6 Cloud Run min/max instance scaling
- [ ] 1.7 Circuit breaker wrapping

**GCP-002 — Resource Metadata (~4 tasks)**
- [ ] 2.1 Create `resource_metadata.py`
- [ ] 2.2 GKE cluster/workload discovery
- [ ] 2.3 Cloud Functions function listing and metadata
- [ ] 2.4 Cloud Run service listing and metadata

**GCP-003 — Secrets Adapter (~3 tasks)**
- [ ] 3.1 Create `secrets.py` implementing `SecretsPort`
- [ ] 3.2 Secret retrieval via Google Secret Manager
- [ ] 3.3 Workload Identity Federation auth

**GCP-004 — Storage Adapter (~3 tasks)**
- [ ] 4.1 Create `storage.py` implementing `ObjectStoragePort`
- [ ] 4.2 Audit log write to Cloud Storage bucket
- [ ] 4.3 Google-managed encryption

**GCP-005 — Configuration and Registration (~4 tasks)**
- [ ] 5.1 Extend `CloudSettings` with GCP fields
- [ ] 5.2 Register GCP in cloud provider registry
- [ ] 5.3 Validate GCP credentials on startup
- [ ] 5.4 Update Helm chart values.yaml with GCP block

**GCP-006 — Testing (~3 tasks)**
- [ ] 6.1 Unit tests with mocked GCP APIs
- [ ] 6.2 E2E tests vs GCP emulator or GCP Test project
- [ ] 6.3 Behavioral parity tests vs AWS/Azure

**Summary:** 24 tasks total, 0 done, 24 pending.

### Key Design Decisions

- GKE remediation via standard Kubernetes API (not GKE-specific API) — CNCF conformant
- Separate files per adapter (operator, resource_metadata, secrets, storage) — matches AWS/Azure pattern
- GCP-specific API only for Cloud Functions and Cloud Run (non-K8s resources)
- Workload Identity Federation for GKE auth; Service Account key fallback for non-GKE

### Dependencies

- Phase 3.1 (Helm chart must exist to add GCP values.yaml block)
- `google-cloud-container`, `google-cloud-functions`, `google-cloud-run`, `google-cloud-secret-manager`, `google-cloud-storage` (new dependencies)
- `SecretsPort` and `ObjectStoragePort` ABCs must exist in ports layer

### Implementation Status

**Not started.** No `adapters/cloud/gcp/` directory exists. 0/24 tasks done.

---

## Phase 3.3 — FinOps Remediation (Cost Context Enrichment)

### Purpose

Adds cost-context enrichment to all scaling and resource-modifying remediations. The agent queries per-workload monthly cost before execution and attaches a before/after delta estimate to `RemediationAction` and audit trail. Cost enrichment is advisory-only (non-gating).

### Feature List

- `CostProviderPort` ABC (`ports/cost.py`): `get_workload_cost()`, `estimate_scaling_cost()`, `health_check()`
- `CostEstimate` data model: `current_monthly_usd`, `projected_monthly_usd`, `delta_monthly_usd`, `resource_breakdown`
- `adapters/cost/kubecost.py` implementing `CostProviderPort` via kubecost Allocation API (`/model/allocation`): `get_workload_cost()`, `estimate_scaling_cost()` (linear extrapolation from per-replica cost), graceful unavailability handling (`cost_impact=null`), `health_check()`
- Cost enrichment step in remediation pipeline (before execution, after validation)
- `CostEstimate` attached to `RemediationAction` domain model
- Cost impact included in HITL approval notifications (Slack/PagerDuty)
- `cost_impact_monthly_usd` field in remediation event audit trail
- Cost breakdown in post-incident summary
- Cost impact in dashboard incident detail view
- `CostSettings` in `config/settings.py` (provider, kubecost URL, enabled flag)
- Cost adapter registered in `adapters/bootstrap.py`
- Helm chart `values.yaml` with cost provider configuration
- Monthly cost projection accuracy within 10%

### Tasks (from tasks.md)

All tasks are unchecked — 0 done.

**FIN-001 — Cost Provider Port (~2 tasks)**
- [ ] 1.1 Create `CostProviderPort` ABC
- [ ] 1.2 Define `CostEstimate` data model

**FIN-002 — kubecost Adapter (~5 tasks)**
- [ ] 2.1 Create `kubecost.py` implementing `CostProviderPort`
- [ ] 2.2 Implement `get_workload_cost()` via kubecost Allocation API
- [ ] 2.3 Implement `estimate_scaling_cost()` via linear extrapolation
- [ ] 2.4 Graceful kubecost unavailability handling
- [ ] 2.5 Implement `health_check()`

**FIN-003 — Remediation Engine Integration (~4 tasks)**
- [ ] 3.1 Add cost enrichment step in remediation pipeline
- [ ] 3.2 Query `CostProviderPort.estimate_scaling_cost()` for all scaling actions
- [ ] 3.3 Attach `CostEstimate` to `RemediationAction` data model
- [ ] 3.4 Include cost impact in HITL notifications

**FIN-004 — Audit Trail Integration (~3 tasks)**
- [ ] 4.1 Add `cost_impact_monthly_usd` to remediation event payloads
- [ ] 4.2 Include cost breakdown in post-incident summary
- [ ] 4.3 Add cost impact to dashboard incident detail view

**FIN-005 — Configuration (~3 tasks)**
- [ ] 5.1 Add `CostSettings` to `config/settings.py`
- [ ] 5.2 Register cost adapter in `adapters/bootstrap.py`
- [ ] 5.3 Update Helm chart values.yaml

**FIN-006 — Testing (~3 tasks)**
- [ ] 6.1 Unit tests for port and kubecost adapter
- [ ] 6.2 Integration test: scale-up → cost estimate attached → audit trail includes cost
- [ ] 6.3 Fallback test: kubecost unavailable → proceeds with `cost_impact=null`

**Summary:** 20 tasks total, 0 done, 20 pending.

### Key Design Decisions

- kubecost Allocation API over raw Prometheus cost metrics (avoids duplicating kubecost's allocation logic)
- Cost enrichment is advisory-only, never gates or delays remediation
- Monthly projection (not hourly) — more meaningful to operators and finance
- Non-blocking: if kubecost unavailable, `cost_impact=null` and remediation proceeds

### Dependencies

- Phase 2.7 Operator Dashboard (FIN-004.3 requires dashboard incident detail view)
- Phase 2.6 Notifications (FIN-003.4 requires HITL notification adapters)
- Phase 3.1 Helm chart (FIN-005.3)
- kubecost/OpenCost deployed in target cluster (optional, graceful fallback)
- `CostProviderPort` is a new port not yet defined

### Implementation Status

**Not started.** No `ports/cost.py` or `adapters/cost/` directory exists. 0/20 tasks done.

---

## Phase 4.0 — Persistence Architecture Reconciliation

### Purpose

Planning-phase deliverable (no runtime code in this phase). Resolves six document-authority conflicts, defines the canonical persistence data model and interface contracts, produces operational readiness artifacts, and establishes quantitative split gates — all before implementation coding begins.

### Feature List

**Architecture Document Reconciliation (C-01)**
- `persistence_architecture.md` established as implementation authority
- `Technology_Stack.md` updated: Redis Streams as current event bus; Kafka/NATS as threshold-triggered future split
- `roadmap.md` updated: pgvector for production, Chroma for development
- `persistence_architecture.md` updated: at-least-once delivery semantics, cooldown key naming alignment
- ADR-006 `docs/project/ADRs/006-persistence-authority-reconciliation.md` created

**Canonical Data Model (C-02 and C-03)**
- 9 entities: `incident_events` (immutable, `idempotency_key` unique), `incidents` projection, `diagnosis_results`, `remediation_actions` (with rollback FK), `event_outbox`, `telemetry_metrics` (TimescaleDB hypertable), `baseline_snapshots`, `vector_embeddings` (pgvector HNSW), `coordination_audit`
- State transitions: incident `open→investigating→mitigating→resolved→closed`; remediation `planned→approved→running→completed/failed→rolled_back`; outbox `pending→sent/failed→pending`

**Persistence Port Interfaces**
- `IncidentStorePort` ABC: `save_event()`, `get_events_by_incident()`, `get_incident()`, `update_projection()`
- `OutboxPort` ABC: `enqueue()`, `mark_sent()`, `mark_failed()`, `get_pending()`
- `CoordinationAuditPort` ABC: `record_lock_event()`, `record_cooldown_event()`, `record_override_event()`, `get_audit_trail()`
- Domain model classes: `IncidentEvent`, `Incident`, `DiagnosisResult`, `RemediationAction`, `OutboxEntry`, `CoordinationAuditEntry`

**SQL Migrations (3 scripts)**
- `001_incident_lifecycle.sql`: `incident_events`, `incidents`, `diagnosis_results`, `remediation_actions`, `event_outbox`
- `002_telemetry_vector.sql`: `telemetry_metrics` hypertable, `baseline_snapshots`, `vector_embeddings`
- `003_coordination_audit.sql`: `coordination_audit` with `compute_mechanism` and `provider` check constraints

**Outbox Relay and Stream Contract (C-04)**
- `OutboxRelay` class: polls committed `event_outbox` rows, publishes to Redis Streams, exponential backoff + jitter (max 10 retries), DLQ routing to `incident.events.dlq`, `idempotency_key` propagation
- Observability metrics: `outbox_pending_rows`, `outbox_dispatch_latency_ms`, `stream_consumer_lag_seconds`
- Redis Streams consumer group setup for `diagnostics`, `remediation`, `audit` groups

**Coordination State Contract (AGENTS.md alignment)**
- Lock key: `lock:{provider}:{compute_mechanism}:{resource_id}` (non-K8s), `lock:{namespace}:{resource_type}:{resource_name}` (K8s)
- Cooldown key aligned to same pattern
- `PostgresCoordinationAuditStore` implementing `CoordinationAuditPort`
- Lock manager adapters (Redis and etcd) updated to write audit entries
- Cooldown adapter key format verified and aligned

**Safety State Migration (C-05, first wave)**
- Cooldown state migrated from in-memory `_cooldown_registry` to Redis+PG durable store (`SafetyStatePort`)
- Kill-switch state migrated to Redis-backed persistence
- Human override events persisted via `CoordinationAuditPort`
- Cooldown check latency SLO: < 5 ms (Redis primary, PG audit async)

**PostgreSQL Adapters**
- `PostgresIncidentStore`: atomic `incident_events` + `event_outbox` write, connection pooling via asyncpg
- `PostgresDiagnosisStore`: `save_diagnosis()`, `save_remediation_action()`, `get_remediation_history()`
- Persistence adapter registration in `bootstrap.py`

**Operational Readiness Artifacts**
- `docs/operations/postgres-extension-readiness-report.md`: extension validation matrix (TimescaleDB >= 2.13.0, pgvector >= 0.5.0)
- `docs/operations/redis-degraded-mode-runbook.md`: detection thresholds, Modes A–D, 15-min exit stability window
- `scripts/ops/projection-rebuild-drill.py`: automated drill (30-day window, 100K events, p95 <= 80ms, total <= 45 min)
- `docs/operations/persistence-migration-rollback-runbook.md`: rollback trigger matrix, feature-flag-first procedures

**Split Gate Instrumentation (C-06)**
- `SplitGateConfig` dataclass with 6 threshold definitions
- `SplitGateEvaluator` service (read-only, structured logging on transitions)
- 6 quantitative gates: DB write latency (120ms/15min), outbox backlog (100K/10min), stream lag (60s/10min), DB contention (PG CPU>75%+IO>20%/30min), vector scale (1M rows+250ms/7 days), metrics ingest (10M/day+5min lag/3 days)

### Tasks (from tasks.md)

**Gate 0 — Preflight (5 tasks: T001–T005) — ALL DONE**
- [x] T001 Verify 2026-04-07 research artifacts present
- [x] T002 Verify 2026-04-08 reconciliation artifacts present
- [x] T003 Verify AGENTS.md policy tokens match contract definitions
- [x] T004 Verify six clarification gates resolved in reconciliation research
- [x] T005 Run existing test suite to establish baseline

**Gate 1 — Architecture Document Reconciliation (7 tasks: T006–T012) — ALL DONE**
- [x] T006 Update `Technology_Stack.md` — event bus decision convergence
- [x] T007 Update `roadmap.md` — vector backend and maturity convergence
- [x] T008 Update `persistence_architecture.md` — cooldown key naming fix (already correct)
- [x] T009 Update `persistence_architecture.md` — ADR-003 delivery semantics (already correct)
- [x] T010 Update `persistence_architecture.md` — vector schema field mismatch
- [x] T011 Create ADR-006 (`docs/project/ADRs/006-persistence-authority-reconciliation.md`)
- [x] T012 Run unit tests (no regressions from doc changes)

**Gate 2 — Persistence Port and Schema Foundation (7 tasks: T013–T019) — ALL PENDING**
- [ ] T013 Create `IncidentStorePort` and `OutboxPort` ABCs in `ports/persistence.py`
- [ ] T014 Create `CoordinationAuditPort` ABC in `ports/persistence.py`
- [ ] T015 SQL migration `001_incident_lifecycle.sql`
- [ ] T016 SQL migration `002_telemetry_vector.sql`
- [ ] T017 SQL migration `003_coordination_audit.sql`
- [ ] T018 Domain model classes in `domain/models/persistence.py`
- [ ] T019 Run unit tests

**Gate 3 — Outbox and Stream Contract (5 tasks: T020–T024) — ALL PENDING**
- [ ] T020 Create `OutboxRelay` adapter
- [ ] T021 Create outbox observability metrics
- [ ] T022 Create Redis Streams consumer group setup
- [ ] T023 Unit tests for outbox relay
- [ ] T024 Run unit tests

**Gate 4 — Coordination State Contract (5 tasks: T025–T029) — ALL PENDING**
- [ ] T025 Create `PostgresCoordinationAuditStore`
- [ ] T026 Update lock manager adapters to write coordination audit
- [ ] T027 Update cooldown adapter to use contract-aligned key formats
- [ ] T028 Unit tests for coordination audit persistence
- [ ] T029 Run unit tests

**Gate 5 — Safety State Migration (5 tasks: T030–T034) — ALL PENDING**
- [ ] T030 Migrate cooldown state to durable store
- [ ] T031 Migrate kill-switch state to durable store
- [ ] T032 Migrate override state to durable audit trail
- [ ] T033 Unit tests for durable safety state
- [ ] T034 Run unit tests

**Gate 6 — PostgreSQL Adapters (5 tasks: T035–T039) — ALL PENDING**
- [ ] T035 Create `PostgresIncidentStore`
- [ ] T036 Create `PostgresDiagnosisStore`
- [ ] T037 Register persistence adapters in bootstrap
- [ ] T038 Integration tests for `PostgresIncidentStore`
- [ ] T039 Run unit and integration tests

**Gate 7 — Operational Readiness (4 tasks: T040–T042A) — ALL PENDING**
- [ ] T040 Execute PostgreSQL extension readiness validation and produce report
- [ ] T041 Finalize Redis degraded-mode runbook
- [ ] T042 Finalize projection rebuild drill script
- [ ] T042A Finalize migration rollback runbook

**Gate 8 — Split Gate Instrumentation (4 tasks: T043–T046) — ALL PENDING**
- [ ] T043 Create `SplitGateConfig` dataclass
- [ ] T044 Create `SplitGateEvaluator` service
- [ ] T045 Unit tests for split gate evaluator
- [ ] T046 Run unit tests

**Gate 9 — Full Suite Verification (~2+ tasks: T047–T048+) — ALL PENDING**
- [ ] T047 Run full unit test suite
- [ ] T048 Run coverage report
- (Additional coverage and compliance tasks expected)

**Summary:** ~49 tasks total, 12 done (T001–T012, Gates 0–1), ~37 pending (T013 onwards).

> **Note:** The current editor context shows `src/sre_agent/ports/persistence.py` as the active file — T013 (creating this file) may be in progress.

### Key Design Decisions

- "Reconcile first, implement second" — doc conflicts resolved before any code (adds small planning cost, eliminates drift class)
- At-least-once delivery + idempotent consumers (not strict exactly-once) — outbox inherently provides this; strict exactly-once requires distributed transaction coordination
- pgvector for production, ChromaDB for development — keeps vector persistence within PG operational surface
- Redis Streams as current event bus — already in stack for locks; Kafka/NATS as quantitative split-gate-triggered future
- Safety state (cooldown, kill-switch, override) included in first migration wave — safety-critical gap that cannot wait
- `compute_mechanism` token naming standardized to AGENTS.md canonical values across all documents

### Dependencies

- Six clarification gates (C-01 through C-06) must be resolved before implementation coding (done in Gates 0–1)
- PostgreSQL with TimescaleDB >= 2.13.0 and pgvector >= 0.5.0 required (extension readiness is a blocking gate — T040)
- Redis Streams already in stack
- asyncpg for PostgreSQL adapter connection pooling

### Implementation Status

**Gates 0 and 1 complete (planning artifacts done). Implementation not started (T013+).** Architecture reconciliation ADR and document updates delivered 2026-04-09. All port interfaces, SQL migrations, adapters, and operational artifacts pending.

---

## Integrate Alignment Report

### Purpose

Formally integrates the AI agent architecture alignment report into `docs/architecture/` and updates references in `README.md` and `Technology_Stack.md`. Documentation-only change; no implementation.

### Feature List

- Move `alignment_report.md` to `docs/architecture/alignment_report.md`
- Update `README.md` to reference the alignment report
- Update `docs/architecture/Technology_Stack.md` to reference potential MCP adoption and explicit LLM tracing findings

### Tasks (from tasks.md)

All tasks are unchecked — 0 done.

**Documentation Integration (3 tasks)**
- [ ] 1.1 Move `alignment_report.md` to `docs/architecture/`
- [ ] 1.2 Update `README.md` with reference
- [ ] 1.3 Update `Technology_Stack.md` with MCP and LLM tracing references

**Summary:** 3 tasks total, 0 done, 3 pending.

### Key Design Decisions

- Report is evaluation of current state, not an implementation plan
- Document placement in `docs/architecture/` to centralize architecture artifacts
- MCP and Graph RAG adoption documented as opportunities, not committed work

### Dependencies

- `alignment_report.md` must exist in project root (assumed present from earlier research)

### Implementation Status

**Not started.** Alignment report not yet moved. 0/3 tasks done.

---

## Summary Table

| Phase | Purpose | Feature Count | Tasks Done | Tasks Pending | Overall Status |
|-------|---------|--------------|-----------|--------------|----------------|
| 2.5 Slow Response Detection | New anomaly types + arbitration for K8s/AWS/Azure latency | 17 features | 0 | 29 | Not started |
| 2.6 Notification Integrations | Slack, Teams, PagerDuty, OpsGenie adapters for HITL | 8 capabilities | 0 | 32 | Not started |
| 2.7 Operator Dashboard | React/Next.js SPA + API/WebSocket endpoints | 8 capabilities | 0 | 26 | Not started |
| 2.8 Datadog Adapter | Full Datadog telemetry provider (metrics, traces, logs, deps) | 4 adapters | 0 | 24 | Not started |
| 2.9 Log Fetching Gap Closure | CloudWatch bootstrap, enrichment fix, K8s fallback adapter | 6 capabilities | 31 | 1 (lint) | Substantially complete |
| 3.1 Helm Deployment | Production Helm chart + K8s Operator | 2 capabilities | 0 | 19 | Not started |
| 3.2 GCP Support | GKE/Cloud Functions/Cloud Run operator + secrets/storage | 4 capabilities | 0 | 24 | Not started |
| 3.3 FinOps Remediation | Cost-context enrichment on scaling remediations | 3 capabilities | 0 | 20 | Not started |
| 4.0 Persistence Reconciliation | Planning: doc reconciliation + port interfaces + PG adapters | 8 capabilities | 12 (Gates 0–1) | 37 | In progress (planning phase done) |
| Integrate Alignment Report | Move alignment report, update doc references | 1 capability | 0 | 3 | Not started |

**Totals across all phases:** ~205 tasks; 43 done; ~162 pending.

---

## Most Important Pending Work

### Highest Priority (blocking subsequent phases or safety-critical)

1. **Phase 4.0 T013/T014** — Create `IncidentStorePort`, `OutboxPort`, `CoordinationAuditPort` ABCs in `src/sre_agent/ports/persistence.py`. Current editor context shows this file is active — work may be in progress. This is the critical-path entry to all persistence implementation (T015–T048).

2. **Phase 4.0 T030/T031** — Migrate cooldown and kill-switch state from in-memory to durable store. This is a safety-critical gap: pod restart zeros cooldown timers and resets kill-switch state in the current implementation.

3. **Phase 2.5** — `SLOW_RESPONSE` and `TIMEOUT_PROXIMITY` anomaly types are entirely unimplemented. The detector cannot fire absolute-threshold or timeout proximity alerts. Gateway item for reliability on ECS and Lambda.

4. **Phase 2.6** — No notification channel exists for HITL approval. Phase 2 HITL workflow cannot function in production without Slack/PagerDuty adapters.

5. **Phase 2.9 Task 6.3 (lint)** — 795 pre-existing Ruff violations block the lint gate. Not introduced by Phase 2.9 but blocks a clean CI gate for the entire repository.

### Notable Open Issues Discovered

- Phase 2.5B (Azure App Service slow response) is blocked by an unknown Azure Monitor Metrics Adapter availability status (Task 0.2 gate not yet evaluated).
- Phase 3.3 (FinOps) depends on Phase 2.7 (Dashboard) and Phase 2.6 (Notifications), both not started.
- Phase 3.2 (GCP) depends on Phase 3.1 (Helm chart existence for GCP values.yaml block), not started.
- Phase 4.0 extension readiness (T040) — PostgreSQL extension matrix not yet executed; TimescaleDB and pgvector availability unvalidated, which is a blocking gate for Phase 4.0 implementation start.

---

## Clarifying Questions

None that cannot be answered through research. All original questions are answered above.

---

## References

- openspec/changes/phase-2-5-slow-response-detection/design.md
- openspec/changes/phase-2-5-slow-response-detection/spec.md
- openspec/changes/phase-2-5-slow-response-detection/tasks.md
- openspec/changes/phase-2-6-notification-integrations/proposal.md
- openspec/changes/phase-2-6-notification-integrations/design.md
- openspec/changes/phase-2-6-notification-integrations/tasks.md
- openspec/changes/phase-2-7-operator-dashboard/proposal.md
- openspec/changes/phase-2-7-operator-dashboard/design.md
- openspec/changes/phase-2-7-operator-dashboard/tasks.md
- openspec/changes/phase-2-8-datadog-adapter/proposal.md
- openspec/changes/phase-2-8-datadog-adapter/design.md
- openspec/changes/phase-2-8-datadog-adapter/tasks.md
- openspec/changes/phase-2-9-log-fetching-gap-closure/proposal.md
- openspec/changes/phase-2-9-log-fetching-gap-closure/design.md
- openspec/changes/phase-2-9-log-fetching-gap-closure/tasks.md
- openspec/changes/phase-2-9-log-fetching-gap-closure/completion-state-report.md
- openspec/changes/phase-3-1-helm-deployment/proposal.md
- openspec/changes/phase-3-1-helm-deployment/design.md
- openspec/changes/phase-3-1-helm-deployment/tasks.md
- openspec/changes/phase-3-1-helm-deployment/specs/helm-deployment/spec.md
- openspec/changes/phase-3-2-gcp-support/proposal.md
- openspec/changes/phase-3-2-gcp-support/design.md
- openspec/changes/phase-3-2-gcp-support/tasks.md
- openspec/changes/phase-3-2-gcp-support/specs/gcp-operator/spec.md
- openspec/changes/phase-3-3-finops-remediation/proposal.md
- openspec/changes/phase-3-3-finops-remediation/design.md
- openspec/changes/phase-3-3-finops-remediation/tasks.md
- openspec/changes/phase-3-3-finops-remediation/specs/finops-enrichment/spec.md
- openspec/changes/phase-4-0-persistence-reconciliation/proposal.md
- openspec/changes/phase-4-0-persistence-reconciliation/design.md
- openspec/changes/phase-4-0-persistence-reconciliation/tasks.md
- openspec/changes/phase-4-0-persistence-reconciliation/specs/persistence-reconciliation/spec.md
- openspec/changes/integrate-alignment-report/proposal.md
- openspec/changes/integrate-alignment-report/design.md
- openspec/changes/integrate-alignment-report/tasks.md
- openspec/changes/integrate-alignment-report/specs/architecture-alignment/spec.md
