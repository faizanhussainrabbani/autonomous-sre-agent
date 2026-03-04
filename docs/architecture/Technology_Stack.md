# Technology Stack: Autonomous SRE Agent

**Date:** February 25, 2026

---

## Stack Overview

```
┌───────────────────────────────────────────────────────────────────┐
│                        OPERATOR LAYER                            │
│  Dashboard (React/Next.js) │ Slack │ PagerDuty │ Jira            │
├───────────────────────────────────────────────────────────────────┤
│                      ORCHESTRATION LAYER                         │
│  Phased Rollout SM │ Severity Classifier │ Agent Coordinator     │
├───────────────────────────────────────────────────────────────────┤
│                      INTELLIGENCE LAYER                          │
│  LLM Reasoning │ RAG Pipeline │ Vector DB │ Confidence Scoring   │
├───────────────────────────────────────────────────────────────────┤
│                        ACTION LAYER                              │
│  K8s API │ ArgoCD/GitOps │ cert-manager │ Safety Guardrails      │
├───────────────────────────────────────────────────────────────────┤
│                       DETECTION LAYER                            │
│  ML Anomaly Detection │ Alert Correlation │ Dependency Graph     │
├───────────────────────────────────────────────────────────────────┤
│                       INGESTION LAYER                            │
│  OpenTelemetry Collector │ eBPF Programs │ Signal Correlator     │
├───────────────────────────────────────────────────────────────────┤
│                      INFRASTRUCTURE                              │
│  Kubernetes │ Linux (eBPF-capable) │ etcd/Redis │ Git/GitHub     │
└───────────────────────────────────────────────────────────────────┘
```

---

## 1. Telemetry & Observability

| Technology | Purpose | Phase | Notes |
|-----------|---------|-------|-------|
| **OpenTelemetry SDK** | Application-level instrumentation (metrics, logs, traces) | 1 | Vendor-neutral; requires >80% service coverage |
| **OpenTelemetry Collector** | Central telemetry collection and routing | 1 | Receives from OTel SDK, exports to backends |
| **Prometheus** | Metrics storage & querying | 1 | Receives via OTel Collector Prometheus receiver; or use **Grafana Mimir** for scalable long-term storage |
| **Jaeger** or **Grafana Tempo** | Distributed trace storage & querying | 1 | Receives traces via OTLP exporter |
| **Loki** or **Elasticsearch** | Log storage & querying | 1 | Structured log indexing with trace ID correlation |
| **Fluentd** or **Vector** | Log collection & forwarding | 1 | Feeds into OTel Collector or directly to log backend |
| **eBPF** (via **Cilium** or **Pixie**) | Kernel-level telemetry: syscalls, network flows, process behavior | 1 | Requires Linux kernel 5.8+ (BTF support); ~1-2% CPU overhead |
| **Grafana** | Visualization & dashboarding (operational metrics) | 1 | Optional alongside the custom operator dashboard |

---

## 2. AI & Machine Learning

| Technology | Purpose | Phase | Notes |
|-----------|---------|-------|-------|
| **LLM Provider** *(decision pending)* | Root cause hypothesis generation, reasoning engine | 2 | Options: **GPT-4o/GPT-5** (cloud API), **Claude** (cloud API), **Llama 3** (self-hosted). Trade-off: latency vs. cost vs. privacy |
| **Vector Database** *(decision pending)* | Semantic similarity search for RAG pipeline | 2 | Options: **Pinecone** (managed, scalable), **Weaviate** (self-hosted, flexible), **Chroma** (lightweight, dev-friendly) |
| **Embedding Model** | Convert incident data to vectors for similarity search | 2 | Options: **OpenAI text-embedding-3-large**, **Cohere Embed v3**, **sentence-transformers** (self-hosted) |
| **Scikit-learn** / **Prophet** / **PyTorch** | ML anomaly detection on streaming time-series | 1 | Statistical models (Isolation Forest, ARIMA) for baseline; optionally deep learning for multi-dimensional correlation |
| **LangChain** or **LlamaIndex** | LLM orchestration framework for RAG pipeline | 2 | Chain management: retrieval → context injection → prompt construction → reasoning → output parsing |

---

## 3. Kubernetes & Container Orchestration

| Technology | Purpose | Phase | Notes |
|-----------|---------|-------|-------|
| **Kubernetes** | Primary compute platform; target of all remediation actions | All | Required: RBAC-configured service accounts, Metrics Server |
| **Kubernetes API (client-go / Python client)** | Pod restart, HPA scaling, deployment queries | 3 | Least-privilege service accounts per action type |
| **ArgoCD** | GitOps-based deployment rollback via Git revert | 3 | Deterministic, auditable rollbacks; integrated with Git |
| **Flux** *(alternative to ArgoCD)* | GitOps alternative | 3 | Same GitOps model; choose one |
| **cert-manager** | Certificate lifecycle management (issuance, rotation, renewal) | 3 | Integrated with Let's Encrypt / Vault PKI |
| **Helm** | Application packaging and deployment templating | All | For deploying the SRE agent itself and its dependencies |

