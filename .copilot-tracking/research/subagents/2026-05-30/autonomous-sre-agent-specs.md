# Research: Autonomous SRE Agent — Sub-Spec Deep-Dive

**Research Date:** 2026-05-30  
**Status:** Complete  
**Files Read:** 19 spec files across 16 sub-spec directories + `tasks.md`, `design.md`, `proposal.md`

---

## Table of Contents

1. [Top-Level Context](#top-level-context)
2. [Sub-Spec Analyses](#sub-spec-analyses)
   - [agent-coordination](#1-agent-coordination)
   - [anomaly-detection](#2-anomaly-detection)
   - [cloud-portability](#3-cloud-portability)
   - [incident-learning](#4-incident-learning)
   - [notifications](#5-notifications)
   - [operator-dashboard](#6-operator-dashboard)
   - [performance-slos](#7-performance-slos)
   - [phased-rollout](#8-phased-rollout)
   - [predictive-capabilities](#9-predictive-capabilities)
   - [provider-abstraction](#10-provider-abstraction)
   - [rag-diagnostics](#11-rag-diagnostics)
   - [remediation-engine](#12-remediation-engine)
   - [safety-guardrails](#13-safety-guardrails)
   - [severity-classification](#14-severity-classification)
   - [telemetry-ingestion](#15-telemetry-ingestion)
   - [token-optimization](#16-token-optimization)
3. [Complete Tasks.md Task List](#complete-tasksmd-task-list)
4. [Master Requirements Matrix](#master-requirements-matrix)
5. [Gap Analysis](#gap-analysis)

---

## Top-Level Context

### Proposal Summary

**Goal:** Autonomous incident response system targeting 40–50% MTTR reduction. Greenfield system — no modified capabilities.

**Core Pipeline:** Detect → Investigate → Diagnose → Remediate → Learn

**Scope:** Kubernetes (EKS, AKS, self-managed), AWS (ECS, Lambda, EC2 ASG), Azure (App Services, Functions)

**Technology Stack:**
- Python 3.11+, FastAPI, anyio, httpx, structlog
- LangChain-style RAG orchestration, OpenAI + Anthropic LLM adapters
- ChromaDB (dev), pgvector/Pinecone/Weaviate (prod)
- Redis Streams (event bus), Redis/etcd (distributed locks)
- OpenTelemetry SDK, eBPF (Cilium/Pixie)
- ArgoCD/Flux for GitOps

### Design Decisions (from design.md)

| Decision | Choice | Rationale |
|---|---|---|
| Telemetry | OpenTelemetry + eBPF | Vendor-neutral + kernel-level depth |
| Diagnosis | RAG over fine-tuned LLM | Dynamic knowledge, provenance tracking |
| Confidence | Evidence-weighted (structural) | LLMs are poorly calibrated self-reporters |
| Deployment Rollback | GitOps via ArgoCD | Auditable, deterministic, version-controlled |
| Multi-agent coordination | Distributed locks (no centralized orchestrator) | No SPOF, leverages existing etcd/Redis |

### Open Questions (unresolved in design.md)

1. LLM provider selection (self-hosted vs cloud API) — unresolved
2. Vector database selection (Pinecone vs Weaviate vs Chroma) — unresolved
3. Blast radius threshold tuning — empirical, needs Phase 1 data
4. Phase graduation authority — RACI undefined ("engineering leadership + SRE team lead + on-call SRE rotation?")

---

## Sub-Spec Analyses

---

### 1. agent-coordination

**System Area:** Multi-agent mutual exclusion and conflict resolution

**Key Requirements:**

1. Acquire distributed lock on any resource being actively remediated (pod, deployment, service)
2. Enforce agent priority hierarchy: Security (1) > SRE (2) > Cost Optimization (3)
3. Release lock after successful remediation + post-action verification
4. Auto-release lock after configurable maximum duration (stalled remediation)
5. Block lower-priority agents from modifying locked resources
6. Cancel SRE actions when Security agent preempts (with notification)
7. Detect oscillation: same resource scaled up/down >3 times within 30-minute window
8. Halt all agent actions on oscillating resource
9. Alert human operators with full oscillation context
10. Require manual human intervention to resume agent operations on oscillating resource

**Required Interfaces / Classes:** Not explicitly named in this spec — deferred to `AGENTS.md` Lock Protocol schema (see below). The lock schema is fully defined:

```json
{
  "agent_id": "sre-agent-prod-01",
  "resource_type": "deployment",
  "resource_name": "checkout-service",
  "namespace": "prod",
  "compute_mechanism": "KUBERNETES",
  "resource_id": "deployment/checkout-service",
  "provider": "kubernetes",
  "priority_level": 2,
  "acquired_at": "...",
  "ttl_seconds": 180,
  "fencing_token": 948271
}
```

Non-K8s key format: `cooldown:{provider}:{compute_mechanism}:{resource_id}`

**Acceptance Criteria:**
- Lock acquired before any remediation action begins
- Lock released within configured TTL on stalled remediations
- Higher-priority agent preempts lower-priority lock deterministically
- Oscillation detected and halted after 3 contradictory actions in 30 min
- Human notification sent on every preemption and oscillation halt

**Implementation Complexity:** Medium  
**Spec Completeness:** Medium — behavioral scenarios defined, but no named interface/class definitions, no explicit module file paths. Defers implementation detail to `remediation-engine/plan.md` (CooldownEnforcer, KillSwitch)

---

### 2. anomaly-detection

**System Area:** ML-based anomaly detection on streaming time-series telemetry

**Key Requirements:**

1. Alert generated within 60 seconds when p99 latency exceeds 3σ from rolling baseline for >2 min
2. Alert generated within 30 seconds when error rate increases >200% from baseline
3. Distinguish 4xx vs 5xx in error rate alerts
4. Suppress alerts for metric perturbations lasting <30 seconds (planned deployments)
5. Log suppression with reasoning for audit
6. Allow per-service, per-metric-type sensitivity configuration
7. Sensitivity changes take effect within 5 minutes
8. Correlate related anomalies from dependency-connected services into a single incident
9. Alert within 120 seconds for memory/disk/cert resource exhaustion conditions
10. Alert when pod memory >85% of limit for >5 min with increasing trend; include projected OOM time
11. Alert when disk >80% or projected full within 24 hours; include growth rate
12. Alert when TLS cert within 14 days of expiry; escalate if within 3 days
13. Detect multi-dimensional anomaly: multiple sub-threshold shifts on same service within 5 min
14. Flag anomaly as "potentially deployment-induced" if within 60 min of deployment to service/dependency
15. Do NOT flag unrelated services as deployment-induced

**Required Interfaces / Classes:**

- `AnomalyDetector` → `src/sre_agent/domain/detection/anomaly_detector.py`
- `BaselineService` → `src/sre_agent/domain/detection/baseline.py`

**Acceptance Criteria:**
- Latency spike alert within 60s
- Error rate alert within 30s
- Resource exhaustion alert within 120s
- Multi-dimensional correlation fires when both sub-threshold metrics shift together
- Deployment context included in alert when within blast radius window
- Alert suppression logs captured for audit

**Implementation Complexity:** High  
**Spec Completeness:** High — 7 requirements, 12 scenarios, precise numeric thresholds, named implementation files

---

### 3. cloud-portability

**System Area:** Multi-cloud deployment support (EKS, AKS, self-managed Kubernetes)

**Key Requirements:**

1. All K8s API interactions use standard client — no cloud-specific code in core logic
2. Cloud-specific integrations (IAM, storage) handled via cloud provider adapter only
3. Secrets retrieved via cloud-native secrets manager based on configured provider
4. AWS: retrieve via Secrets Manager or SSM Parameter Store; use AWS-managed rotation
5. Azure: retrieve via Key Vault; authenticate via Managed Identity or Workload Identity Federation
6. HashiCorp Vault: universal option that works on all clouds
7. Audit logs stored via storage-agnostic interface (S3, Azure Blob, MinIO)
8. AWS: S3 with KMS encryption; Azure: Blob with SSE; Self-managed: MinIO (S3-compatible API)
9. AWS: authenticate via IRSA; no long-lived credentials
10. Azure: authenticate via Workload Identity Federation; no long-lived credentials
11. Self-managed: K8s-native service accounts; external creds from secrets manager
12. Cloud provider config validated on startup before accepting incidents
13. AWS config: region, EKS cluster name, S3 bucket, Secrets Manager prefix, optional IAM role ARN
14. Azure config: subscription ID, resource group, AKS cluster name, Blob container, Key Vault name, Managed Identity client ID
15. "None/self-managed" mode: K8s-native resources only; log warning about missing cloud features
16. Cross-cloud integration tests required: identical agent behavior on EKS, AKS, self-managed K8s

**Required Interfaces / Classes:**

- Cloud Provider Adapter (abstract port + concrete AWS/Azure/None adapters)
- SecretsPort (implied)
- ObjectStoragePort (implied)
- IAMAuthPort (implied)

**Acceptance Criteria:**
- Agent deploys and operates on EKS, AKS, and self-managed K8s without core code changes
- No long-lived credentials in configuration for cloud environments
- Startup fails fast on invalid cloud provider configuration
- Audit log encryption uses cloud-native KMS/SSE
- Cross-cloud integration test suite passes

**Implementation Complexity:** High  
**Spec Completeness:** High — 16 requirements, detailed scenario specifications, references a Phase 3.2 GCP extension in cross-references

---

### 4. incident-learning

**System Area:** Continuous learning pipeline — indexing incidents, generating runbooks, accuracy tracking

**Key Requirements:**

1. Index resolved incidents (agent or human) into vector database within 15 minutes of resolution
2. Structured incident record: root cause, symptoms, telemetry patterns, actions, TTR, outcome
3. Prompt human responders for root cause + remediation details on human-resolved escalations
4. Index human feedback to improve future diagnostic retrieval
5. Generate runbook draft when 3+ incidents with same root cause use the same remediation steps
6. Runbook drafts flagged for human review before production KB insertion
7. Notify reviewer via configured notification channel
8. Block agent-generated runbooks from production KB until human approved
9. Track correct/incorrect diagnosis counts per incident category
10. Record human override details (agent original + human corrected diagnosis)
11. Use override corrections as retrieval relevance training signal
12. Route configurable % (default 20%) of agent-capable incidents to human (random selector)
13. In shadow mode during human-routed incidents; record agent diagnosis for comparison
14. Enforce minimum 2 manually-handled incidents per on-call shift

**Required Interfaces / Classes:** None named explicitly in this spec.

**Acceptance Criteria:**
- Resolved incident indexed in vector DB within 15 minutes
- Runbook generation triggers after ≥3 same-pattern incidents
- Generated runbook not visible to agent until human-reviewed
- Override corrections captured and associated with incorrect category
- 20% routing rate measurable over time
- On-call quota (≥2 manual per shift) enforced

**Implementation Complexity:** Medium  
**Spec Completeness:** Medium-High — 4 requirements, 10 scenarios, good behavioral coverage, but no named interfaces or module paths

---

### 5. notifications

**System Area:** Multi-channel notification delivery for escalations, approvals, summaries

**Key Requirements:**

1. Trigger PagerDuty incident on escalation with: summary, diagnosis, confidence score, evidence citations, telemetry links
2. Post structured Slack message on escalation with: severity, service, hypothesis, evidence summary, action buttons (approve/reject/investigate)
3. Fallback to next priority channel when primary channel unreachable
4. Halt autonomous actions and log if ALL channels fail; require human acknowledgment
5. Send PR notification (Slack + email) for Sev 1-2 rollback approval with: diagnosis, blast radius, expected rollback impact
6. Re-escalate after configurable timeout (default 15 min) if approval not responded to
7. Simultaneously escalate to secondary on-call/team lead on approval timeout
8. Post resolution summary to incident Slack channel within 5 minutes of resolution
9. Summary content: timeline, root cause, remediation actions, post-action metric validation, total resolution time
10. Create Jira ticket for Sev 1-2 incidents linking audit trail, telemetry, and agent reasoning
11. Allow per-severity notification routing configuration
12. Routing config changes take effect within 2 minutes
13. Generate internal alert to platform ops on channel health failure
14. Auto-activate fallback channel on channel health failure

**Required Interfaces / Classes:**

- `NotificationPort` (implied — referenced in remediation-engine spec)
- PagerDuty adapter
- Slack adapter
- Jira adapter
- Phase 2.6 (separate OpenSpec): Slack/Teams/PagerDuty/OpsGenie adapter implementations

**Acceptance Criteria:**
- Escalation delivered to primary channel
- Fallback triggered within 30s of primary failure
- All channels failing → autonomous actions halted
- Approval timeout re-escalation fires at 15 min
- Sev 1-2 Jira ticket created post-resolution
- Severity routing config effective within 2 min

**Implementation Complexity:** Medium  
**Spec Completeness:** High — 4 requirements, detailed scenarios, numeric SLOs, references Phase 2.6 for adapter implementations

---

### 6. operator-dashboard

**System Area:** Real-time operational dashboard for SRE leadership

**Key Requirements:**

1. Display current operational phase (Observe/Assist/Autonomous/Predictive)
2. Show graduation criteria progress for next phase (% completion per criterion)
3. Show each active incident: service, severity, current stage, confidence score, elapsed time
4. Kill switch status: prominent visual indicator, timestamp, activator identity, reason
5. Incident confidence drill-down: trace correlation strength, timeline match quality, RAG retrieval similarity, second-opinion validator agreement
6. Color-coded per-component confidence breakdown (green/yellow/red)
7. Rolling chart of average confidence scores over time + human override rate overlay
8. Overall accuracy: total evaluated, correct, incorrect, percentage
9. Accuracy breakdown by incident category (OOM, traffic spike, deployment regression, cert expiry, disk exhaustion)
10. Agent vs. human side-by-side comparison view (Observe/Assist modes)
11. Per-incident chronological timeline: alert trigger, queries, RAG docs retrieved (with similarity), hypotheses, confidence at each step, remediation actions, metric changes, resolution
12. Timeline entries expandable to full detail
13. Graduation gate progress tracker: each criterion with current vs required, green/red status

**Required Interfaces / Classes:** None explicitly named — UI/frontend component, API endpoints implied

**Acceptance Criteria:**
- All four operational modes displayed
- Kill switch status immediately visible on activation
- Confidence breakdown available per-incident
- Accuracy dashboard shows per-category rates
- Graduation gate progress shows real-time criteria completion

**Implementation Complexity:** High (frontend heavy)  
**Spec Completeness:** Medium — behavioral requirements well defined, but no API contracts, no frontend tech stack specified, no wireframes referenced

---

### 7. performance-slos

**System Area:** End-to-end latency and availability SLOs for the agent pipeline

**Key Requirements & Numeric Targets:**

| Stage | Target |
|---|---|
| Sev 3-4 detect → remediation initiation | ≤ 5 minutes |
| Sev 3-4 detect → verified resolution | ≤ 15 minutes |
| Sev 1-2 detect → proposal delivery | ≤ 5 minutes |
| Latency spike alert generation | within 60 seconds |
| Error rate surge alert generation | within 30 seconds |
| Proactive resource alert | within 120 seconds |
| RAG retrieval (normal load, ≤3 concurrent) | ≤ 500ms |
| Full LLM reasoning chain (normal load) | ≤ 10 seconds |
| RAG retrieval (high load, 10+ concurrent) | ≤ 1 second (2× normal) |
| Full LLM reasoning (high load) | ≤ 20 seconds (2× normal) |
| RAG query absolute timeout | 30 seconds |
| Pod restart K8s API call | within 5 seconds of approval |
| Post-restart monitoring start | within 10 seconds of restart |
| GitOps revert commit creation | within 10 seconds |
| ArgoCD reconciliation start | within 60 seconds of commit |
| HPA patch application | within 5 seconds |
| Pod scheduling start | within 30 seconds of HPA patch |
| Post-remediation verification window | 3–10 minutes (configurable) |
| Escalation notification delivery | within 15 seconds (primary channel) |
| Fallback notification attempt | within 30 seconds of primary failure |
| Resolution summary delivery | within 5 minutes of resolution |
| System availability | 99.9% (≤43 min/month downtime) |

**Additional Requirements:**
- Per-stage timestamped tracking: detection, diagnosis start, RAG query complete, LLM complete, confidence scored, second-opinion complete, remediation initiated, verification started, resolution confirmed
- Severity-based incident queue (Sev 1 processed first under load)
- RAG timeout → escalate to human with "diagnostic timeout" message
- Graceful degradation: core pipeline continues when non-critical subsystems fail
- SLO violation alerting: internal alert on any stage exceeding target

**Required Interfaces / Classes:**
- Latency instrumentation decorators/middleware
- SLO violation alerter
- References: `docs/architecture/architecture.md`, `docs/operations/slos_and_error_budgets.md`

**Acceptance Criteria:**
- All numeric latency SLOs met under stated load conditions
- Stage latencies visible on operator dashboard
- SLO breach fires internal alert
- 99.9% availability measured over rolling 30-day window

**Implementation Complexity:** Medium-High  
**Spec Completeness:** Very High — all SLOs quantified, scenarios for each stage, load conditions specified

---

### 8. phased-rollout

**System Area:** Four-phase operational mode orchestration with graduation gates

**Key Requirements:**

1. Four modes: Observe, Assist, Autonomous, Predictive — only one active at a time
2. Default: Observe mode on first deployment
3. In Observe: produce recommendations, NO remediation actions; log all for comparison
4. Operator mode change logged with timestamp, operator identity, reason
5. Shadow mode: track agent recommendation vs human decision; record match/mismatch per category
6. Assist mode: auto-execute Sev 3-4 (subject to guardrails); propose + require human approval for Sev 1-2
7. Observe mode: NO autonomous actions regardless of severity
8. **Observe → Assist graduation gate:** accuracy ≥90% vs human, min 100 incidents evaluated, zero false-positive destructive recommendations, KB coverage verified for top 20 incident types
9. **Assist → Autonomous graduation gate:** Sev 3-4 resolution rate ≥95%, zero blast-radius breaches over 60 consecutive days, human override rate for Sev 1-2 proposals <15%, no agent action worsened an incident
10. **Autonomous → Predictive graduation gate:** autonomous resolution rate ≥98%, all agent-generated runbooks reviewed by SRE team, quarterly chaos day completed, no multi-agent conflicts detected
11. Dual sign-off required for phase advancement: engineering leadership AND on-call SRE team lead
12. Both approvals logged with identity and timestamp
13. Automatic regression to lower phase on safety violations (blast-radius breach, agent-worsened incident)
14. After regression: must re-satisfy graduation criteria before returning to higher phase

**Required Interfaces / Classes:**

- `OperationalModeStateMachine` (phase state machine)
- `GraduationGateEvaluator`
- `PhaseMetrics` (referenced in remediation tasks as `PhaseGate`)

**Acceptance Criteria:**
- System starts in Observe mode by default
- All graduation gates enforced; transition blocked if any criterion unmet
- Dual sign-off recorded before transition executes
- Automatic regression triggers on safety violation without manual intervention

**Implementation Complexity:** Medium-High  
**Spec Completeness:** High — 6 requirements, detailed graduation criteria per gate, regression logic defined

---

### 9. predictive-capabilities

**System Area:** Phase 4 (Predictive mode) proactive intelligence capabilities

**Key Requirements:**

1. Predict disk exhaustion: compute projected time-to-full; alert if <72h; preemptive remediation if <24h
2. Detect memory leak trend: consistent upward trend over 4+ hours projecting OOM within 12h; alert with trend regression data
3. Predict connection pool exhaustion: trending toward 90% pool limit within 2h
4. Track TLS cert expiry: schedule rotation at 14 days, escalate if rotation fails
5. Track API key/token expiry: alert responsible team at 7 days
6. Learn recurring traffic patterns (daily, weekly, monthly): preemptive scale 15 min before predicted spike
7. Detect event-driven traffic correlations (deployment, campaigns, scheduled jobs)
8. Scale-down only after confirming spike has subsided
9. Prediction accuracy feedback loop: track hit/miss/magnitude; disable pattern if accuracy <70% over 30 days
10. Detect slow p50 latency degradation: >5% week-over-week for 3 consecutive weeks
11. Detect error rate creep: >2% month-over-month for 2 consecutive months
12. Correlate degradation with code changes, dependency updates, infra changes
13. Architectural recommendations: when same root cause generates 5+ incidents in 90 days
14. Include: recurring pattern, total downtime, proposed structural change (circuit breaker, caching, retry policy, resource limit)
15. Deliver as report to engineering leadership — NOT as autonomous action
16. Cascade failure recommendations: 3+ occurrences in 60 days → recommend isolation (bulkhead, circuit breaker, async decoupling)
17. Right-sizing: service <30% CPU/memory over 30 days → recommend right-sizing (cost flag, NOT autonomous)
18. Multi-hop causal chain: identify cause chain A→B→C,D with confidence scores per link
19. Detect indirect root causes across 3+ hops in dependency graph
20. **Predictive graduation gate:** ≥98% autonomous resolution for 6 months, all top-20 runbooks reviewed, chaos day done, prediction accuracy ≥75% over 60 days, no multi-agent conflicts in 90 days, zero worsened actions in 90 days
21. Automatic regression from Predictive to Autonomous if accuracy <60% over 30 days OR proactive action causes incident

**Required Interfaces / Classes:** None named explicitly

**Acceptance Criteria:**
- Proactive alerts fire before resource exhaustion occurs
- Traffic pattern model achieves ≥70% accuracy or self-disables
- Architectural recommendations delivered as reports (no autonomous execution)
- Predictive graduation gate enforces all 6 criteria
- Regression from Predictive triggers automatic on accuracy drop

**Implementation Complexity:** Very High  
**Spec Completeness:** High — 6 requirements, comprehensive scenarios, graduation criteria detailed, but no named implementation files

---

### 10. provider-abstraction

**System Area:** Telemetry backend abstraction supporting open-standard and proprietary backends

**Key Requirements:**

1. Route metric queries to Prometheus API for OTel provider; normalize to canonical format
2. Route metric queries to New Relic NerdGraph/NRQL for NR provider; normalize to canonical format
3. Anomaly detection engine operates identically regardless of active telemetry backend
4. Route trace queries to Jaeger/Tempo API for OTel; normalize to canonical trace format
5. Route trace queries to NerdGraph distributed tracing API for NR; normalize
6. Operator configures provider via single config setting (no code changes)
7. Validate connectivity to all configured endpoints before marking provider active
8. Generate internal alert and flag subsystems as "degraded telemetry" on provider health failure
9. Canonical metric format: name, value, timestamp, labels (service, namespace, pod, node), data quality flags
10. Canonical trace format: trace ID, spans (service, operation, duration, status, parent span ID), completeness flag
11. Dependency graph buildable from either OTel trace parent-child spans OR New Relic Service Maps API
12. Same canonical node/edge format for both graph sources
13. Plugin interface: new providers implement `MetricsQuery`, `TraceQuery`, `LogQuery`, `DependencyGraphQuery`
14. New provider selectable via config; no changes to anomaly detection, diagnostics, or remediation code

**Required Interfaces / Classes:**

- `MetricsQuery` (abstract port method/interface)
- `TraceQuery` (abstract port method/interface)
- `LogQuery` (abstract port method/interface)
- `DependencyGraphQuery` (abstract port method/interface)
- OTel/Prometheus adapter
- New Relic adapter
- **Port file:** `src/sre_agent/ports/telemetry.py`
- **Adapter directory:** `src/sre_agent/adapters/telemetry/`
- Phase 2.8 (separate OpenSpec): Datadog adapter as first external provider validation

**Acceptance Criteria:**
- Agent diagnoses identically whether backed by OTel/Prometheus or New Relic
- Provider switch requires only config change
- Provider health failure triggers degraded mode, not crash
- New provider plugin registers and functions without modifying core code

**Implementation Complexity:** High  
**Spec Completeness:** High — 4 requirements, complete canonical format definitions, named module paths, extensibility interface defined

---

### 11. rag-diagnostics

**System Area:** RAG-powered diagnostic engine — the intelligence core

**Key Requirements:**

1. Embed alert context as vector; retrieve top-K semantically similar historical incidents from vector DB
2. Each retrieved document includes similarity score
3. No documents above threshold → classify as "novel"; escalate to human with full telemetry
4. Diagnoses include citations to specific documents used
5. Evidence-weighted confidence = trace correlation + timeline match + retrieval quality
6. Multiple hypotheses ranked by evidence-weight when evidence is conflicting
7. No hypothesis above minimum threshold → escalate to human
8. Chronological event timeline: includes deployment event, config changes, metric shifts, log entries, alert triggers with temporal correlations
9. Second-opinion: separate validator cross-checks primary diagnosis
10. Primary + validator agree → proceed to remediation
11. Primary + validator disagree → no autonomous remediation; escalate with both diagnoses
12. Full audit provenance: exact post-mortems, runbooks, telemetry queries, reasoning chain
13. Chunk documents at semantic boundaries (Markdown headers) not strict token counts
14. Default embedding model: `sentence-transformers` (configurable via `VectorStorePort`)
15. 90-day rolling TTL on vector representations
16. Strict token budget: max 4000 tokens for context; prioritize most recent + highest-similarity evidence on overflow
17. LLM rate limit handling: exponential backoff → degrade gracefully → escalate without hallucinating low-confidence diagnosis
18. All RAG coordination via abstract ports: `DiagnosticPort`, `VectorStorePort`, `LLMReasoningPort`
19. Runtime injection of concrete adapters (ChromaDB, OpenAI, Anthropic, Pinecone)

**Production Hardening Requirements (competitive roadmap):**

20. P99 diagnosis latency < 30 seconds; expose `DIAGNOSIS_DURATION` Prometheus histogram
21. Fire `DiagnosisLatencySLOBreach` alert if rolling P99 >30s for 2 consecutive minutes
22. Accuracy ≥90% over rolling window (min 50 incidents); tracked per anomaly category
23. Fire internal alert if accuracy drops below 85% over 7 days
24. Handle 10 concurrent diagnosis requests without crash, deadlock, or resource exhaustion
25. No request exceeds 3× median single-request latency under concurrent load
26. Memory must not grow unboundedly under sustained load (5 req/min for 30 min); stay within 4–8 GB budget
27. On LLM timeout (>30s): fall back to rule-based severity assignment; mark `degraded_mode=true`, `confidence=low`
28. On vector store unavailable: skip RAG; proceed with LLM + real-time telemetry only; mark `rag_available=false`

**Required Interfaces / Classes:**

- `DiagnosticPort` (abstract port)
- `VectorStorePort` (abstract port)
- `LLMReasoningPort` (abstract port)
- ChromaDB adapter (current dev)
- OpenAI adapter
- Anthropic adapter
- Pinecone adapter (prod option)

**Acceptance Criteria:**
- Novel incident classification on no results above threshold
- Second-opinion disagreement halts autonomous remediation
- Provenance fully traceable per incident
- P99 latency < 30s; `DiagnosisLatencySLOBreach` alert fires on breach
- Concurrent load test: 10 simultaneous requests complete without error
- LLM failure → graceful degradation to rule-based (not crash or hallucination)

**Implementation Complexity:** Very High  
**Spec Completeness:** Very High — 28 requirements, production hardening from competitive roadmap, named port interfaces, detailed failure scenarios, metrics defined

---

### 12. remediation-engine

**System Area:** Remediation action planning, execution, verification, and audit

**Additional files:** `plan.md` (implementation plan), `remediation_models.md` (domain models), `tasks.md` (granular tasks)

**Key Requirements (from spec.md):**

1. Execute pod restart, horizontal scaling, certificate rotation, log rotation via Kubernetes API
2. Route deployment rollbacks via ArgoCD GitOps (Git revert commit)
3. Sev 3-4 rollback: auto-execute (no human approval)
4. Sev 1-2 rollback: create PR with diagnosis + evidence; human MUST approve before ArgoCD applies
5. Monitor affected metrics for 5 min (default) observation window post-remediation
6. Mark resolved if metrics return within 1σ of baseline; emit `REMEDIATION_COMPLETED`
7. Auto-rollback and emit `REMEDIATION_ROLLED_BACK` if metrics don't improve/worsen
8. Strategy selection is deterministic rule-based (not LLM): `AnomalyType` × `root_cause` → `RemediationStrategy`
9. OOM → RESTART; Traffic spike → SCALE_UP; Deployment regression → GITOPS_REVERT; Cert expiry → CERTIFICATE_ROTATION; Disk exhaustion → LOG_TRUNCATION
10. Route to correct `CloudOperatorPort` adapter based on `ComputeMechanism` + `provider`
11. Kubernetes → `KubernetesOperator.restart_compute_unit()`
12. AWS ECS → `ECSOperator.restart_compute_unit()`
13. AWS Lambda → `LambdaOperator.scale_capacity()`
14. Azure App Service → `AppServiceOperator.restart_compute_unit()`
15. Unsupported `ComputeMechanism` → escalate (never attempt execution)
16. Cloud API timeout: retry with exponential backoff (max 3 retries, default 30s timeout); mark FAILED after exhaustion
17. Circuit breaker OPEN → do not attempt; queue for retry; emit `REMEDIATION_FAILED` with `reason="circuit_breaker_open"`
18. Partial batch failure → halt remaining batches; do not rollback completed batches (unless metrics degrade)
19. Acquire distributed lock per AGENTS.md protocol before any execution
20. On lock preemption by SecOps: immediately abort in-progress remediation; queue for retry
21. Write cooldown key after completion: K8s format `cooldown:{namespace}:{resource_type}:{resource_name}`; non-K8s `cooldown:{provider}:{compute_mechanism}:{resource_id}`; default TTL 15 min
22. Sev 3-4 + confidence ≥ 0.85 → auto-execute (`approval_mode="autonomous"`)
23. Sev 1-2 → create proposal; send via `NotificationPort`; emit `REMEDIATION_PLANNED` with `approval_mode="hitl"`
24. Emit full event sequence: `REMEDIATION_PLANNED` → `REMEDIATION_APPROVED` → `REMEDIATION_STARTED` → `REMEDIATION_COMPLETED`

**Domain Models (from remediation_models.md):**

```python
class RemediationStrategy(Enum):
    RESTART = "restart"
    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    GITOPS_REVERT = "gitops_revert"
    CONFIG_CHANGE = "config_change"
    CERTIFICATE_ROTATION = "certificate_rotation"
    LOG_TRUNCATION = "log_truncation"

class ApprovalState(Enum):
    PENDING | APPROVED | REJECTED | EXPIRED

class ActionStatus(Enum):
    PROPOSED | APPROVED | EXECUTING | VERIFYING | COMPLETED | FAILED | ROLLED_BACK | CANCELLED

class VerificationStatus(Enum):
    PENDING | METRICS_NORMALIZED | METRICS_DEGRADED | VERIFICATION_TIMEOUT | SKIPPED
```

**Event Types to add to `canonical.py`:**
- `REMEDIATION_PLANNED`, `REMEDIATION_APPROVED`, `REMEDIATION_STARTED`, `REMEDIATION_COMPLETED`, `REMEDIATION_FAILED`, `REMEDIATION_ROLLED_BACK`
- `KILL_SWITCH_ACTIVATED`, `KILL_SWITCH_DEACTIVATED`, `BLAST_RADIUS_EXCEEDED`, `COOLDOWN_ENFORCED`, `PHASE_GATE_EVALUATED`

**New files per plan.md:**

```
src/sre_agent/
├── ports/remediation.py                          [NEW]
├── domain/remediation/
│   ├── engine.py, strategies.py, planner.py, models.py, verification.py  [NEW]
└── domain/safety/
    ├── blast_radius.py, kill_switch.py, cooldown.py, guardrails.py, phase_gate.py  [NEW]
└── adapters/kubernetes/operator.py               [NEW]
└── api/rest/remediation_router.py                [NEW]
```

**Acceptance Criteria:**
- All 5 incident types map to correct strategy
- Canary-first execution verified before full rollout
- Lock acquired and released per AGENTS.md protocol
- All event types emitted at correct state transitions
- Auto-rollback triggers when post-action metrics worsen

**Implementation Complexity:** Very High  
**Spec Completeness:** Very High — most complete sub-spec in the set; includes spec, domain models, implementation plan, and granular task list (T001–T031+)

---

### 13. safety-guardrails

**System Area:** Three-tier safety framework (action execution, knowledge/reasoning, security/access)

**Key Requirements:**

1. Evidence-weighted confidence gating: ≥0.85 → proceed; 0.70–0.85 → proposal; <0.70 → escalate
2. Log confidence breakdown per-component on all decisions
3. Blast radius limit (pod restart): max 20% of fleet; escalate if exceeded; include pod count, %, configured limit
4. Blast radius limit (scaling): max 2× current replicas; not exceed namespace quota; cap at max + escalate remainder
5. Canary execution for pod restarts: start with configurable subset (default 5%); validate healthy within 60s; then expand
6. Canary failure halts rollout entirely; do not restart additional pods
7. Minimum canary batch size: 1 pod (for deployments <20 pods)
8. Canary batch formula: `max(1, ceil(total_pods * canary_percentage / 100))`
9. Kill switch: `POST /api/v1/kill-switch` or CLI `sre-agent halt` by any authorized team member
10. Kill switch: halt all in-progress and queued actions; no new autonomous actions; emit `KILL_SWITCH_ACTIVATED`
11. Kill switch deactivation: resume autonomous actions; cancelled plans NOT auto-requeued; emit `KILL_SWITCH_DEACTIVATED`
12. KB document TTL (default 90 days): flag for re-validation; reduce confidence weight by 50% on expired docs
13. Automated staleness detection: flag docs referencing non-existent services/endpoints/configs
14. Alert KB owner for stale document review
15. Least privilege: deny action if agent not authorized for required permission; log denied attempt with required permission and agent scope
16. Input sanitization: strip/neutralize prompt injection payloads from all telemetry before LLM ingestion
17. Log sanitized malicious log entries for security review
18. Audit log: complete sequence for every incident (alert trigger → queries → data → hypotheses → confidence → actions → post-action metrics → resolution); immutable + tamper-evident
19. Cooldown key enforcement: deny new locks within cooldown TTL (K8s and non-K8s formats)
20. Higher-priority agent (SecOps) bypasses cooldown restriction
21. **Assist → Autonomous phase gate criteria:** accuracy ≥90% (30-day window), zero agent-caused destructive incidents, ≥95% Sev 3-4 autonomous resolution, integration test coverage ≥30% for `domain/remediation/`, 7-day soak test with zero crashes

**Required Interfaces / Classes:**

- `KillSwitch` → `src/sre_agent/domain/safety/kill_switch.py`
- `BlastRadiusCalculator` → `src/sre_agent/domain/safety/blast_radius.py`
- `CooldownEnforcer` → `src/sre_agent/domain/safety/cooldown.py`
- `GuardrailOrchestrator` → `src/sre_agent/domain/safety/guardrails.py`
- `PhaseGate` → `src/sre_agent/domain/safety/phase_gate.py`

**Acceptance Criteria:**
- Confidence <0.70 always escalates; never executes
- 20%+ pod restart blocked and escalated
- Canary failure stops all further execution
- Kill switch halts all in-flight actions within seconds
- Stale KB docs get 50% confidence weight reduction
- Prompt injection stripped before LLM input
- Audit log immutable and complete per incident

**Implementation Complexity:** High  
**Spec Completeness:** Very High — 21 requirements, numeric thresholds, named implementation files, phase gate criteria specified with testing coverage metric

---

### 14. severity-classification

**System Area:** Automated incident severity assignment (Sev 1–4)

**Key Requirements:**

1. **Sev 1** (ANY of): revenue services fully unavailable to >50% users; data loss/corruption detected or imminent; active security breach → agent takes NO autonomous action
2. **Sev 2** (ANY of): critical service >25% error rate or >3× latency; multiple non-critical services simultaneously affected; single service affecting >10,000 users degraded (not fully down) → agent proposes, human approves
3. **Sev 3** (ALL of): single non-critical service degraded; <10,000 users affected; no data loss/security risk; known reversible remediation exists → agent authorized for autonomous action
4. **Sev 4** (ALL of): single pod/container/non-user-facing component; no user-visible degradation; fully idempotent remediation → agent authorized for autonomous action
5. Tier 1 (revenue-critical) service: any OOM kill → at least Sev 2, regardless of pod count
6. Tier 3 (internal tooling) service: single OOM kill → Sev 4, agent fully authorized for pod restart
7. Human severity override API: immediate reclassification at any time
8. Override up → halt in-progress autonomous remediation; log with original + new + reason
9. Override down → resume agent handling under new severity rules
10. Multi-dimensional composite scoring: user impact, service criticality (tier), blast radius, financial impact, remediation reversibility
11. Weighted sum formula: `Score = (W1 * UserImpact) + (W2 * TierCrit) + (W3 * BlastRadius) + (W4 * FinImpact) - (W5 * Reversibility)`
12. Weights W1–W5 configurable globally
13. Thresholds configurable: `Threshold_Sev1`, `Threshold_Sev2`, etc.
14. Service tier sourced from: K8s `metadata.labels['service-tier']` or external service catalog (Backstage)
15. Missing/unreachable service tier → default to Tier 1 (fail-safe)

**Required Interfaces / Classes:**

- `SeverityClassifier` / `SeverityEngine` (implied)
- `ServiceCatalogPort` / `ServiceTierProvider` (implied for tier lookup)
- `SeverityOverrideAPI` → referenced: `src/sre_agent/api/rest/severity_override_router.py`

**Acceptance Criteria:**
- All four severity levels assigned correctly per scenario
- Tier weighting applied: Tier 1 OOM → at least Sev 2
- Override API immediately reclassifies and halts/resumes agent action
- Missing tier label defaults to Tier 1 (never silently escalates to Tier 3)
- Scoring formula uses configurable weights

**Implementation Complexity:** Medium  
**Spec Completeness:** High — 15 requirements, clear Sev 1–4 definitions, formula specified, sourcing strategy defined

---

### 15. telemetry-ingestion

**System Area:** Multi-signal telemetry collection, correlation, and pipeline resilience

**Key Requirements:**

1. Metrics received and stored within 10 seconds of OTel emission
2. Metrics include: service name, namespace, pod name, node labels
3. Log ingestion with trace ID + span ID correlation; searchable within 30 seconds of emission
4. Assemble complete distributed traces linking all spans with latency, status, error details
5. eBPF programs: capture syscall activity (file I/O, network calls, process execution) per pod
6. eBPF CPU overhead: ≤2% on host node
7. eBPF network flow capture: source, destination, bytes transferred, latency (even through encrypted service mesh)
8. eBPF data available when application-level instrumentation is absent
9. Cross-signal correlation by trace ID: metrics, logs, traces, eBPF events aligned on common timeline with sub-second precision
10. Dependency graph: edge from A→B when distributed traces show A calling B
11. Dependency graph updates within 5 minutes of observing new dependency
12. Dependency graph query returns direct + transitive dependencies with health status
13. OTel collector failure: detect within 60 seconds; internal alert; flag affected services as "degraded observability"
14. eBPF program fails to load (kernel incompatibility): log with node + kernel version; continue with OTel-only; flag as "reduced visibility"
15. Late-arriving telemetry (>60s past emission): still ingest and correlate; note in data quality metadata; retroactively update incident record if it changes outcome
16. Metrics without required labels: attempt enrichment from dependency graph; if fails → "low-quality" flag; reduced weighting in confidence scoring
17. Incomplete trace (missing spans): mark as "incomplete"; log missing service names; inform diagnostic engine

**Required Interfaces / Classes:**

- Signal correlator → `src/sre_agent/domain/correlation/signal_correlator.py`
- Ingestion adapters → `src/sre_agent/adapters/telemetry/`

**Acceptance Criteria:**
- Metrics ingested within 10s of emission
- Logs searchable within 30s of emission
- eBPF overhead ≤2% CPU
- OTel collector failure detected and alerted within 60s
- Late-arriving data updates incident records retroactively
- Low-quality metrics weighted less in confidence scoring

**Implementation Complexity:** High  
**Spec Completeness:** High — 17 requirements, precise timing SLOs, eBPF overhead budget, named implementation files

---

### 16. token-optimization

**System Area:** LLM token efficiency for cost reduction and latency improvement

**Key Requirements:**

1. Compress each retrieved evidence chunk using token-level compression before LLM submission
2. Compression preserves SRE-critical terminology (OOM, kill, latency, p99, deployment, rollback)
3. Compressed evidence ≥40% smaller in token count than original
4. Use abstract `CompressorPort` interface with runtime-injected concrete adapter
5. Rerank vector search top-K results using cross-encoder model evaluating (query, document) pairs
6. Keep only top-N results after reranking (N ≤ K)
7. Reranking via abstract `RerankerPort` interface
8. Semantic cache: if same fingerprint (service + anomaly_type + metric) hit within TTL (default 4h), return cached diagnosis without LLM call
9. Log cache hits for observability
10. Cache miss → full RAG pipeline; store result
11. Anomaly-type-aware timeline filtering: OOM → include memory/pod restart/container/OOM signals only; exclude DNS, cert, disk
12. Unknown anomaly type → include all signals (safe fallback)
13. Validation prompt: send citation summaries (≤150 chars each) + hypothesis only; NOT full evidence content
14. Validation total input ≤800 tokens
15. Validate LLM response against Pydantic model with typed fields; retry up to 2× on non-conforming responses
16. Remove JSON schema description from system prompt (Pydantic structured output handles it)
17. Record per-diagnosis: total input tokens, output tokens, compression savings
18. Expose metrics via existing Prometheus `/metrics` endpoint

**Required Interfaces / Classes:**

- `CompressorPort` (abstract)
- `RerankerPort` (abstract)
- Pydantic model for LLM response parsing (structured output)

**Acceptance Criteria:**
- Evidence compression achieves ≥40% token reduction
- SRE terminology preserved post-compression
- Cache hit prevents LLM call for same fingerprint within TTL
- Timeline filtering reduces noise per anomaly type
- Validation prompts ≤800 tokens
- Token metrics emitted to Prometheus

**Implementation Complexity:** Medium  
**Spec Completeness:** High — 18 requirements, numeric targets, port abstractions named, Prometheus integration specified

---

## Complete Tasks.md Task List

### Section 1: Telemetry Ingestion Pipeline

- [ ] 1.1 Set up OTel Collector with receivers for metrics (Prometheus), logs (Fluentd/Vector), traces (OTLP)
- [ ] 1.2 Configure OTel exporters to backend storage
- [ ] 1.3 Implement eBPF programs for kernel-level telemetry (syscalls, network flows, process behavior)
- [ ] 1.4 Build signal correlation service joining metrics, logs, traces, eBPF events by trace ID and time window
- [ ] 1.5 Auto-discovery service dependency graph from trace data with 5-minute refresh
- [ ] 1.6 Health check and meta-observability for ingestion pipeline

### Section 2: Anomaly Detection Engine

- [ ] 2.1 Rolling baseline computation for key metrics per service
- [ ] 2.2 ML anomaly detection model for time-series (statistical and/or learned)
- [ ] 2.3 Alert correlation engine grouping related anomalies by dependency graph
- [ ] 2.4 Alert suppression for planned deployments and maintenance windows
- [ ] 2.5 Operator-facing API for per-service sensitivity configuration

### Section 3: RAG Diagnostic Pipeline

- [ ] 3.1 Set up vector database (Pinecone/Weaviate/Chroma) with schema
- [ ] 3.2 Document ingestion pipeline for post-mortems and runbooks
- [ ] 3.3 Alert-to-vector embedding service
- [ ] 3.4 Semantic similarity search with configurable threshold + "novel incident" classification
- [ ] 3.5 Chronological event timeline construction
- [ ] 3.6 LLM reasoning engine for root cause hypotheses
- [ ] 3.7 Evidence-weighted confidence scoring
- [ ] 3.8 Second-opinion validator
- [ ] 3.9 Provenance tracking (documents + reasoning chain per diagnosis)

### Section 4: Remediation Action Layer

- [ ] 4.1 Remediation planner: diagnosis → safe reversible action plan
- [ ] 4.2 Kubernetes actions: pod restart, horizontal scaling, log rotation
- [ ] 4.3 GitOps integration with ArgoCD for deployment rollbacks
- [ ] 4.4 Severity-based execution paths (auto for Sev 3-4, PR for Sev 1-2)
- [ ] 4.5 Certificate rotation integration with cert-manager
- [ ] 4.6 Post-remediation verification (configurable observation window)
- [ ] 4.7 Automatic rollback trigger on metric degradation

### Section 5: Safety Guardrails Framework

- [ ] 5.1 Evidence-weighted confidence gating
- [ ] 5.2 Blast radius estimation engine
- [ ] 5.3 Hard-coded blast radius limits per action type (defaults: 20% restart, 50% scaling)
- [ ] 5.4 Canary execution framework
- [ ] 5.5 Kill switch mechanism (API, CLI, Slack integration)
- [ ] 5.6 KB TTL enforcement and automated staleness detection
- [ ] 5.7 Human review gate for agent-generated runbooks
- [ ] 5.8 IAM scoping with least-privilege service accounts per action type
- [ ] 5.9 Input sanitization layer for all telemetry before LLM
- [ ] 5.10 Comprehensive audit logging (immutable, tamper-evident)
- [ ] 5.11 Secrets management integration (Vault or AWS Secrets Manager)

### Section 6: Multi-Agent Coordination

- [ ] 6.1 Distributed locking service (etcd/Redis-based) for mutual exclusion
- [ ] 6.2 Agent priority hierarchy enforcement (Security > SRE > Cost Optimization)
- [ ] 6.3 Oscillation detection (3 contradictory actions in 30 min)
- [ ] 6.4 Conflict resolution alerting + human operator notification

### Section 7: Incident Learning Pipeline

- [ ] 7.1 Resolved incident indexing pipeline → vector DB
- [ ] 7.2 Human feedback capture for agent-escalated incidents
- [ ] 7.3 Pattern detection for recurring incidents → smart runbook generation
- [ ] 7.4 Diagnostic accuracy tracking dashboard
- [ ] 7.5 Mandatory human routing system (default 20%)
- [ ] 7.6 On-call manual handling quota enforcement (min 2 per shift)

### Section 8: Integration & Operational Readiness

- [ ] 8.1 Notification integrations (Slack, PagerDuty, Jira)
- [ ] 8.2 Operator dashboard (real-time agent status, confidence, timeline)
- [ ] 8.3 Configuration management (thresholds, limits, sensitivity)
- [ ] 8.4 Phased rollout controls (shadow mode, severity scope, graduation gates)
- [ ] 8.5 End-to-end integration tests (full pipeline)
- [ ] 8.6 Adversarial red-teaming with crafted log payloads

### Section 9: Severity Classification Engine

- [ ] 9.1 Service tier classification schema + service catalog integration
- [ ] 9.2 Multi-dimensional impact scoring (5 dimensions)
- [ ] 9.3 Automated severity assignment engine (Sev 1-4) with composite score thresholds
- [ ] 9.4 Human severity override API with real-time reclassification
- [ ] 9.5 Deployment correlation flag → auto-elevate severity for Tier 1 blast radius

### Section 10: Phased Rollout Orchestrator

- [ ] 10.1 Operational mode state machine (Observe → Assist → Autonomous → Predictive)
- [ ] 10.2 Shadow mode diagnostic comparison engine
- [ ] 10.3 Severity-scoped authorization per phase
- [ ] 10.4 Graduation gate evaluation engine with automated criteria checking
- [ ] 10.5 Dual sign-off workflow for phase transitions
- [ ] 10.6 Automatic phase regression on safety violations

### Section 11: Notification & Escalation System

- [ ] 11.1 PagerDuty integration
- [ ] 11.2 Slack integration with action buttons
- [ ] 11.3 Remediation approval notification flow with timeout re-escalation
- [ ] 11.4 Fallback channel delivery
- [ ] 11.5 Autonomous resolution summary generator
- [ ] 11.6 Jira integration for Sev 1-2 post-incident reports
- [ ] 11.7 Severity-based notification routing config API

### Section 12: Operator Dashboard

- [ ] 12.1 Real-time agent status panel
- [ ] 12.2 Evidence-weighted confidence visualization with component breakdown
- [ ] 12.3 Diagnostic accuracy dashboard per category
- [ ] 12.4 Incident timeline drill-down view
- [ ] 12.5 Graduation gate progress tracker

### Section 13: Provider Abstraction Layer

- [ ] 13.1 Canonical data model (metrics, traces, logs, events)
- [ ] 13.2 Telemetry provider interface: MetricsQuery, TraceQuery, LogQuery, DependencyGraphQuery
- [ ] 13.3 OTel/Prometheus adapter
- [ ] 13.4 New Relic adapter (NerdGraph/NRQL)
- [ ] 13.5 Provider registration system with runtime config and connectivity validation
- [ ] 13.6 Dependency graph provider abstraction
- [ ] 13.7 Provider health monitoring with "degraded telemetry" mode
- [ ] 13.8 Extensible plugin interface for future providers

### Section 14: Cloud Portability

- [ ] 14.1 Secrets management abstraction (AWS, Azure, Vault)
- [ ] 14.2 Object storage abstraction (S3, Azure Blob, MinIO)
- [ ] 14.3 IAM/authentication abstraction (IRSA, Azure Workload Identity, K8s-native)
- [ ] 14.4 Cloud provider configuration block with startup validation
- [ ] 14.5 "No cloud provider" mode for self-managed clusters
- [ ] 14.6 Cross-cloud integration tests (EKS, AKS, self-managed K8s)

### Section 15: Performance & Latency SLOs

- [ ] 15.1 Per-stage latency instrumentation (timestamped tracking)
- [ ] 15.2 End-to-end latency dashboard (pipeline stage waterfall per incident)
- [ ] 15.3 Severity-based incident queue with priority ordering
- [ ] 15.4 RAG query timeout handling (30s max, auto-escalation)
- [ ] 15.5 SLO violation alerting (internal alert on stage latency exceeded)
- [ ] 15.6 Graceful degradation logic (core pipeline survives non-critical subsystem failure)
- [ ] 15.7 System availability monitoring (99.9% uptime target)

### Section 16: Predictive Capabilities (Phase 4)

- [ ] 16.1 Resource exhaustion prediction engine (disk, memory, connection pools)
- [ ] 16.2 Proactive certificate and credential expiration tracking
- [ ] 16.3 Traffic pattern learning model (recurring spike detection)
- [ ] 16.4 Preemptive scaling engine with prediction accuracy feedback
- [ ] 16.5 Degradation trend detector (multi-week latency/error creep)
- [ ] 16.6 Architectural improvement recommendation engine
- [ ] 16.7 Cross-service causal reasoning (multi-hop dependency analysis)
- [ ] 16.8 Predictive phase graduation gate evaluation + automatic regression on accuracy drop

### Remediation Engine Granular Tasks (tasks.md — T001 to T031+)

**All items unchecked ([ ]) — none completed.**  

- [ ] T001–T005 Phase 1: Setup (package structures)
- [ ] T006–T014 Phase 2: Domain models + RemediationPort ABC + unit tests
- [ ] T015–T018 Phase 3 (US1): Strategy selection + RemediationPlanner
- [ ] T019–T027 Phase 4 (US2): All safety guardrails (BlastRadiusCalculator, KillSwitch, CooldownEnforcer, PhaseGate, GuardrailOrchestrator)
- [ ] T028–T031 Phase 5 (US3): RemediationEngine + canary batching + error handling

---

## Master Requirements Matrix

| Requirement | Sub-Spec | Priority | Estimated Complexity |
|---|---|---|---|
| Multi-signal telemetry ingestion (OTel) | telemetry-ingestion | P0 | High |
| eBPF kernel-level telemetry | telemetry-ingestion | P1 | High |
| Signal correlation (cross-signal by trace ID) | telemetry-ingestion | P0 | Medium |
| Service dependency graph auto-discovery | telemetry-ingestion | P0 | Medium |
| Pipeline failure resilience + degraded mode | telemetry-ingestion | P1 | Medium |
| Data quality validation + enrichment | telemetry-ingestion | P1 | Medium |
| Time-series anomaly detection (3σ, 30s/60s) | anomaly-detection | P0 | High |
| Configurable sensitivity per service | anomaly-detection | P1 | Low |
| Alert correlation by dependency graph | anomaly-detection | P0 | Medium |
| Proactive resource exhaustion detection | anomaly-detection | P1 | Medium |
| Multi-dimensional anomaly correlation | anomaly-detection | P2 | Medium |
| Deployment-aware anomaly detection | anomaly-detection | P1 | Medium |
| Vector embedding + semantic search | rag-diagnostics | P0 | High |
| Evidence-based root cause hypothesis | rag-diagnostics | P0 | High |
| Chronological event timeline | rag-diagnostics | P0 | Medium |
| Second-opinion validation | rag-diagnostics | P0 | Medium |
| Provenance tracking | rag-diagnostics | P1 | Medium |
| Embedding strategy + document chunking | rag-diagnostics | P1 | Medium |
| LLM prompt engineering + token budgets | rag-diagnostics | P0 | Medium |
| Intelligence layer port interfaces | rag-diagnostics | P0 | Medium |
| P99 diagnosis latency <30s + alerting | rag-diagnostics | P1 | Medium |
| Accuracy SLO ≥90% + accuracy alerting | rag-diagnostics | P1 | Medium |
| Concurrent diagnosis stability (10 req) | rag-diagnostics | P1 | Medium |
| Graceful degradation on LLM failure | rag-diagnostics | P1 | Medium |
| Evidence compression (≥40% token reduction) | token-optimization | P1 | Medium |
| Cross-encoder reranking | token-optimization | P2 | Medium |
| Semantic caching (4h TTL) | token-optimization | P1 | Medium |
| Anomaly-type-aware timeline filtering | token-optimization | P1 | Low |
| Lightweight validation prompts (≤800 tokens) | token-optimization | P1 | Low |
| Pydantic structured LLM output | token-optimization | P0 | Low |
| Token usage observability | token-optimization | P2 | Low |
| Safe remediation execution (K8s) | remediation-engine | P0 | High |
| GitOps rollback via ArgoCD | remediation-engine | P0 | High |
| Post-remediation verification + auto-rollback | remediation-engine | P0 | Medium |
| Diagnosis-to-strategy selection matrix | remediation-engine | P0 | Low |
| Multi-cloud remediation routing | remediation-engine | P1 | High |
| Error handling + circuit breaker | remediation-engine | P1 | Medium |
| Multi-agent lock coordination | remediation-engine | P0 | High |
| Severity-based HITL routing | remediation-engine | P0 | Low |
| Remediation event audit trail | remediation-engine | P0 | Low |
| Evidence-weighted confidence gating | safety-guardrails | P0 | Low |
| Blast radius limits (20% restart, 2× scale) | safety-guardrails | P0 | Medium |
| Canary execution framework | safety-guardrails | P0 | Medium |
| Kill switch (API + CLI) | safety-guardrails | P0 | Low |
| KB TTL enforcement + staleness detection | safety-guardrails | P1 | Medium |
| Least privilege access control | safety-guardrails | P0 | Medium |
| Input sanitization (prompt injection) | safety-guardrails | P0 | Low |
| Immutable audit logging | safety-guardrails | P0 | Medium |
| Cooldown protocol enforcement | safety-guardrails | P0 | Medium |
| Phase gate graduation criteria | safety-guardrails | P0 | Medium |
| Automated Sev 1–4 classification | severity-classification | P0 | Medium |
| Service tier weighting (Tier 1–3) | severity-classification | P0 | Low |
| Human severity override API | severity-classification | P0 | Low |
| Multi-dimensional impact scoring formula | severity-classification | P1 | Medium |
| Service tier sourcing (K8s labels / Backstage) | severity-classification | P1 | Low |
| Mutual exclusion distributed locks | agent-coordination | P0 | High |
| Priority hierarchy enforcement | agent-coordination | P0 | Medium |
| Oscillation detection + halt | agent-coordination | P1 | Medium |
| Phased mode state machine | phased-rollout | P0 | Medium |
| Shadow mode diagnostic comparison | phased-rollout | P0 | Medium |
| Severity-scoped authorization per phase | phased-rollout | P0 | Low |
| Phase graduation gates (3 transitions) | phased-rollout | P0 | Medium |
| Dual sign-off workflow | phased-rollout | P0 | Low |
| Phase regression on safety violation | phased-rollout | P0 | Low |
| Resolved incident indexing (≤15 min) | incident-learning | P1 | Medium |
| Smart runbook generation (pattern-based) | incident-learning | P2 | High |
| Diagnostic accuracy tracking | incident-learning | P1 | Low |
| Mandatory human routing (20%) | incident-learning | P1 | Low |
| PagerDuty escalation integration | notifications | P0 | Medium |
| Slack integration with action buttons | notifications | P0 | Medium |
| Fallback channel delivery | notifications | P1 | Low |
| Remediation approval notification + timeout | notifications | P0 | Medium |
| Resolution summary delivery (≤5 min) | notifications | P1 | Low |
| Jira post-incident ticket creation | notifications | P2 | Low |
| Per-severity routing configuration | notifications | P1 | Low |
| Real-time agent status dashboard | operator-dashboard | P1 | High |
| Confidence visualization (component breakdown) | operator-dashboard | P1 | Medium |
| Diagnostic accuracy dashboard | operator-dashboard | P1 | Medium |
| Incident timeline drill-down | operator-dashboard | P1 | High |
| Graduation gate progress tracker | operator-dashboard | P1 | Medium |
| End-to-end latency SLOs (all stages) | performance-slos | P0 | Medium |
| Detection-to-alert latency bounds | performance-slos | P0 | Low |
| RAG query latency bounds + timeout | performance-slos | P0 | Low |
| Remediation execution latency | performance-slos | P0 | Low |
| System availability 99.9% | performance-slos | P0 | Medium |
| Graceful degradation logic | performance-slos | P0 | Medium |
| Telemetry backend abstraction | provider-abstraction | P1 | High |
| Canonical data model (metrics, traces, logs) | provider-abstraction | P1 | Medium |
| Provider registration + health monitoring | provider-abstraction | P1 | Medium |
| Dependency graph provider independence | provider-abstraction | P1 | Medium |
| Extensible plugin interface | provider-abstraction | P2 | High |
| K8s distribution portability | cloud-portability | P0 | Medium |
| Secrets management abstraction | cloud-portability | P0 | High |
| Object storage abstraction | cloud-portability | P1 | Medium |
| IAM/auth abstraction | cloud-portability | P0 | Medium |
| Cloud provider config + startup validation | cloud-portability | P0 | Low |
| Proactive capacity exhaustion prediction | predictive-capabilities | P3 | Very High |
| Traffic pattern prediction + preemptive scaling | predictive-capabilities | P3 | Very High |
| Degradation trend detection | predictive-capabilities | P3 | High |
| Architectural improvement recommendations | predictive-capabilities | P3 | High |
| Cross-service causal reasoning | predictive-capabilities | P3 | Very High |
| Predictive graduation gate | predictive-capabilities | P3 | Medium |

---

## Gap Analysis

### Specs That Are Most Complete (Very High Completeness)

1. **remediation-engine** — Only sub-spec with its own `plan.md`, `remediation_models.md`, and `tasks.md`. Has named classes, enums, event types, file paths, and granular T001–T031+ tasks. This is production-implementation-ready.
2. **rag-diagnostics** — Has named port interfaces, adapter patterns, Prometheus metrics, competitive parity requirements. Includes production hardening section.
3. **safety-guardrails** — Has named implementation files, specific numeric thresholds, event types, phase gate with test coverage metric.

### Specs with Notable Gaps

1. **operator-dashboard** — No API contracts defined, no frontend tech stack specified, no wireframes/mockup references. Implementation details entirely absent.
2. **agent-coordination** — No named interfaces/classes or module file paths. Lock schema defined in `AGENTS.md` but no Python port/adapter interface specified for this spec.
3. **incident-learning** — No named interfaces or module paths. Behavioral scenarios defined but no implementation guidance.
4. **predictive-capabilities** — No named interfaces or module paths. Very complex ML requirements without specifying model types, training data pipelines, or storage formats for prediction state.
5. **provider-abstraction** — Names module paths (`ports/telemetry.py`, `adapters/telemetry/`) but no concrete method signatures for `MetricsQuery`, `TraceQuery`, `LogQuery`, `DependencyGraphQuery` interfaces.

### Areas NOT Specified / Underspecified

1. **LLM provider selection** — Explicitly unresolved in `design.md`. No provider chosen.
2. **Vector database selection** — Explicitly unresolved. ChromaDB for dev, but production target unspecified.
3. **Phase graduation RACI** — Who signs off on phase transitions described vaguely; no formal RACI document.
4. **Blast radius threshold empirical tuning** — 20% is noted as a "starting point" requiring Phase 1 data.
5. **Frontend technology for operator dashboard** — No framework, no API contracts, no WebSocket vs polling decision.
6. **eBPF toolchain specifics** — Cilium vs Pixie mentioned in proposal but no adapter implementation specified.
7. **Redis vs etcd for distributed locks** — Both mentioned, no decision.
8. **Smart runbook generation ML approach** — Pattern matching thresholds (3 incidents) defined but no NLP/embedding model specified.
9. **Traffic prediction model type** — No specification of algorithm (ARIMA, Prophet, LSTM, etc.).
10. **Jira integration** — Mentioned in notifications spec as P2 but no API contract or Jira project configuration.
11. **Kill switch Slack integration** — Mentioned in tasks.md (5.5) but not in safety-guardrails spec.md.
12. **Log truncation reversibility** — Marked as `❌ No (data loss)` in remediation_models.md; the approach/policy for deciding what logs to truncate is unspecified beyond "designated log paths on volume."

### No Implementation Started

Based on the `tasks.md` (all items unchecked `[ ]`) and the remediation-engine `tasks.md` (T001–T031+ all unchecked), **zero tasks have been marked complete** in either the top-level or sub-spec task lists.

The codebase (referenced file paths in `src/sre_agent/`) may have partial implementations from earlier work (e.g., `CloudOperatorPort`, `EventBus`, `AnomalyDetector`), but no spec tasks are ticked.

---

## References

- `openspec/changes/autonomous-sre-agent/proposal.md`
- `openspec/changes/autonomous-sre-agent/design.md`
- `openspec/changes/autonomous-sre-agent/tasks.md`
- `openspec/changes/autonomous-sre-agent/specs/agent-coordination/spec.md`
- `openspec/changes/autonomous-sre-agent/specs/anomaly-detection/spec.md`
- `openspec/changes/autonomous-sre-agent/specs/cloud-portability/spec.md`
- `openspec/changes/autonomous-sre-agent/specs/incident-learning/spec.md`
- `openspec/changes/autonomous-sre-agent/specs/notifications/spec.md`
- `openspec/changes/autonomous-sre-agent/specs/operator-dashboard/spec.md`
- `openspec/changes/autonomous-sre-agent/specs/performance-slos/spec.md`
- `openspec/changes/autonomous-sre-agent/specs/phased-rollout/spec.md`
- `openspec/changes/autonomous-sre-agent/specs/predictive-capabilities/spec.md`
- `openspec/changes/autonomous-sre-agent/specs/provider-abstraction/spec.md`
- `openspec/changes/autonomous-sre-agent/specs/rag-diagnostics/spec.md`
- `openspec/changes/autonomous-sre-agent/specs/remediation-engine/spec.md`
- `openspec/changes/autonomous-sre-agent/specs/remediation-engine/plan.md`
- `openspec/changes/autonomous-sre-agent/specs/remediation-engine/remediation_models.md`
- `openspec/changes/autonomous-sre-agent/specs/remediation-engine/tasks.md`
- `openspec/changes/autonomous-sre-agent/specs/safety-guardrails/spec.md`
- `openspec/changes/autonomous-sre-agent/specs/severity-classification/spec.md`
- `openspec/changes/autonomous-sre-agent/specs/telemetry-ingestion/spec.md`
- `openspec/changes/autonomous-sre-agent/specs/token-optimization/spec.md`
