# Change Proposals Analysis

**Status:** Complete  
**Date:** 2026-05-30  
**Research Topics:** Features, tasks, design decisions, phases across all openspec change proposals

---

## Summary of Change Proposals Investigated

| Change | Phase Label | Purpose |
|---|---|---|
| autonomous-sre-agent | Foundation (All Phases) | Greenfield system definition — the master spec |
| add-executable-specs | Dev Tooling | AsyncAPI + Behave BDD infrastructure |
| phase-2-5-slow-response-detection | Phase 2.5A/B | Slow response / timeout-proximity detection |
| phase-2-6-notification-integrations | Phase 2.6 | Slack, Teams, PagerDuty, OpsGenie adapters |
| phase-2-7-operator-dashboard | Phase 2.7 | React/Next.js SPA operator dashboard |
| phase-2-8-datadog-adapter | Phase 2.8 | Datadog telemetry provider adapter |
| phase-2-9-log-fetching-gap-closure | Phase 2.9 | Log fetching bug fixes + CloudWatch + K8s fallback |
| phase-3-1-helm-deployment | Phase 3.1 | Helm chart + K8s Operator |
| phase-3-2-gcp-support | Phase 3.2 | GCP tri-cloud support |
| phase-3-3-finops-remediation | Phase 3.3 | Cost-context enrichment for remediations |
| phase-4-0-persistence-reconciliation | Phase 4.0 | Durable persistence, architecture reconciliation |
| integrate-alignment-report | Documentation | Architecture alignment report integration |
| archive/phase-1-5-non-k8s-platforms | Phase 1.5 (archived/completed) | Multi-cloud compute abstraction |
| archive/phase-2-1-observability | Phase 2.1 (archived/completed) | Agent self-observability + SLO instrumentation |

---

## 1. autonomous-sre-agent (Foundation)

**Purpose:** Defines the full Autonomous SRE Agent system — the greenfield master specification across all phases.

### Feature List (New Capabilities)

- **telemetry-ingestion**: Multi-signal collection via OpenTelemetry + eBPF (metrics, logs, traces, kernel events). OTel exporters to Prometheus/Mimir, Jaeger/Tempo, Loki. eBPF for syscalls, network flows, process behavior. Signal correlation by trace ID + time window. Auto-discovery service dependency graph (5-min refresh).
- **anomaly-detection**: ML-based anomaly detection on streaming time-series. Rolling baseline computation for latency percentiles, error rate, throughput. Alert correlation engine using dependency graph. Alert suppression for planned maintenance. Operator API for per-service sensitivity config.
- **rag-diagnostics**: RAG-powered root cause analysis. Vector DB for historical incidents, post-mortems, runbooks. Alert-to-vector embedding. Chronological event timeline construction. LLM reasoning engine generating hypotheses. Evidence-weighted confidence scoring (trace + timeline + retrieval quality). Second-opinion validator. Provenance tracking.
- **remediation-engine**: Safe, reversible action execution. Pod restart, horizontal scaling, log rotation. GitOps/ArgoCD deployment rollbacks. Certificate rotation. Severity-based execution paths (auto for Sev 3-4, PR-required for Sev 1-2). Post-remediation verification with 5-min observation window. Automatic rollback on metric degradation.
- **safety-guardrails** (Three-Tier):
  - *Action execution*: Evidence-weighted confidence gating (≥0.85 auto-execute, 0.70–0.85 proposal, <0.70 escalate), blast radius limits (20% restart, 50% scaling), canary execution (5% first), kill switch (API + CLI + Slack).
  - *Knowledge/reasoning*: RAG grounding, 90-day document TTL, staleness detection, human review gate for runbooks.
  - *Security/access*: IAM least-privilege, input sanitization on all telemetry, immutable audit logging, secrets management (HashiCorp Vault / AWS SM).
- **agent-coordination**: Distributed mutual exclusion locks (etcd/Redis). Priority hierarchy (Security > SRE > Cost Optimization). Oscillation detection (>3 contradictory actions in 30 min → halt + alert). Conflict resolution alerting.
- **incident-learning**: Resolved incident indexing pipeline. Human feedback capture. Pattern detection for recurring incidents. Diagnostic accuracy tracking dashboard. 20% mandatory human routing (skill atrophy prevention). On-call manual handling quota (min 2 incidents/shift).
- **phased-rollout**: Four-phase state machine (Observe → Assist → Autonomous → Predictive). Shadow mode diagnostic comparison. Severity-scoped authorization per phase. Graduation gate evaluation engine. Dual sign-off workflow (engineering leadership + SRE team lead). Automatic phase regression on safety violations.
- **severity-classification**: Sev 1-4 automated assignment. Multi-dimensional scoring (user impact, service tier, blast radius, financial impact, remediation reversibility). Human override API with real-time reclassification. Deployment correlation flag for automatic Sev elevation. Service tier weighting (Tier 1-3).
- **notifications** (Abstract): Multi-channel delivery (PagerDuty, Slack, Jira). Escalations, approval requests, post-incident summaries. Fallback and severity-based routing.
- **operator-dashboard** (Abstract): Real-time agent status, confidence visualization, diagnostic accuracy metrics, incident timeline drill-down, graduation gate progress tracker.
- **provider-abstraction**: Canonical data model (metrics, traces, logs, events). MetricsQuery, TraceQuery, LogQuery, DependencyGraphQuery interfaces. OTel/Prometheus + New Relic adapters. Extensible plugin system for Datadog, Splunk, Dynatrace.
- **cloud-portability**: AWS (EKS), Azure (AKS), self-managed K8s. Secrets management abstraction (AWS SM / Azure KV / HashiCorp Vault). Object storage abstraction (S3 / Azure Blob / MinIO). IAM abstraction (IRSA / Workload Identity / K8s-native). "No cloud provider" mode.
- **performance-slos**: Detect-to-resolve ≤15 min for Sev 3-4. Per-stage latency instrumentation. RAG query 30-second timeout. Severity-based incident queue. 99.9% system availability. Graceful degradation logic.
- **predictive-capabilities** (Phase 4): Resource exhaustion prediction. Certificate/credential expiration tracking. Traffic pattern learning. Preemptive scaling. Degradation trend detection. Architectural improvement recommendations. Cross-service causal reasoning. Phase graduation gate evaluation.
- **token-optimization**: (implied by spec) Token-aware reasoning and evidence reranking pipeline.

### Tasks List (tasks.md) — Status: All unchecked [ ]

