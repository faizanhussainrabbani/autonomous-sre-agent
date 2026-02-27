# Autonomous SRE Agent — Engineering Standards

**Version:** 1.0.0 | **Companion to:** [constitution.md](./constitution.md)

> **Constitution** = what we value. **Engineering Standards** = how we build.

---

## 1. Software Architecture

### 1.1 Hexagonal Architecture (Ports & Adapters)

All external system interactions go through **port interfaces** with swappable **adapter implementations**. No core domain logic imports external SDKs directly.

```
                    ┌─────────────────────────────┐
                    │       CORE DOMAIN           │
                    │  (pure business logic)       │
                    │                              │
                    │  Detection │ Diagnostics     │
                    │  Remediation │ Safety        │
                    ├──────────┬───────────────────┤
                    │   PORTS  │  (interfaces)     │
                    ├──────────┴───────────────────┤
          ┌─────── │        ADAPTERS               │ ───────┐
          │        └───────────────────────────────┘        │
          ▼                    ▼                    ▼        ▼
    Telemetry            Kubernetes            LLM       Notification
    Adapters             Adapter              Adapter    Adapters
  ┌──────────┐        ┌──────────┐        ┌────────┐  ┌──────────┐
  │OTel │ NR │        │K8s Client│        │GPT│Llama│  │PD│Slack│Jira│
  └──────────┘        └──────────┘        └────────┘  └──────────┘
```

**Rules:**
- Core domain NEVER imports `kubernetes`, `openai`, `newrelic`, `pagerduty`, etc.
- All external calls go through port interfaces defined in the domain layer
- Adapters import external SDKs; core domain only knows the port interface
- **Apply to ALL integrations** — not just telemetry (K8s API, ArgoCD, vector DB, LLM, notification channels, secrets managers, object storage)

### 1.2 Domain-Driven Design (DDD) — Bounded Contexts

The system is organized into four bounded contexts with explicit interfaces between them:

```
┌──────────────────┐     ┌──────────────────┐
│  DETECTION        │────▶│  DIAGNOSTIC       │
│  Context          │     │  Context          │
│                   │     │                   │
│  • Telemetry      │     │  • RAG Pipeline   │
│  • Anomaly Det.   │     │  • LLM Reasoning  │
│  • Dep. Graph     │     │  • Severity Class. │
│  • Provider Abs.  │     │  • Confidence      │
│                   │     │                   │
│  Emits: AnomalyAlert   │  Emits: Diagnosis │
└──────────────────┘     └────────┬─────────┘
                                  │
┌──────────────────┐     ┌────────▼─────────┐
│  SAFETY           │────▶│  REMEDIATION      │
│  Context          │     │  Context          │
│                   │     │                   │
│  • Guardrails     │     │  • Action Exec.   │
│  • Kill Switch    │     │  • GitOps/ArgoCD  │
│  • Blast Radius   │     │  • Verification   │
│  • Audit Logging  │     │  • Rollback       │
│  • Agent Coord.   │     │  • Learning       │
│                   │     │                   │
│  Emits: AuthorizationDecision │  Emits: RemediationResult │
└──────────────────┘     └──────────────────┘
```

**Rules:**
- Contexts communicate via domain events, not direct method calls
- Each context owns its data — no shared databases between contexts
- Anti-corruption layers translate between context-specific models
- A context can be deployed and scaled independently

### 1.3 Saga Pattern — Incident Pipeline

The detect → diagnose → remediate → verify → learn pipeline is a **saga** with explicit compensation (rollback) at each step:

| Step | Action | Compensation (on failure) |
|------|--------|--------------------------|
| 1. Detect | Generate anomaly alert | N/A (read-only) |
| 2. Classify | Assign severity | N/A (read-only) |
| 3. Diagnose | RAG retrieval + LLM reasoning | Skip to escalation |
| 4. Validate | Second-opinion check | Escalate instead of act |
| 5. Authorize | Safety guardrail check | Block action, escalate |
| 6. Remediate | Execute action (restart, scale, rollback) | Rollback the action |
| 7. Verify | Monitor post-action metrics | Rollback + escalate |
| 8. Learn | Index resolved incident | Log failure, retry async |

**Rules:**
- Every step has a defined compensation/rollback
- The saga coordinator tracks state persistently — survives agent restarts
- Timeouts at every step with escalation behavior
- Full saga audit trail in immutable event store

### 1.4 CQRS (Command Query Responsibility Segregation)

| Concern | Query Side (Read) | Command Side (Write) |
|---------|-------------------|---------------------|
| **What** | Telemetry queries, RAG retrieval, dashboard reads | Remediation actions, audit writes, KB updates |
| **Scale** | High throughput, low latency, cacheable | Low throughput, high consistency, audited |
| **Consistency** | Eventually consistent acceptable | Strong consistency required |
| **Optimization** | Read-optimized data stores, materialized views | Write-ahead log, event sourcing |