---

## 3.5 Cloud Provider Remediation (Phase 1.5)

| Technology | Purpose | Phase | Notes |
|-----------|---------|-------|-------|
| **boto3** (AWS SDK) | ECS task restart, EC2 ASG scaling, Lambda concurrency | 1.5 | Optional dependency (`pip install sre-agent[aws]`). Requires IAM roles for ECS, ASG, Lambda access |
| **azure-mgmt-web** (Azure SDK) | App Service restart/scaling, Azure Functions restart/scaling | 1.5 | Optional dependency (`pip install sre-agent[azure]`). Requires Azure RBAC with Web Plan Contributor role |

---

## 4. Data Infrastructure

| Technology | Purpose | Phase | Notes |
|-----------|---------|-------|-------|
| **etcd** or **Redis** | Distributed locking for multi-agent coordination | 4 | Mutual exclusion on remediated resources; lock TTLs |
| **PostgreSQL** or **MySQL** | Relational metadata: incident records, audit logs, configuration, phase state | 3 | Stores severity classifications, phase transitions, agent state |
| **Object Storage** (S3/GCS/MinIO) | Long-term storage of audit logs, incident records, post-mortems | 3 | Immutable, tamper-evident audit trail |
| **Apache Kafka** or **NATS** | Event streaming for telemetry pipeline and inter-component communication | 1 | High-throughput message bus between collection → detection → diagnostics |

---

## 5. Security & Access Control

| Technology | Purpose | Phase | Notes |
|-----------|---------|-------|-------|
| **HashiCorp Vault** or **AWS Secrets Manager** | Secrets management (API keys, DB credentials, LLM tokens) | 3 | No direct credential storage in agent code or config |
| **Kubernetes RBAC** | Scoped permissions per agent action type | 3 | Separate service accounts for read-only, pod-restart, scaling, rollback |
| **OPA (Open Policy Agent)** *(optional)* | Policy enforcement for blast radius limits and action authorization | 3 | Declarative policy: "never restart >20% of pods" |
| **Falco** *(optional)* | Runtime security monitoring for the agent itself | 5 | Detects anomalous agent behavior (unexpected API calls, privilege escalation) |

---

## 6. Notification & Integration

| Technology | Purpose | Phase | Notes |
|-----------|---------|-------|-------|
| **PagerDuty API** | On-call escalation for human-required incidents | 5 | Structured incident payloads with diagnosis, confidence, evidence |
| **Slack API** (Bolt/Web API) | Incident channel notifications with action buttons | 5 | Approve/reject/investigate actions; resolution summaries |
| **Jira API** | Post-incident ticket creation for Sev 1-2 incidents | 5 | Links to full audit trail and telemetry data |
| **Email (SMTP/SES)** | Fallback notification channel | 5 | Used when primary channels (PagerDuty/Slack) are unreachable |

---

## 7. Frontend & Dashboard

| Technology | Purpose | Phase | Notes |
|-----------|---------|-------|-------|
| **React** or **Next.js** | Operator dashboard UI framework | 5 | Real-time agent status, confidence visualization, timeline drill-down |
| **D3.js** or **Recharts** | Data visualization (charts, graphs, timelines) | 5 | Confidence score decomposition, accuracy trends, graduation gate progress |
| **WebSocket** or **Server-Sent Events** | Real-time dashboard updates | 5 | Live incident status, active remediation tracking |
| **Tailwind CSS** or **Chakra UI** | UI styling framework | 5 | Responsive, accessible design |

---

## 8. Development & CI/CD

| Technology | Purpose | Phase | Notes |
|-----------|---------|-------|-------|
| **Python 3.11+** | Primary language for agent backend, ML pipeline, RAG | All | LangChain/LlamaIndex ecosystem, K8s client, scikit-learn |
| **Go** *(optional)* | High-performance components (signal correlator, eBPF loader) | 1 | Better for low-latency telemetry pipeline components |
| **TypeScript** | Dashboard frontend | 5 | React/Next.js ecosystem |
| **Docker** | Containerization of all agent components | All | Multi-stage builds for production images |
| **GitHub Actions** or **GitLab CI** | CI/CD pipeline for agent code | All | Test → Build → Deploy; integration test gates |
| **pytest** | Python test framework | All | Unit + integration tests for all agent components |
| **OpenSpec** | Spec-driven development (requirements, scenarios) | All | Already initialized; defines acceptance criteria |
| **Spec Kit** | Phase-wise implementation planning (constitution, plans, tasks) | All | Already initialized; defines execution order |

---

## 9. Specification & Planning Tools