16 sections, 80+ individual tasks:
- **Section 1** (Telemetry Ingestion): 1.1–1.6 (OTel Collector, eBPF, signal correlation, dependency graph, health monitoring)
- **Section 2** (Anomaly Detection): 2.1–2.5 (baseline computation, ML model, alert correlation, suppression, sensitivity API)
- **Section 3** (RAG Diagnostic Pipeline): 3.1–3.9 (vector DB, document ingestion, embedding, timeline, LLM reasoning, confidence scoring, second-opinion, provenance)
- **Section 4** (Remediation Action Layer): 4.1–4.7 (planner, K8s actions, GitOps, severity-based execution, cert rotation, post-remediation verification, auto-rollback)
- **Section 5** (Safety Guardrails): 5.1–5.11 (confidence gating, blast radius, canary, kill switch, TTL enforcement, human review gate, IAM, input sanitization, audit logging, secrets)
- **Section 6** (Multi-Agent Coordination): 6.1–6.4 (distributed locking, priority hierarchy, oscillation detection, conflict alerting)
- **Section 7** (Incident Learning): 7.1–7.6 (incident indexing, feedback capture, pattern detection, accuracy dashboard, mandatory routing, on-call quota)
- **Section 8** (Integration & Ops): 8.1–8.6 (notifications, dashboard, config management, phase controls, E2E tests, adversarial red-teaming)
- **Section 9** (Severity Classification): 9.1–9.5 (service tier schema, multi-dimensional scoring, automated assignment, human override API, deployment correlation flag)
- **Section 10** (Phased Rollout Orchestrator): 10.1–10.6 (state machine, shadow mode, severity-scoped auth, graduation gate engine, dual sign-off, auto phase regression)
- **Section 11** (Notification & Escalation System): 11.1–11.7 (PagerDuty, Slack, approval flow, fallback delivery, resolution summary, Jira, severity routing)
- **Section 12** (Operator Dashboard): 12.1–12.5 (real-time status, confidence viz, accuracy dashboard, timeline drill-down, graduation gate progress)
- **Section 13** (Provider Abstraction Layer): 13.1–13.8 (canonical model, provider interface, OTel/Prometheus adapter, New Relic adapter, provider registry, dependency graph abstraction, health monitoring, plugin interface)
- **Section 14** (Cloud Portability): 14.1–14.6 (secrets abstraction, object storage abstraction, IAM abstraction, startup validation, no-cloud mode, cross-cloud tests)
- **Section 15** (Performance & Latency SLOs): 15.1–15.7 (per-stage instrumentation, latency waterfall dashboard, severity queue, RAG timeout, SLO alerting, graceful degradation, availability monitoring)
- **Section 16** (Predictive Capabilities — Phase 4): 16.1–16.8 (resource exhaustion prediction, cert expiration tracking, traffic pattern learning, preemptive scaling, degradation trend detection, architectural recommendations, cross-service causal reasoning, predictive phase graduation)

### Design Decisions

1. **OpenTelemetry + eBPF** over proprietary APM agents — vendor-neutral breadth (OTel) + kernel-level depth (eBPF)
2. **RAG with vector DB** over fine-tuned LLM — dynamic knowledge updates, provenance tracking, anti-hallucination
3. **Evidence-weighted confidence** over LLM self-reported confidence — objective structural checks
4. **GitOps via ArgoCD** over direct kubectl — auditable, deterministic rollbacks; PR-gated for Sev 1-2
5. **Mutual exclusion locks** over centralized orchestrator — no single-point-of-failure; uses existing Redis/etcd

### Acceptance Criteria (from specs/)

- Agent-coordination spec (v2.0.0 APPROVED): Lock acquisition/release on all remediations. Priority hierarchy enforcement (Security > SRE > Cost Opt). Oscillation halts at >3 contradictory actions in 30 min.
- Remediation-engine spec (v2.0.0 APPROVED): Strategy selection by anomaly type (OOM→RESTART, traffic→SCALE_UP, deployment→GITOPS_REVERT, cert→CERTIFICATE_ROTATION, disk→LOG_TRUNCATION). Post-remediation 5-min verification. Auto-rollback on metric degradation. Canary batch formula: `max(1, ceil(total_pods * canary_pct / 100))`.
- Safety-guardrails spec (v2.0.0 APPROVED): Confidence thresholds (≥0.85 auto, 0.70–0.85 proposal, <0.70 escalate). Blast radius: 20% restart fleet max, 2x replica max. Canary: 5% first, 60s healthy validation, minimum 1 pod.
- Severity-classification spec: Sev 1-4 definitions with multi-dimensional composite scoring. Human override with immediate reclassification and in-progress action halt.

### Dependencies

- All phases depend on this base spec
- Requires OTel instrumentation >80% service coverage before Phase 2
- Requires GitOps (ArgoCD/Flux) for rollback capability

---

## 2. add-executable-specs

**Purpose:** Dev tooling infrastructure — AsyncAPI event schema definitions + Behave BDD executable specification framework.

### Feature List

- **asyncapi-telemetry**: AsyncAPI YAML specs for Kafka/NATS event channels the agent subscribes to (metrics, logs, traces, eBPF data)
- **executable-specs**: Behave BDD framework integration — OpenSpec scenarios become automated Python integration tests

### Tasks List (tasks.md) — Status: All unchecked [ ]

- 1.1 Create `docs/architecture/api_contracts/` directory structure
- 1.2 Create skeleton `asyncapi.yaml` for basic event channels
- 2.1 Add `behave` to dev dependencies (`pyproject.toml`)
- 2.2 Create `tests/features/` and `tests/features/steps/`
- 2.3 Create `tests/features/README.md` explaining OpenSpec-to-feature mapping
- 2.4 Create sample `.feature` file for one existing capability (proof of concept)

### Design Decisions

1. AsyncAPI files stored in `docs/architecture/api_contracts/` (centralized with architecture docs)
2. Behave files in `tests/features/` + `tests/features/steps/` (standard Python BDD structure)
3. CI/CD enforcement: Behave tests gate merges

### Dependencies

- Foundational to all future spec-driven testing
- No dependencies on other phases

---

## 3. phase-2-5-slow-response-detection

**Purpose:** Adds absolute-threshold and timeout-proximity latency detection alongside existing sigma-based detection. Delivers in two sequenced gates (2.5A: K8s + AWS; 2.5B: Azure).

### Feature List

- **SLOW_RESPONSE anomaly type**: Absolute-threshold latency detection (no baseline required). Default: 2000ms for 60 seconds.
- **TIMEOUT_PROXIMITY anomaly type**: Serverless-only timeout risk detection. Default: 80% of function timeout.
- **Deterministic rule arbitration**: Single alert per `(service, metric_name, timestamp)`. Precedence: `TIMEOUT_PROXIMITY > SLOW_RESPONSE > LATENCY_SPIKE`.
- **Kubernetes p99 detection** (2.5A): `http_request_duration_p99` metric. HPA transient suppression.
- **ECS slow response detection** (2.5A): CloudWatch `ResponseTime` → canonical `ecs_response_time_ms`. Deployment correlation flag (`is_deployment_induced`).
- **Lambda timeout proximity detection** (2.5A): Uses `timeout_ms` metadata. Cold-start suppression applies. Falls back gracefully when timeout metadata unavailable.
- **Azure App Service detection** (2.5B): Conditional on Azure telemetry adapter availability. `requests/duration` → `appservice_response_time_ms`.