### 1.5 Event Sourcing for Audit

Every agent decision and action is stored as an **immutable event**, not as mutable state:

```
IncidentDetected { anomaly_id, service, timestamp, metrics }
SeverityAssigned { incident_id, severity, scoring_breakdown }
DiagnosisGenerated { incident_id, hypothesis, confidence, evidence_ids }
SecondOpinionCompleted { incident_id, agreement: bool, validator_reasoning }
RemediationAuthorized { incident_id, action_type, blast_radius_estimate }
RemediationExecuted { incident_id, action, target, k8s_response }
VerificationStarted { incident_id, observation_window }
VerificationCompleted { incident_id, outcome: resolved|worsened|unchanged }
IncidentResolved { incident_id, total_duration, summary }
```

**Rules:**
- Events are append-only — never modified or deleted
- Current state is derived by replaying events (projections)
- Any audit question is answerable by querying the event stream

---

## 2. Industry Standards Alignment

### 2.1 NIST Incident Response Framework (SP 800-61)

Our pipeline maps to NIST's phases:

| NIST Phase | Our Implementation |
|---|---|
| **Preparation** | Phase 1: Telemetry + detection setup; KB population; baseline computation |
| **Detection & Analysis** | Anomaly detection + severity classification + RAG diagnostics |
| **Containment** | Safety guardrails: blast radius limits, canary execution, confidence gating |
| **Eradication** | Remediation engine: pod restart, scaling, rollback, cert rotation |
| **Recovery** | Post-remediation verification: metric monitoring, auto-rollback on degradation |
| **Lessons Learned** | Incident learning pipeline: indexing, runbook generation, accuracy tracking |

### 2.2 Google SRE Principles

| Principle | Our Implementation |
|---|---|
| **SLIs / SLOs** | `performance-slos` spec: end-to-end latency targets, per-stage bounds, 99.9% availability |
| **Error Budgets** | Phase regression: safety violations consume "trust budget"; enough violations → phase regression |
| **Toil Reduction** | Core purpose: automate 40-50% of repeatable incident response |
| **Blameless Post-Mortems** | Agent-generated resolution summaries; no blame attribution in reports |
| **Monitoring & Alerting** | Agent monitors itself (meta-observability, pipeline health, provider health) |
| **Release Engineering** | GitOps via ArgoCD for all deployment remediations |

### 2.3 12-Factor App (for the Agent Itself)

| Factor | Application |
|---|---|
| **I. Codebase** | Single repo, tracked in Git |
| **II. Dependencies** | Explicitly declared (requirements.txt / go.mod); no implicit system deps |
| **III. Config** | Cloud provider, telemetry provider, thresholds — all via env vars / config files, never hardcoded |
| **IV. Backing Services** | Vector DB, Prometheus, Jaeger, LLM API — all treated as attached resources via adapters |
| **V. Build/Release/Run** | Strict separation: Docker build → tagged release → K8s deploy |
| **VI. Processes** | Stateless agent processes; saga state in persistent store (DB/etcd) |
| **VII. Port Binding** | Each agent component exposes API via bound port |
| **VIII. Concurrency** | Scale by running N agent replicas with distributed locking |
| **IX. Disposability** | Fast startup, graceful shutdown (drain in-flight incidents) |
| **X. Dev/Prod Parity** | Same Docker images, same configs (except secrets) across environments |
| **XI. Logs** | Structured JSON logs to stdout; collected by OTel pipeline |
| **XII. Admin Processes** | Kill switch, phase transitions, config changes — via API, not SSH |

### 2.4 OTel Semantic Conventions

The canonical data model MUST align with [OpenTelemetry Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/):

| Convention | Our Canonical Model |
|---|---|
| `service.name` | `CanonicalMetric.labels.service` |
| `service.namespace` | `CanonicalMetric.labels.namespace` |
| `k8s.pod.name` | `CanonicalMetric.labels.pod` |
| `k8s.node.name` | `CanonicalMetric.labels.node` |
| `http.request.method` | Trace span attributes |
| `http.response.status_code` | Trace span attributes |

**Rule:** When our canonical model names differ from OTel semantic conventions, document the mapping explicitly.

---

## 3. Design Patterns Reference

### 3.1 Patterns Used Per Component