| Technology | Purpose | Status |
|-----------|---------|--------|
| **OpenSpec** (`@fission-ai/openspec`) | Spec authoring, change tracking, scenario definitions | ✅ Installed & 4/4 artifacts complete |
| **Spec Kit** (`github/spec-kit`) | Phase-wise execution planning, constitution, task breakdown | ✅ Installed & constitution created |
| **uv** | Python package manager (for Spec Kit CLI) | ✅ Installed v0.10.6 |
| **Node.js** | Runtime for OpenSpec CLI | ✅ v24.3.0 |

---

## 10. Provider Abstraction Layer

The agent uses a **provider-agnostic architecture** with adapters for different telemetry backends and cloud providers.

### Telemetry Backend Adapters

```
┌─────────────────────────────────────────────────────────┐
│              Agent Core (provider-agnostic)              │
│  Anomaly Detection │ RAG Diagnostics │ Remediation       │
│                                                          │
│  Uses ONLY canonical data model — never calls provider   │
│  APIs directly                                           │
├──────────────────────┬───────────────────────────────────┤
│   Canonical Data Model (metrics, traces, logs, events)   │
├──────────────────────┴───────────────────────────────────┤
│         Provider Abstraction Layer (plugin interface)     │
├─────────────────────┬────────────────────────────────────┤
│  OTel Adapter       │  New Relic Adapter                 │
│  ├─ Prometheus API  │  ├─ NerdGraph/NRQL API             │
│  ├─ Jaeger/Tempo    │  ├─ Distributed Tracing API        │
│  ├─ Loki API        │  ├─ Logs API                       │
│  └─ Trace-derived   │  └─ Service Maps API               │
│     dep. graph      │     dep. graph                      │
└─────────────────────┴────────────────────────────────────┘
  Future: Datadog │ Splunk │ Dynatrace adapters
```

| Adapter | Metrics | Traces | Logs | Dep Graph | Status |
|---------|---------|--------|------|-----------|--------|
| **OTel/Prometheus/Jaeger/Loki** | PromQL | Jaeger/Tempo API | LogQL | Trace-derived | Planned (Phase 1) |
| **New Relic** | NRQL/NerdGraph | NerdGraph | NerdGraph | Service Maps API | Planned (Phase 1) |
| **Datadog** | Metrics API v2 | APM API | Logs API | Service Map API | Future |
| **Splunk** | SPL | — | SPL | — | Future |

### Multi-Cloud Adapters

| Cloud Service | AWS | Azure | Self-Managed |
|--------------|-----|-------|--------------|
| **Kubernetes** | EKS | AKS | kubeadm/k3s/Rancher |
| **Secrets** | Secrets Manager / SSM | Key Vault | HashiCorp Vault |
| **Object Storage** | S3 | Blob Storage | MinIO (S3-compatible) |
| **IAM/Auth** | IRSA (IAM Roles for SA) | Workload Identity | K8s ServiceAccount |
| **Certificate** | ACM + cert-manager | App Gateway + cert-manager | cert-manager + Let's Encrypt |
| **Encryption** | KMS | Azure KMS | Vault Transit |

---

## Open Technology Decisions

| Decision | Options | Criteria | When to Decide |
|----------|---------|----------|---------------|
| **LLM Provider** | GPT-4o/5, Claude, Llama 3 (self-hosted) | Latency, cost, data privacy, model quality | Before Phase 2 (Month 4) |
| **Vector Database** | Pinecone, Weaviate, Chroma | Scale, operational preference, self-hosted vs. managed | Before Phase 2 (Month 4) |
| **Embedding Model** | OpenAI, Cohere, sentence-transformers | Cost, quality, self-hosted requirement | Before Phase 2 (Month 4) |
| **Log Backend** | Loki vs. Elasticsearch | Query complexity needs, operational cost | Phase 1 (Month 1) |
| **Trace Backend** | Jaeger vs. Grafana Tempo | Scale, integration with existing Grafana stack | Phase 1 (Month 1) |
| **Event Streaming** | Kafka vs. NATS | Throughput needs, operational complexity | Phase 1 (Month 1) |

---

## Infrastructure Prerequisites (Before Phase 1)

| Prerequisite | Requirement |
|-------------|-------------|
| OpenTelemetry | Deployed across >80% of services |
| Linux Kernels | eBPF-capable (5.8+ with BTF support) on all cluster nodes |
| Kubernetes | Cluster access with RBAC service accounts configured |
| GitOps | ArgoCD or Flux operational with Git-based deployment pipeline |
| Secrets Vault | HashiCorp Vault or AWS Secrets Manager provisioned |
| Incident History | Minimum 6 months of searchable incidents with post-mortems |
| Service Catalog | Service tier classification (Tier 1-3) defined |
| On-Call System | PagerDuty/OpsGenie configured with escalation policies |

---

*Source: [design.md](../openspec/changes/autonomous-sre-agent/design.md), [proposal.md](../openspec/changes/autonomous-sre-agent/proposal.md), [constitution.md](../.specify/memory/constitution.md)*