### Tasks List (tasks.md) — Status: All unchecked [ ]

- Gate 0 (Preflight): 0.1 scope confirmation, 0.2 Azure adapter dependency check
- Gate 1 (Domain Extensions): 1.1 Add `SLOW_RESPONSE`+`TIMEOUT_PROXIMITY` to `AnomalyType`, 1.2–1.4 Extend `DetectionConfig`
- Gate 2 (Detector Rules): 2.1 `_detect_absolute_latency()`, 2.2 `_detect_timeout_proximity()`, 2.3 Refactor latency evaluation path, 2.4 Cold-start suppression for timeout proximity
- Gate 3 (Platform Metrics): 3.1 ECS `ResponseTime` mapping, 3.2 Lambda `timeout_ms` enrichment, 3.3 K8s p99 polling defaults
- Gate 4 (Observability): 4.1 Structured log events, 4.2 Prometheus counters/histograms
- Gate 5 (Unit Tests): 5.1+ Domain tests covering all new rules

### Design Decisions

- **Phase 2.5A first** — avoids Azure adapter dependency blockers; ships K8s + AWS early
- **Single alert arbitration** — replaces ambiguous "higher severity" language with deterministic precedence
- **Baseline not required** for absolute/timeout rules — enables detection from first metric observation

### Dependencies

- `autonomous-sre-agent` anomaly detection base
- Phase 2.5B depends on Azure telemetry adapter (may be blocked)

---

## 4. phase-2-6-notification-integrations

**Purpose:** Concrete implementation of `NotificationPort` and `EscalationPort` ABCs with Slack, Teams, PagerDuty, and OpsGenie adapters. Enables Phase 2 HITL approval workflow.

### Feature List

- **NotificationPort ABC**: `send_alert()`, `send_approval_request()`, `send_resolution_summary()`, `health_check()`
- **EscalationPort ABC**: `create_incident()`, `update_incident()`, `resolve_incident()`, `health_check()`
- **slack-notifications**: Block Kit incident alerts. Interactive Approve/Reject buttons. Resolution summaries. Circuit breaker for Slack API.
- **teams-notifications**: Adaptive Cards for incident alerts and approval flow. Webhook-based delivery.
- **pagerduty-escalation**: Events API v2 integration. Severity mapping (Sev 1→critical, Sev 2→error). Dedup key for idempotent management. Auto-resolve on remediation completion.
- **opsgenie-escalation**: OpsGenie Alert API. Secondary on-call provider.
- **Severity-based routing**: Sev 1-2 → PagerDuty + Slack. Sev 3-4 → Slack only.
- **Fallback chain**: Priority-ordered retry across channels on failure.
- **Approval state in EventStore**: `ApprovalReceived` domain event — Slack is UI only.

### Tasks List (tasks.md) — Status: All unchecked [ ]

- NOTIF-001 (Ports): 1.1–1.4 (NotificationPort, EscalationPort, NotificationMessage model, EscalationPayload model)
- NOTIF-002 (Slack): 2.1–2.7 (adapter, send_alert, approval request, button handler, resolution summary, health_check, circuit breaker)
- NOTIF-003 (Teams): 3.1–3.4 (adapter, Adaptive Cards, webhook delivery, action handler)
- NOTIF-004 (PagerDuty): 4.1–4.6 (adapter, create/update/resolve incident, health_check)
- NOTIF-005 (OpsGenie): 5.1–5.3 (adapter, create/update/resolve, severity mapping)
- NOTIF-006 (Config): 6.1–6.4 (NotificationSettings, severity routing, fallback chain, bootstrap registration)
- NOTIF-007 (Tests): 7.1–7.4 (unit, Slack mock, PagerDuty mock, E2E HITL flow)

### Design Decisions

1. **Slack Bolt SDK** over raw Web API — built-in interactive component handling
2. **PagerDuty Events API v2** over REST API v2 — automated integration semantics, dedup key
3. **Approval state in EventStore** (not Slack) — event sourcing is single source of truth

### Acceptance Criteria (spec.md)

- Slack delivery ≤5 seconds of diagnosis completion
- Approval button click → `ApprovalReceived` event ≤3 seconds
- PagerDuty creation ≤3 seconds
- Fallback attempt within 10 seconds of primary failure
- All-channels exhausted → `notification_degraded=true` on `/api/v1/status`

### Dependencies

- `autonomous-sre-agent` notifications + safety-guardrails specs
- Requires Slack bot token, PagerDuty routing key in secrets manager

---

## 5. phase-2-7-operator-dashboard

**Purpose:** Concrete MVP implementation of the abstract `operator-dashboard` spec. React/Next.js SPA with real-time incident feed, confidence visualization, and phase tracker.

### Feature List

- **dashboard-incident-feed**: Real-time WebSocket-driven incident list. Per-incident: service name, severity badge, stage indicator, confidence score, elapsed timer. Severity filtering + sorting.
- **dashboard-confidence-viz**: Evidence-weighted confidence decomposition (trace, timeline, RAG, validator). Color-coded thresholds (green ≥0.8, yellow 0.5–0.8, red <0.5). Historical confidence trend chart.
- **dashboard-timeline-view**: Chronological incident timeline. Expandable entries. Links to source documents/dashboards. Shows alert trigger, telemetry queries, RAG documents, hypotheses, remediations, post-action metrics.
- **dashboard-phase-tracker**: Phase status indicator. Graduation criteria checklist with progress bars. Met (green) vs. unmet (red) criteria.
- **New API endpoints**: `GET /api/v1/incidents`, `GET /api/v1/incidents/{id}`, `GET /api/v1/incidents/{id}/timeline`, `GET /api/v1/phases/status`, `GET /api/v1/accuracy/summary`
- **WebSocket endpoint**: `GET /api/ws/incidents` — real-time incident event stream

### Tasks List (tasks.md) — Status: All unchecked [ ]

- DASH-001 (API): 1.1–1.6 (incidents list, incident detail, timeline, phase status, accuracy summary, WebSocket)
- DASH-002 (Foundation): 2.1–2.4 (Next.js 15 + TypeScript, Tailwind, layout component, WebSocket client)
- DASH-003 (Incident Feed): 3.1–3.4 (real-time list, per-incident display, filtering, detail modal)
- DASH-004 (Confidence Viz): 4.1–4.3 (decomposition component, color coding, trend chart)
- DASH-005 (Timeline): 5.1–5.3 (timeline component, expandable entries, evidence links)
- DASH-006 (Phase Tracker): 6.1–6.3 (phase status, graduation checklist, color coding)
- DASH-007 (Tests): 7.1–7.3 (API unit tests, React component tests, E2E browser test)