| Component | Patterns Applied |
|---|---|
| **Telemetry Ingestion** | Adapter, Pipeline/Filter, Observer, Bulkhead |
| **Anomaly Detection** | Strategy (detection algorithm selection), Observer (alert subscription), Sliding Window |
| **RAG Diagnostics** | Chain of Responsibility (retrieval → reasoning → validation), Template Method |
| **Remediation Engine** | Command (encapsulated actions), Saga (pipeline), Strategy (per-action-type execution) |
| **Safety Guardrails** | Decorator (wrap actions with checks), Chain of Responsibility (tier 1 → 2 → 3), Circuit Breaker |
| **Provider Abstraction** | Abstract Factory (provider creation), Adapter (protocol translation), Plugin/Registry |
| **Notifications** | Observer (event subscription), Strategy (per-channel delivery), Fallback Chain |

### 3.2 Circuit Breaker — Where Applied

| Component | Trigger | Open State Behavior |
|---|---|---|
| **Telemetry provider** | 3 consecutive API failures | Fall back to cached data; flag "degraded telemetry" |
| **LLM API** | 3 consecutive timeouts or errors | Escalate all incidents to humans; alert platform team |
| **Vector DB** | 3 consecutive query failures | Escalate; use fallback keyword search if available |
| **Notification channel** | 2 consecutive delivery failures | Activate fallback channel in priority order |
| **K8s API** | 5 consecutive failures | Halt all remediations; alert via all channels |

### 3.3 Bulkhead Pattern — Failure Isolation

Each bounded context runs in isolation. Failure in one context does NOT cascade:

| Failure | Impact Scope | Protected Contexts |
|---|---|---|
| Dashboard crash | Dashboard only | Detection, Diagnostics, Remediation, Safety all unaffected |
| Notification channel down | Notifications only | Detection, Diagnostics continue; remediation uses fallback channel |
| Vector DB failure | RAG diagnostics | Detection continues; incidents escalated to humans |
| LLM API outage | RAG diagnostics | Detection continues; incidents escalated to humans |

---

## 4. Development Practices

### 4.1 Testing Strategy — Test Pyramid

```
        ╱  E2E Tests  ╲          ~10% — Full pipeline (detect→resolve)
       ╱  Integration   ╲        ~30% — Cross-component (adapter+service)
      ╱    Unit Tests     ╲      ~60% — Pure functions, domain logic
     ╱─────────────────────╲
```

| Level | Scope | Target | Tools |
|---|---|---|---|
| **Unit** | Single function/class, no I/O | ≥90% line coverage on core domain | pytest, go test |
| **Integration** | Component + its adapters | Every adapter tested against real or containerized backend | pytest + testcontainers |
| **E2E** | Full pipeline in test cluster | All 5 incident types detected and handled correctly | K8s test cluster + chaos injection |
| **Chaos** | Production-like environment | Quarterly agent-disabled chaos day; random component failure injection | Chaos Mesh / Litmus |
| **Adversarial** | Security | Prompt injection via crafted logs; malformed telemetry | Custom red-team scripts |

**Coverage Targets:**
- Core domain logic: ≥90%
- Adapters: ≥80%
- Overall project: ≥85%

### 4.2 API-First Design

All inter-component communication is API-defined before implementation:

- **Internal APIs:** gRPC for inter-service communication (typed, fast, streaming support)
- **External APIs:** REST/JSON for operator-facing endpoints (config, dashboard, kill switch)
- **Event Bus:** Protobuf-serialized events on Kafka/NATS for async domain events
- **API Documentation:** OpenAPI 3.1 for REST; Protobuf `.proto` files for gRPC

**Rule:** API contract defined → consumer and provider tests written → then implement.

### 4.3 Git Workflow

**Trunk-Based Development** with short-lived feature branches:

```
main ─────●────●────●────●────●────●────●──▶
           ╲  ╱      ╲  ╱      ╲  ╱
            feat/     feat/     feat/
            AC-2.1.1  AC-2.3.1  AC-3.1.2
```

- Feature branches named by acceptance criteria ID (e.g., `feat/AC-2.1.1-metrics-collection`)
- PRs require: passing tests, code review, AC criteria linked
- Merge to `main` via squash commit
- Release tags follow semver: `v0.1.0` (Phase 1 MVP) → `v1.0.0` (Phase 3 Autonomous-ready)

### 4.4 CI/CD Pipeline

```
Push → Lint → Unit Tests → Build → Integration Tests → Security Scan → Deploy to Staging
                                                                              │
                                                          E2E Tests ◀─────────┘
                                                              │
                                                    Manual Approval (Sev 1-2 paths)
                                                              │
                                                        Deploy to Prod
```

**Gates (automated, non-bypassable):**
- Unit test coverage ≥ targets
- Zero critical/high security vulnerabilities
- Integration tests pass
- Docker image scanned (Trivy/Snyk)

### 4.5 Code Organization