### Design Decisions

1. **Next.js 15 App Router** — SSR + React Server Components for data-heavy views
2. **WebSocket over SSE/polling** — bidirectional for future interactive features (kill switch from dashboard)
3. **Tailwind CSS** — rapid prototyping for internal operations tool

### Acceptance Criteria

- <200ms page load
- <1s WebSocket update delay
- Mobile-responsive layout

### Dependencies

- `phase-2-6-notification-integrations` (EventStore event model)
- `autonomous-sre-agent` operator-dashboard abstract spec

---

## 6. phase-2-8-datadog-adapter

**Purpose:** First proprietary telemetry backend adapter. Implements all four provider ABCs for Datadog APIs, canonicalizing to the internal data model.

### Feature List

- **datadog-telemetry**: Full metric/trace/log ingestion from Datadog. Provider selectable via `telemetry_provider: "datadog"`.
  - Metrics adapter (`metrics.py`): Datadog Metrics API v2. Pagination. `CanonicalMetric` output. Multi-site support (US1/US3/US5/EU1/AP1).
  - Traces adapter (`traces.py`): Datadog APM Trace Search API. Cursor-based pagination. `CanonicalTrace` output.
  - Logs adapter (`logs.py`): Datadog Logs Search API. Cursor-based pagination. `CanonicalLog` output.
  - Service map adapter (`service_map.py`): Datadog Service Map API → canonical node/edge graph.
- **Circuit breaker** on all Datadog API calls (reuses `resilience.py`)
- **Request coalescing** to stay within Datadog API rate limits (300 req/hr Metrics v2)
- **`raw_metadata` passthrough** for unmappable Datadog-specific fields

### Tasks List (tasks.md) — Status: All unchecked [ ]

- DD-001 (Metrics): 1.1–1.7 (adapter, query_metrics, pagination, canonicalize, multi-site, circuit breaker)
- DD-002 (Traces): 2.1–2.4 (adapter, query_traces, canonicalize, pagination)
- DD-003 (Logs): 3.1–3.4 (adapter, query_logs, canonicalize, pagination)
- DD-004 (Service Map): 4.1–4.3 (adapter, dependency graph, canonicalize)
- DD-005 (Config): 5.1–5.3 (TelemetrySettings extension, provider registry, startup validation)
- DD-006 (Tests): 6.1–6.3 (unit tests with mocks, canonical parity test, integration with DD sandbox)

### Design Decisions

1. **Official `datadog-api-client` SDK** — handles auth, pagination, retries, multi-site
2. **Separate files per query type** — follows existing `adapters/cloud/aws/` pattern; isolated testing

### Acceptance Criteria

- Canonical output parity: same data through Prometheus adapter == Datadog adapter (structurally)

### Dependencies

- `provider-abstraction` spec from `autonomous-sre-agent`
- Existing OTel/Prometheus adapter as parity reference

---

## 7. phase-2-9-log-fetching-gap-closure

**Purpose:** Closes five critical log-fetching gaps: dead CloudWatch provider, `AttributeError` bug in enrichment, missing K8s log fallback, Loki dependency, undocumented New Relic adapter.

### Feature List

- **cloudwatch-telemetry-provider**: `CLOUDWATCH` added to `TelemetryProviderType` enum. `_cloudwatch_factory` registered in bootstrap. Selectable via `TELEMETRY_PROVIDER=cloudwatch`.
- **kubernetes-log-fallback**: `KubernetesLogAdapter` via `CoreV1Api.read_namespaced_pod_log()`. Optional `kubernetes>=29.0.0` dependency. Async-safe via `anyio.to_thread.run_sync()`. Bounded: 5 pods max, `tail_lines=1000`.
- **FallbackLogAdapter decorator**: Composes primary (Loki) + fallback (K8s API). Wired at bootstrap. Transparent to domain.
- **bridge-enrichment** (fixed+enabled): `FeatureFlags.bridge_enrichment` default changed to `True`. Env var `BRIDGE_ENRICHMENT` default changed to `"1"`. Aligned between settings and demo script.
- **enrichment-log-format** (bugfix): `AlertEnricher._to_canonical_logs()` returns `list[CanonicalLogEntry]` (not `list[dict]`). Fixes `AttributeError` in `TimelineConstructor`.
- **New Relic log adapter documentation**: Contract tests added for `NewRelicLogAdapter.query_logs()` + `query_by_trace_id()`.

### Tasks List (tasks.md) — Status: Mixed (Gates 0-4 completed [x], Gates 5-6+ unchecked [ ])

- Gate 0 (Preflight): 0.1–0.4 [x] ALL COMPLETED
- Gate 1 (Enrichment Bug Fix): 1.1–1.4 [x] ALL COMPLETED
- Gate 2 (Enable Enrichment Default): 2.1–2.4 [x] ALL COMPLETED
- Gate 3 (CloudWatch Bootstrap): 3.1–3.7 [x] ALL COMPLETED
- Gate 4 (K8s Log Fallback): 4.1–4.x [x] ALL COMPLETED

**Completion State Report** (completion-state-report.md): Phase 2.9 is **partially complete**. Implementation gaps closed, coverage (90.02%) passing. Remaining: lint debt (pre-existing Ruff findings), Gate 6.6 integration rerun evidence.

### Design Decisions

1. **Extend `TelemetryProviderType` enum** over string-based selection — compile-time validation
2. **Fix enrichment at adapter boundary** over domain-side workaround — Anti-Corruption Layer principle
3. **Enable enrichment by default (dual mechanism alignment)** — both feature flag + env var changed
4. **`kubernetes` optional dependency** — avoids bloating non-Kubernetes deployments
5. **Decorator pattern for fallback** — SRP, OCP; no domain changes; bootstrap wiring only

### Dependencies

- CloudWatch bootstrap depends on `boto3`
- K8s adapter depends on `kubernetes>=29.0.0` (optional)

---

## 8. phase-3-1-helm-deployment

**Purpose:** Packages the SRE Agent as a production Helm chart with phase-based RBAC and adds a Kubernetes Operator for lifecycle management.

### Feature List

- **helm-deployment**: `helm install sre-agent`. `charts/sre-agent/` with Chart.yaml, values.yaml, values.schema.json. ConfigMap, Deployment, Service, ServiceAccount, RBAC, HPA templates. JSON Schema validation for `helm lint`.
- **k8s-operator**: Lifecycle management for upgrades, backup, configuration reconciliation. (`operator/` directory)
- **Phase-specific RBAC templates**:
  - Observe: read-only ClusterRole
  - Assist: read + limited write for approved actions
  - Autonomous: read + write for all remediation types
- **Artifact Hub metadata**: `artifacthub-repo.yml` for Helm chart discovery
- **Docker multi-stage build update**: Optimized for production, minimal attack surface

### Tasks List (tasks.md) — Status: All unchecked [ ]

- HELM-001 (Chart): 1.1–1.8 (Chart.yaml, values.yaml, schema, templates)
- HELM-002 (RBAC): 2.1–2.4 (phase-specific roles, values.yaml selection)
- HELM-003 (Config): 3.1–3.3 (values→env vars, secret refs, provider config blocks)
- HELM-004 (Tests): 4.1–4.4 (helm lint, helm template, ct install, health check)

### Design Decisions

1. **Helm 3** over Helm 2 or Kustomize — standard for third-party distribution
2. **values.yaml with JSON Schema** — `helm lint` validation + IDE autocompletion

### Dependencies

- All prior phases (packages the complete agent)

---

## 9. phase-3-2-gcp-support

**Purpose:** Extends cloud portability from dual-cloud (AWS+Azure) to tri-cloud by adding GCP operator adapters for GKE, Cloud Functions, and Cloud Run.

### Feature List

- **gcp-cloud-operator**: `CloudOperatorPort` implementation. GKE workload restart/scale (via standard K8s API). Cloud Functions concurrency management. Cloud Run min/max instance scaling.
- **gcp-resource-metadata**: GKE cluster/workload discovery. Cloud Functions listing and metadata. Cloud Run service listing and metadata.
- **gcp-secrets**: Google Secret Manager via `SecretsPort`. Workload Identity Federation support.
- **gcp-storage**: Cloud Storage via `ObjectStoragePort`. Audit log write. Google-managed key encryption.
- **GCP configuration block**: Project ID, region, GKE cluster name, bucket name, secret prefix in `CloudSettings`.
- **Helm chart update**: GCP configuration block in values.yaml.

### Tasks List (tasks.md) — Status: All unchecked [ ]

- GCP-001 (Operator): 1.1–1.7 (adapter, GKE restart/scale, Cloud Functions, Cloud Run, circuit breaker)
- GCP-002 (Metadata): 2.1–2.4 (resource discovery)
- GCP-003 (Secrets): 3.1–3.3 (Secret Manager adapter, Workload Identity)
- GCP-004 (Storage): 4.1–4.3 (Cloud Storage adapter, encryption)
- GCP-005 (Config): 5.1–5.4 (CloudSettings extension, registry, startup validation, Helm update)
- GCP-006 (Tests): 6.1–6.3 (unit, GCP emulator E2E, behavioral parity with AWS/Azure)

### Design Decisions

1. **GKE via standard K8s API** (not GKE-specific) — GKE is CNCF-conformant; no extra client needed
2. **Separate files per concern** following `adapters/cloud/aws/` pattern

### Dependencies

- `cloud-portability` port from `autonomous-sre-agent`
- `phase-3-1-helm-deployment` for Helm chart updates

---

## 10. phase-3-3-finops-remediation

**Purpose:** Adds cost-context enrichment to all scaling remediations. Non-blocking: cost visibility is additive, never prevents action.

### Feature List

- **CostProviderPort ABC**: `get_workload_cost()`, `estimate_scaling_cost()`, `health_check()`
- **CostEstimate data model**: `current_monthly_usd`, `projected_monthly_usd`, `delta_monthly_usd`, `resource_breakdown`
- **cost-context-enrichment**: Cost estimation step in remediation pipeline (pre-execution, post-validation). Attaches `CostEstimate` to `RemediationAction` model. Graceful fallback: `cost_impact=null` when provider unavailable.
- **kubecost-integration**: `CostProviderPort` via kubecost Allocation API (`/model/allocation`). Linear extrapolation for scaling cost estimation.
- **Audit trail integration**: `cost_impact_monthly_usd` in remediation event payloads. Cost breakdown in post-incident summaries. Cost impact in dashboard incident detail view.
- **HITL approval enhancement**: Cost impact visible in Slack/PagerDuty approval requests.

### Tasks List (tasks.md) — Status: All unchecked [ ]

- FIN-001 (Port): 1.1–1.2 (CostProviderPort, CostEstimate model)
- FIN-002 (kubecost): 2.1–2.5 (adapter, get_workload_cost, estimate_scaling_cost, graceful fallback, health_check)
- FIN-003 (Integration): 3.1–3.4 (remediation pipeline, scaling query, RemediationAction update, HITL notification)
- FIN-004 (Audit): 4.1–4.3 (event payloads, post-incident summary, dashboard detail)
- FIN-005 (Config): 5.1–5.3 (CostSettings, bootstrap registration, Helm update)
- FIN-006 (Tests): 6.1–6.3 (unit, integration: scale → cost attached, fallback: kubecost unavailable)

### Design Decisions

1. **kubecost allocation API** over raw Prometheus cost metrics — pre-calculated per-workload cost allocation
2. **Advisory-only** (non-gating) — reliability mission must never be delayed by cost visibility
3. **Monthly projection** over hourly cost — more meaningful for operators and finance

### Acceptance Criteria

- Cost projection accuracy within 10% monthly
- Fallback test: kubecost unavailable → remediation proceeds → `cost_impact=null`

### Dependencies

- `remediation-engine` port from `autonomous-sre-agent`
- `phase-3-1-helm-deployment` for Helm chart updates
- kubecost/OpenCost deployed in target cluster (optional)

---

## 11. phase-4-0-persistence-reconciliation

**Purpose:** Planning-only phase. Resolves six architecture conflicts (C-01 through C-06), defines canonical durable data model, produces implementation-ready contracts, establishes migration foundation.

### Feature List (New Capabilities)

- **persistence-data-model**: Canonical entity catalog — 10 entities:
  - `incident_events` (immutable append-only, idempotency_key unique constraint)
  - `incidents` (projection, updated from committed events)
  - `diagnosis_results`
  - `remediation_actions` (rollback FK validation, status transitions)
  - `event_outbox` (transactional outbox pattern)
  - `telemetry_metrics` (hypertable via TimescaleDB)
  - `baseline_snapshots`
  - `vector_embeddings` (pgvector HNSW index)
  - `coordination_audit`