```
sre-agent/
├── domain/                    # Core business logic (NO external imports)
│   ├── detection/             # Anomaly detection, baselines, correlation
│   ├── diagnostics/           # RAG reasoning, confidence scoring
│   ├── remediation/           # Action planning, saga coordination
│   ├── safety/                # Guardrails, kill switch, blast radius
│   └── models/                # Canonical data model, domain events
│
├── ports/                     # Interface definitions (abstract classes)
│   ├── telemetry.py           # MetricsQuery, TraceQuery, LogQuery
│   ├── kubernetes.py          # K8sClient interface
│   ├── llm.py                 # LLMReasoner interface
│   ├── vectordb.py            # VectorSearch interface
│   ├── notifications.py       # NotificationChannel interface
│   ├── secrets.py             # SecretsManager interface
│   └── storage.py             # ObjectStorage interface
│
├── adapters/                  # External system implementations
│   ├── telemetry/
│   │   ├── otel/              # Prometheus, Jaeger, Loki clients
│   │   └── newrelic/          # NerdGraph client
│   ├── kubernetes/            # K8s client-python wrapper
│   ├── gitops/                # ArgoCD adapter
│   ├── llm/
│   │   ├── openai/            # GPT adapter
│   │   └── anthropic/         # Claude adapter
│   ├── vectordb/
│   │   ├── pinecone/
│   │   └── weaviate/
│   ├── notifications/
│   │   ├── pagerduty/
│   │   ├── slack/
│   │   └── jira/
│   ├── secrets/
│   │   ├── vault/
│   │   ├── aws_sm/
│   │   └── azure_kv/
│   └── storage/
│       ├── s3/
│       ├── azure_blob/
│       └── minio/
│
├── api/                       # External-facing APIs
│   ├── rest/                  # Operator API (config, dashboard, kill switch)
│   └── grpc/                  # Internal inter-service API
│
├── config/                    # Configuration loading & validation
├── events/                    # Event store & bus
└── tests/
    ├── unit/
    ├── integration/
    ├── e2e/
    └── adversarial/
```

### 4.6 Dependency Injection

All adapters are injected at startup, never instantiated inside domain logic:

```python
# ✅ CORRECT — domain receives interface, doesn't know adapter
class AnomalyDetector:
    def __init__(self, metrics: MetricsQuery, graph: DependencyGraphQuery):
        self.metrics = metrics
        self.graph = graph

# ❌ WRONG — domain imports and creates adapter
class AnomalyDetector:
    def __init__(self):
        self.metrics = PrometheusClient("http://prometheus:9090")  # NO!
```

---

## 5. Operational Patterns

### 5.1 Health Checks & Probes

Every agent component exposes:

| Probe | Purpose | Endpoint |
|---|---|---|
| **Liveness** | "Am I running?" | `GET /healthz` → 200 if process alive |
| **Readiness** | "Can I serve traffic?" | `GET /readyz` → 200 if all port connections healthy |
| **Startup** | "Have I initialized?" | `GET /startupz` → 200 after config validated and adapters connected |

### 5.2 Graceful Shutdown

When an agent component receives `SIGTERM`:

1. Stop accepting new incidents/alerts (mark not-ready)
2. Complete in-flight saga steps (with 30-second deadline)
3. If deadline exceeded: persist saga state for another replica to resume
4. Release distributed locks
5. Flush pending events to event store
6. Exit

### 5.3 Rate Limiting & Backpressure

| Component | Rate Limit | Backpressure Strategy |
|---|---|---|
| **Telemetry ingestion** | No hard limit; buffer in Kafka | Drop oldest metrics if buffer full; flag "data loss" |
| **Anomaly detection** | Process alerts in real-time | Queue overflow → sample; alert on queue depth |
| **RAG queries** | Max 10 concurrent LLM calls | Priority queue by severity; timeout at 30s |
| **Remediation execution** | Max 3 concurrent actions | Queue with severity priority; block lower-sev until slot free |
| **Notification delivery** | Max 50 messages/minute per channel | Batch low-severity notifications; never batch Sev 1-2 |

### 5.4 Feature Flags

Individual capabilities can be toggled independently:

```yaml
feature_flags:
  ebpf_enabled: true
  multi_dimensional_correlation: true
  deployment_aware_detection: true
  proactive_scaling: false           # Phase 4 — disabled until ready
  architectural_recommendations: false
  new_relic_adapter: true
  otel_adapter: true
```

**Rules:**
- Feature flags for new capabilities start `false` and are enabled after testing
- Phase 4 (Predictive) capabilities are flag-guarded independently
- Flags are stored in config, not hardcoded; changeable without redeploy

---

## Governance

- This document is a companion to `constitution.md` — both apply simultaneously
- Constitution covers *principles and values*; this document covers *technical implementation*
- Updates require PR with rationale, review by 2 engineers, and impact assessment
- Architecture pattern changes (e.g., switching from hexagonal to layered) require RFC

**Version:** 1.0.0 | **Created:** 2026-02-25 | **Last Amended:** 2026-02-25