- **outbox-delivery-contract**: At-least-once + idempotency-key semantics. DLQ after 10 retries. Exponential backoff with jitter. Three observability metrics: `outbox_pending_rows`, `outbox_dispatch_latency_ms`, `stream_consumer_lag_seconds`.
- **coordination-state-contract**: Lock/cooldown key schema aligned to `AGENTS.md`. `compute_mechanism` values: `KUBERNETES`, `SERVERLESS`, `VIRTUAL_MACHINE`, `CONTAINER_INSTANCE`. Human override formalization with `audit_required=true`. Fencing token enforcement.
- **architecture-reconciliation-adr**: ADR-006 created (`docs/project/ADRs/006-persistence-authority-reconciliation.md`). `persistence_architecture.md` is authoritative. Technology_Stack.md + roadmap.md converged.
- **split-gate-thresholds**: Six quantitative triggers for PostgreSQL consolidation → dedicated backends (DB write latency, outbox backlog, stream lag, DB contention, vector scale, metrics ingest rate).
- **Operational readiness artifacts**: PostgreSQL extension readiness matrix. Redis degraded-mode runbook (Modes A–D). Projection rebuild drill script (`scripts/ops/projection-rebuild-drill.py`).

### Modified Capabilities

- **multi-agent-coordination**: Cooldown key format standardized to `cooldown:{provider}:{compute_mechanism}:{resource_id}`
- **safety-state-migration**: Cooldown, kill-switch, and override state in first migration wave

### Tasks List (tasks.md) — Status: Mixed (Gates 0-1 completed [x], Gates 2-7 unchecked [ ])

- Gate 0 (Preflight): T001–T005 [x] ALL COMPLETED (2026-04-09)
- Gate 1 (Architecture Reconciliation): T006–T012 [x] ALL COMPLETED (2026-04-09) — Technology_Stack.md, roadmap.md, persistence_architecture.md updated; ADR-006 created
- Gate 2 (Persistence Port + Schema): T013–T019 [ ] — `IncidentStorePort`, `CoordinationAuditPort`, SQL migration scripts (001/002/003), domain model classes
- Gate 3 (Outbox + Stream Contract): T020–T024 [ ] — `OutboxRelay`, outbox metrics, Redis Streams consumer groups, unit tests
- Gate 4 (Coordination State): T025–T029 [ ] — `PostgresCoordinationAuditStore`, lock manager audit wiring, cooldown key format compliance
- Gate 5 (Safety State Migration): T030–T034 [ ] — Cooldown → Redis-backed, kill-switch → Redis-backed, override audit trail
- Gate 6 (PostgreSQL Adapter): T035–T039 [ ] — `PostgresIncidentStore`, `PostgresIncidentStore`, bootstrap registration, integration tests
- Gate 7 (Operational Readiness): T040–T042 [ ] — Extension readiness validation, Redis degraded-mode runbook, projection rebuild drill script

### Design Decisions

1. **Reconcile first, implement second** — eliminates architectural drift during implementation
2. **At-least-once + idempotent consumers** over strict exactly-once — PG+Redis cannot coordinate global transactions
3. **pgvector for production, Chroma for development** — keeps vector within PG operational surface
4. **Redis Streams now, Kafka/NATS as threshold-triggered future split**
5. **Safety state in first migration wave** — cooldown/kill-switch state is safety-critical, must not wait

### Clarification Gates Resolved

| Gate | Issue | Resolution |
|---|---|---|
| C-01 | Three-way document authority conflict | persistence_architecture.md is implementation authority |
| C-02 | pgvector vs ChromaDB | pgvector production, Chroma development |
| C-03 | Redis Streams vs Kafka/NATS | Redis now; Kafka/NATS threshold-triggered |
| C-04 | Delivery semantics ambiguity | At-least-once + idempotent consumers |
| C-05 | Safety state migration scope | Cooldown + kill-switch + override in first wave |
| C-06 | Split gate thresholds | Six quantitative triggers with duration windows |

### Dependencies

- Requires all Phase 1–3 work to be in place before implementation begins
- PostgreSQL with TimescaleDB ≥2.13.0 and pgvector ≥0.5.0 extensions
- Redis already deployed for lock coordination

---

## 12. integrate-alignment-report

**Purpose:** Documentation-only change. Formally integrates the AI Agent Architecture alignment report into `docs/architecture/`.

### Feature List

- **architecture-alignment**: Evaluates SRE Agent adherence to industry-standard AI agent patterns. References MCP and explicit LLM tracing as identified opportunities.

### Tasks List (tasks.md) — Status: All unchecked [ ]

- 1.1 Move `alignment_report.md` → `docs/architecture/alignment_report.md`
- 1.2 Update `README.md` with alignment report reference
- 1.3 Update `docs/architecture/Technology_Stack.md` with MCP adoption and LLM tracing findings

### Design Decisions

1. Document placement in `docs/architecture/` (centralized with architecture docs)
2. Alignment report is evaluation only — not an implementation plan

### Dependencies

- None (documentation only)

---

## 13. archive/phase-1-5-non-k8s-platforms (COMPLETED)

**Purpose:** Decoupled canonical data model from Kubernetes primitives, added multi-cloud compute abstraction, AWS + Azure remediation adapters.

### Feature List (all [x] COMPLETED)

- **serverless-anomaly-detection**: `ComputeMechanism` enum (KUBERNETES, SERVERLESS, VIRTUAL_MACHINE, CONTAINER_INSTANCE). Cold-start suppression for Lambda/Azure Functions. OOM exemption for serverless. Invocation error surge monitoring. eBPF graceful degradation with `is_supported()`.
- **aws-remediation-adapters**: `ECSOperator` (`StopTask`, `UpdateService`). `EC2ASGOperator` (`SetDesiredCapacity`). `LambdaOperator` (reserved concurrency). boto3 optional dependency.
- **azure-remediation-adapters**: `AppServiceOperator` (restart, instance scaling). `AzureFunctionsOperator` (restart, Premium scaling). `azure-mgmt-web` optional dependency.
- **cloud-portability (modified)**: `CloudOperatorPort` ABC. `CloudOperatorRegistry` (selects operator by `compute_mechanism` + provider). `ServiceLabels` refactored (generic `resource_id`, `compute_mechanism`; `namespace`/`pod` optional).

### Status

All tasks [x] COMPLETED (archived).

### Dependencies

- Breaking change to `ServiceLabels` in `canonical.py` — all downstream tests required updates

---

## 14. archive/phase-2-1-observability (COMPLETED)

**Purpose:** Agent self-observability — Prometheus metrics, SLO instrumentation, structured logging, correlation IDs, alert rules.

### Feature List (all [x] COMPLETED)

- **agent-self-observability**: Prometheus metrics module (`adapters/telemetry/metrics.py`). 14 metrics: `DIAGNOSIS_DURATION`, `DIAGNOSIS_ERRORS`, `SEVERITY_ASSIGNED`, `EVIDENCE_RELEVANCE`, `LLM_CALL_DURATION`, `LLM_TOKENS_USED`, `LLM_PARSE_FAILURES`, `LLM_QUEUE_DEPTH`, `LLM_QUEUE_WAIT`, `EMBEDDING_DURATION`, `EMBEDDING_COLD_START`, `CIRCUIT_BREAKER_STATE`, + `/metrics` endpoint.
- **slo-instrumentation**: `/healthz` readiness probe with component checks (vector store, embedding, LLM). HTTP 503 on failure. `DIAGNOSIS_DURATION` histogram. `EVIDENCE_RELEVANCE` histogram. `SEVERITY_ASSIGNED` counter. `DIAGNOSIS_ERRORS` counter.
- **correlation-id-propagation**: `contextvars.ContextVar[str]` for `alert_id`. Structlog processor injects `alert_id` into every log line during diagnosis. `X-Request-ID` header on HTTP responses.
- **real-healthz-probe**: Component-level readiness checks (vector store, embedding, LLM init).
- **circuit-breaker-observability**: `CIRCUIT_BREAKER_STATE` gauge (0=CLOSED, 1=HALF_OPEN, 2=OPEN) on every state transition.
- **rag-diagnostics (modified)**: 8 structured log points (diagnosis_started, embed_alert, vector_search_complete, token_budget_trim, llm_hypothesis_start, validation_start, confidence_scored, diagnosis_completed).
- **llm-reasoning (modified)**: Token usage as Prometheus counters (`LLM_TOKENS_USED`, `LLM_CALL_DURATION`) for both Anthropic + OpenAI adapters.
- **throttled-llm (modified)**: Queue depth + wait time exported as Prometheus metrics.
- **api-layer (modified)**: HTTP request logging middleware with structured `request_received` + `request_completed` log lines.
- **Prometheus alert rules** (`infra/prometheus/rules/sre_agent_slo.yaml`): 8 rules — `DiagnosisLatencySLOBreach` (P99 >30s for 2 min), `LLMAPIErrors`, `LLMParseFailureSpike`, `ThrottleQueueSaturation`, `EvidenceQualityDrop`, `LLMTokenRateTooHigh`, `EmbeddingColdStartHigh`, + `sre_agent:diagnosis_latency:p99` recording rule.

### Status

All tasks [x] COMPLETED (archived).

---

## Master Feature Table

| Feature | Phase | Spec/Change |
|---|---|---|
| telemetry-ingestion (OTel + eBPF) | Foundation | autonomous-sre-agent |
| anomaly-detection (ML time-series) | Foundation | autonomous-sre-agent |
| rag-diagnostics (RAG + LLM reasoning) | Foundation | autonomous-sre-agent |
| remediation-engine (safe + reversible) | Foundation | autonomous-sre-agent |
| safety-guardrails (3-tier framework) | Foundation | autonomous-sre-agent |
| agent-coordination (distributed locks + priority) | Foundation | autonomous-sre-agent |
| incident-learning (continuous learning pipeline) | Foundation | autonomous-sre-agent |
| phased-rollout (Observe→Assist→Autonomous→Predictive) | Foundation | autonomous-sre-agent |
| severity-classification (Sev 1-4 auto + override) | Foundation | autonomous-sre-agent |
| notifications (abstract multi-channel) | Foundation | autonomous-sre-agent |
| operator-dashboard (abstract) | Foundation | autonomous-sre-agent |
| provider-abstraction (canonical model + plugin) | Foundation | autonomous-sre-agent |
| cloud-portability (AWS/Azure/self-managed K8s) | Foundation | autonomous-sre-agent |
| performance-slos (detect-to-resolve ≤15 min) | Foundation | autonomous-sre-agent |
| predictive-capabilities (Phase 4 proactive) | Phase 4 | autonomous-sre-agent |
| token-optimization | Foundation | autonomous-sre-agent |
| asyncapi-telemetry | Dev Tooling | add-executable-specs |
| executable-specs (Behave BDD) | Dev Tooling | add-executable-specs |
| SLOW_RESPONSE detection (absolute threshold) | Phase 2.5A | phase-2-5-slow-response-detection |
| TIMEOUT_PROXIMITY detection (serverless) | Phase 2.5A | phase-2-5-slow-response-detection |
| Rule arbitration (TIMEOUT_PROXIMITY > SLOW_RESPONSE > LATENCY_SPIKE) | Phase 2.5A | phase-2-5-slow-response-detection |
| K8s p99 latency detection | Phase 2.5A | phase-2-5-slow-response-detection |
| ECS response time detection | Phase 2.5A | phase-2-5-slow-response-detection |
| Lambda timeout proximity detection | Phase 2.5A | phase-2-5-slow-response-detection |
| Azure App Service slow response detection | Phase 2.5B | phase-2-5-slow-response-detection |
| slack-notifications (Block Kit + approval buttons) | Phase 2.6 | phase-2-6-notification-integrations |
| teams-notifications (Adaptive Cards) | Phase 2.6 | phase-2-6-notification-integrations |
| pagerduty-escalation (Events API v2) | Phase 2.6 | phase-2-6-notification-integrations |
| opsgenie-escalation | Phase 2.6 | phase-2-6-notification-integrations |
| NotificationPort ABC | Phase 2.6 | phase-2-6-notification-integrations |
| EscalationPort ABC | Phase 2.6 | phase-2-6-notification-integrations |
| Notification fallback chain | Phase 2.6 | phase-2-6-notification-integrations |
| Severity-based notification routing | Phase 2.6 | phase-2-6-notification-integrations |
| dashboard-incident-feed (WebSocket real-time) | Phase 2.7 | phase-2-7-operator-dashboard |
| dashboard-confidence-viz (decomposition) | Phase 2.7 | phase-2-7-operator-dashboard |
| dashboard-timeline-view (drill-down) | Phase 2.7 | phase-2-7-operator-dashboard |
| dashboard-phase-tracker (graduation gates) | Phase 2.7 | phase-2-7-operator-dashboard |
| API endpoints for dashboard data | Phase 2.7 | phase-2-7-operator-dashboard |
| WebSocket incident stream | Phase 2.7 | phase-2-7-operator-dashboard |
| datadog-telemetry (all 4 query ABCs) | Phase 2.8 | phase-2-8-datadog-adapter |
| Datadog multi-site support | Phase 2.8 | phase-2-8-datadog-adapter |
| cloudwatch-telemetry-provider (bootstrap registration) | Phase 2.9 | phase-2-9-log-fetching-gap-closure |
| kubernetes-log-fallback (K8s API pod logs) | Phase 2.9 | phase-2-9-log-fetching-gap-closure |
| FallbackLogAdapter decorator | Phase 2.9 | phase-2-9-log-fetching-gap-closure |
| bridge-enrichment enabled by default | Phase 2.9 | phase-2-9-log-fetching-gap-closure |
| CanonicalLogEntry enrichment fix | Phase 2.9 | phase-2-9-log-fetching-gap-closure |
| New Relic log adapter test coverage | Phase 2.9 | phase-2-9-log-fetching-gap-closure |
| helm-deployment (production Helm chart) | Phase 3.1 | phase-3-1-helm-deployment |
| k8s-operator (lifecycle management) | Phase 3.1 | phase-3-1-helm-deployment |
| Phase-specific RBAC templates (Observe/Assist/Autonomous) | Phase 3.1 | phase-3-1-helm-deployment |
| gcp-cloud-operator (GKE + Functions + Run) | Phase 3.2 | phase-3-2-gcp-support |
| gcp-secrets (Secret Manager) | Phase 3.2 | phase-3-2-gcp-support |
| gcp-storage (Cloud Storage) | Phase 3.2 | phase-3-2-gcp-support |
| Tri-cloud portability (AWS + Azure + GCP) | Phase 3.2 | phase-3-2-gcp-support |
| cost-context-enrichment (non-blocking) | Phase 3.3 | phase-3-3-finops-remediation |
| kubecost-integration (CostProviderPort) | Phase 3.3 | phase-3-3-finops-remediation |
| CostEstimate in remediation audit trail | Phase 3.3 | phase-3-3-finops-remediation |
| Cost impact in HITL approvals | Phase 3.3 | phase-3-3-finops-remediation |
| persistence-data-model (10 durable entities) | Phase 4.0 | phase-4-0-persistence-reconciliation |
| outbox-delivery-contract (at-least-once + DLQ) | Phase 4.0 | phase-4-0-persistence-reconciliation |
| coordination-state-contract (AGENTS.md aligned) | Phase 4.0 | phase-4-0-persistence-reconciliation |
| architecture-reconciliation-adr (ADR-006) | Phase 4.0 | phase-4-0-persistence-reconciliation |
| split-gate-thresholds (6 quantitative triggers) | Phase 4.0 | phase-4-0-persistence-reconciliation |
| Cooldown state durability (Redis-backed) | Phase 4.0 | phase-4-0-persistence-reconciliation |
| Kill-switch state durability | Phase 4.0 | phase-4-0-persistence-reconciliation |
| PostgreSQL incident store (IncidentStorePort) | Phase 4.0 | phase-4-0-persistence-reconciliation |
| OutboxRelay (PG → Redis Streams) | Phase 4.0 | phase-4-0-persistence-reconciliation |
| CoordinationAuditPort + PostgresCoordinationAuditStore | Phase 4.0 | phase-4-0-persistence-reconciliation |
| architecture-alignment (report integration) | Documentation | integrate-alignment-report |
| ComputeMechanism enum + ServiceLabels refactor | Phase 1.5 (DONE) | archive/phase-1-5-non-k8s-platforms |
| serverless-anomaly-detection (cold-start suppression) | Phase 1.5 (DONE) | archive/phase-1-5-non-k8s-platforms |
| aws-remediation-adapters (ECS/EC2 ASG/Lambda) | Phase 1.5 (DONE) | archive/phase-1-5-non-k8s-platforms |
| azure-remediation-adapters (App Service/Functions) | Phase 1.5 (DONE) | archive/phase-1-5-non-k8s-platforms |
| CloudOperatorPort + CloudOperatorRegistry | Phase 1.5 (DONE) | archive/phase-1-5-non-k8s-platforms |
| agent-self-observability (Prometheus golden signals) | Phase 2.1 (DONE) | archive/phase-2-1-observability |
| slo-instrumentation (3 SLOs code-level) | Phase 2.1 (DONE) | archive/phase-2-1-observability |
| correlation-id-propagation (contextvars) | Phase 2.1 (DONE) | archive/phase-2-1-observability |
| real-healthz-probe (component checks) | Phase 2.1 (DONE) | archive/phase-2-1-observability |
| circuit-breaker-observability (state gauge) | Phase 2.1 (DONE) | archive/phase-2-1-observability |
| Prometheus alert rules (8 rules) | Phase 2.1 (DONE) | archive/phase-2-1-observability |

---

## Delivery Phase Summary

| Phase | Label | Status | Key Output |
|---|---|---|---|
| Foundation | All-phase spec | Planning | Master system specification (all capabilities) |
| Dev Tooling | add-executable-specs | Not Started | AsyncAPI YAML + Behave BDD infrastructure |
| Phase 1.5 | Non-K8s Platforms | **COMPLETED** (archived) | ComputeMechanism, AWS/Azure operators |
| Phase 2.1 | Observability | **COMPLETED** (archived) | Prometheus metrics, SLOs, alert rules |
| Phase 2.5 | Slow Response Detection | Not Started | 2.5A (K8s+AWS), 2.5B (Azure conditional) |
| Phase 2.6 | Notification Integrations | Not Started | Slack/Teams/PagerDuty/OpsGenie adapters |
| Phase 2.7 | Operator Dashboard | Not Started | React/Next.js SPA + WebSocket API |
| Phase 2.8 | Datadog Adapter | Not Started | Datadog telemetry provider |
| Phase 2.9 | Log Fetching Gap Closure | **PARTIALLY COMPLETE** | CloudWatch bootstrap, K8s fallback, enrichment fix |
| Phase 3.1 | Helm Deployment | Not Started | Production Helm chart + K8s Operator |
| Phase 3.2 | GCP Support | Not Started | Tri-cloud operator adapters |
| Phase 3.3 | FinOps Remediation | Not Started | Cost enrichment + kubecost adapter |
| Phase 4.0 | Persistence Reconciliation | **Gates 0-1 COMPLETE**, Gates 2-7 Not Started | Architecture reconciliation, durable persistence |
| Documentation | integrate-alignment-report | Not Started | Architecture alignment report moved |

---

## Open Questions / Clarifying Questions

1. **Phase 2.5B (Azure slow response)**: Is the Azure telemetry adapter (`AzureMonitorMetricsAdapter`) now available? Gate 0.2 check determines if 2.5B is blocked.
2. **Phase 2.6–2.9 execution order**: There is no explicit sequencing defined between phases 2.6, 2.7, and 2.8 — are they intended to be developed in parallel?
3. **Phase 2.9 lint debt**: Pre-existing repository-wide Ruff findings need to be resolved before the lint gate is green. Is there a tracking ticket?
4. **Phase 4.0 PostgreSQL extensions**: TimescaleDB ≥2.13.0 and pgvector ≥0.5.0 are required. Have these been validated in staging/production environments (Gate T040)?
5. **Helm chart and GCP (3.1 + 3.2) coordination**: Helm chart updates are needed for both GCP support and FinOps — should these be merged into a single chart release?
6. **Email notification adapter**: Noted as deferred in Phase 2.6 — which phase is it scheduled for?
7. **Jira ticket creation**: Defined in abstract spec (Section 11.6) and noted as deferred from Phase 2.6 — when is it planned?
8. **`add-executable-specs`**: This change has no phase assignment and appears to have zero tasks completed — is this intentionally deferred or should it be part of foundation work?
