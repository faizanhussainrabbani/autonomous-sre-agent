# Technical Analysis: Autonomous SRE Agent

**Date:** February 25, 2026

---

## Table of Contents

1. [System Purpose & Scope](#1-system-purpose--scope)
2. [Architecture & Components](#2-architecture--components)
3. [Key Technical Decisions](#3-key-technical-decisions)
4. [Safety & Risk Mitigation](#4-safety--risk-mitigation)
5. [Operational Model](#5-operational-model)
6. [Implementation Status](#6-implementation-status)

---

## 1. System Purpose & Scope

### Problem Statement

Current SRE incident response is a manual, multi-tool, multi-step process that averages **45+ minutes MTTR** even for well-understood incidents. Engineers must sequentially query Prometheus, Jaeger, and ELK, correlate signals across layers, consult historical post-mortems, and manually execute runbook steps. Industry data shows **40–50% of incidents are repeatable patterns** that still require human intervention every time.

The cost is concrete: at an estimated $5,600/minute of downtime (Gartner 2024), a 500-microservice organization experiencing 15 significant incidents/month faces **~$45M in annual downtime costs**.

### What the System Handles

The agent targets a specific, bounded class of incidents — those that are well-understood, repeatable, and have safe, reversible remediations:

| Incident Type | Remediation | Signal Source |
|---|---|---|
| OOM kills | Pod restart | Memory metrics, kernel OOM events via eBPF |
| Traffic spikes | Horizontal pod scaling | Request rate, latency percentiles, throughput metrics |
| Deployment-induced regressions | GitOps rollback via ArgoCD Git revert | Temporal correlation with deployment history, trace degradation |
| Certificate expirations | Certificate rotation via cert-manager | Predictive detection from cert metadata |
| Disk space exhaustion | Log rotation, temp cleanup, volume expansion | Disk usage metrics, growth rate projection |

These five incident types are the recommended starting set, chosen because their remediations are **idempotent**, **reversible**, and have **clear telemetry signals**.

### Explicit Non-Goals

The system explicitly does NOT handle:

| Excluded Category | Rationale |
|---|---|
| **Novel failure modes** | No historical data for RAG grounding; high hallucination risk from pure LLM reasoning |
| **Stateful/irreversible actions** (schema changes, data migrations) | Wrong action causes data corruption with no safe undo path |
| **Security incident response** | Requires forensic evidence preservation; autonomous action could destroy evidence |
| **Multi-team coordination incidents** | Require human communication, judgment, and cross-team negotiation |
| **Business-logic errors** | Require domain expertise beyond infrastructure patterns that LLMs cannot reliably provide |

The boundary is deliberately conservative: the system **augments** SRE teams for repeatable work, it does not **replace** them.

---

## 2. Architecture & Components

The system is organized into a pipeline of six major subsystems, with three cross-cutting concerns (safety guardrails, multi-agent coordination, phased rollout). Each subsystem is defined as a separate capability with its own formal specification in `openspec/changes/autonomous-sre-agent/specs/`.

### 2.1 Telemetry Ingestion Pipeline

**Spec:** `specs/telemetry-ingestion/spec.md` | **Tasks:** 1.1–1.6

The data foundation layer collects four signal types through two complementary mechanisms:

**OpenTelemetry Collector** handles application-level telemetry:
- **Metrics** — CPU, memory, request rate, error rate, latency percentiles via Prometheus receivers
- **Logs** — Structured log ingestion via Fluentd/Vector with trace ID and span ID correlation
- **Traces** — Distributed trace assembly via OTLP linking all spans across service boundaries

**eBPF Programs** add kernel-level depth without sidecar overhead (~1–2% CPU):
- Syscall-level visibility (process behavior, file access patterns)
- Network flow tracing at packet level, including within encrypted service meshes
- Process behavior monitoring for anomalous execution patterns

**Signal Correlation Service** joins all four signal types by trace ID and time window into a unified per-service view with sub-second precision. This is the critical glue — without it, the diagnostic engine would be querying isolated data silos.

**Service Dependency Graph** is auto-discovered from observed trace data with a 5-minute refresh cycle. This graph serves multiple downstream consumers: anomaly correlation, blast radius estimation, and staleness detection for the knowledge base.

**Data Quality Requirements** are specified rigorously:
- Metrics missing required labels are enriched from the dependency graph; if enrichment fails, they're flagged as "low-quality" and weighted less in confidence scoring
- Incomplete traces are marked and the diagnostic engine is informed of gaps to prevent misattributing latency
- Late-arriving data (>60s) is still ingested; if it would have changed a prior anomaly detection outcome, the incident record is retroactively updated

### 2.2 Anomaly Detection Engine

**Spec:** `specs/anomaly-detection/spec.md` | **Tasks:** 2.1–2.5

Replaces static threshold alerts with ML-based detection on streaming time-series data:

**Rolling Baseline Computation** maintains per-service, per-metric baselines for latency percentiles, error rates, and throughput. Anomalies are detected as deviations from these baselines rather than fixed thresholds.

**Detection Rules** (from the spec):
- Latency spike: p99 exceeds 3σ from rolling baseline for >2 minutes → alert within 60 seconds
- Error rate surge: >200% increase from baseline → alert distinguishing 4xx vs 5xx
- Memory pressure: >85% of limit for >5 minutes with increasing trend → proactive alert with projected time-to-OOM
- Disk exhaustion: >80% capacity OR projected full within 24 hours → alert with growth rate

**Alert Correlation Engine** groups related anomalies into single incidents using the service dependency graph. When multiple services report anomalies simultaneously, they are correlated rather than generating independent alerts — this is the primary mechanism for preventing alert storms.

**Alert Suppression** handles planned deployments: brief metric perturbations lasting <30 seconds during known deployment windows are suppressed (logged with reasoning for audit). Anomalies within 60 minutes of a deployment are flagged as "potentially deployment-induced" with the deployment's commit SHA, deployer, and changed services included in context.

**Configurable Sensitivity** — operators can tune sensitivity per service and per metric type via an API, with changes taking effect within 5 minutes.

### 2.3 RAG Diagnostic Pipeline

**Spec:** `specs/rag-diagnostics/spec.md` | **Tasks:** 3.1–3.9

The intelligence core that converts anomaly alerts into root cause diagnoses grounded in organizational history:

**Vector Embedding & Retrieval:**
1. Alert context (service name, error type, affected metrics, time window) is embedded as a vector
2. Semantic similarity search retrieves top-K most similar historical incidents from the vector database
3. Each retrieved document carries a similarity score; documents below threshold trigger "novel incident" classification and immediate human escalation

**Chronological Event Timeline Construction** assembles a time-ordered sequence of events from correlated telemetry — this gives the LLM reasoning engine a structured narrative rather than raw signal data.

**LLM Reasoning Engine** generates root cause hypotheses grounded in retrieved evidence. The key constraint: diagnoses MUST include citations to specific documents used. If retrieved documents provide conflicting indicators, multiple hypotheses are ranked by evidence-weighted confidence. If no hypothesis exceeds the minimum confidence threshold, the system escalates rather than guessing.

**Second-Opinion Validation** — a separate model or rule-based validator cross-checks the primary agent's diagnosis. If primary and validator agree, remediation proceeds. If they disagree, the system does NOT proceed with autonomous remediation — it escalates with both diagnoses presented.

**Provenance Tracking** maintains a full audit trail of which documents, data sources, and reasoning steps were used for every diagnosis.


### 2.4 Remediation Action Layer

**Spec:** `specs/remediation-engine/spec.md` | **Tasks:** 4.1–4.7

Executes targeted remediations through two paths, gated by severity:

**Direct Kubernetes API Actions:**
- Pod restart for OOM kills — logged with pod name, namespace, timestamp, and diagnosis reference
- Horizontal scaling for traffic spikes — bounded by configured maximum replica limits
- Certificate rotation via cert-manager integration — verifies new cert is valid and active before marking resolved
- Log rotation for disk exhaustion

**GitOps via ArgoCD** for deployment remediations:
- **Sev 3–4 incidents:** Agent creates a Git revert commit directly; ArgoCD reconciles cluster to reverted state; no human approval required
- **Sev 1–2 incidents:** Agent creates a pull request with the proposed Git revert including full diagnosis, evidence, and impact assessment; human MUST approve before ArgoCD applies

**Post-Remediation Verification** monitors affected service metrics (latency, error rate, throughput) for a configurable observation window after every action. If metrics return to baseline → incident marked resolved. If metrics do NOT improve or worsen → automatic rollback of the remediation action + escalation to human.

**Remediation Planner** maps diagnoses to safe, reversible action plans. This is the translation layer between "here's what's wrong" (diagnostic output) and "here's what to do about it" (executable action).

### 2.5 Severity Classification Engine

**Spec:** `specs/severity-classification/spec.md` | **Tasks:** 9.1–9.5

Automated severity assignment determines the agent's authorization level:

| Severity | Criteria | Agent Authorization |
|---|---|---|
| **Sev 1** | Revenue services fully unavailable to >50% users, data loss detected/imminent, active security breach | NO autonomous action regardless of phase (human-only) |
| **Sev 2** | Critical service significantly degraded (>25% error rate / >3x latency), multiple services affected, >10K users degraded | Propose remediation, require human approval |
| **Sev 3** | Single non-critical service degraded, <10K users, no data loss, known reversible remediation exists | Autonomous remediation (in Assist/Autonomous phases) |
| **Sev 4** | Single pod/container/non-user-facing, no user-visible degradation, fully idempotent remediation | Autonomous remediation (in Assist/Autonomous phases) |

**Service Tier Weighting** adjusts severity based on business criticality:
- OOM kill on Tier 1 (revenue-critical) service → minimum Sev 2, regardless of pod count
- OOM kill on Tier 3 (internal tooling) with single pod → Sev 4, fully autonomous

**Multi-Dimensional Impact Scoring** uses five dimensions for ambiguous cases: user impact, service criticality (from service catalog), blast radius, financial impact (revenue at risk per minute), and remediation reversibility.

**Human Override** allows responders to reclassify severity at any time, with immediate effect on in-progress agent actions (e.g., escalating Sev 3 → Sev 1 halts autonomous remediation).

### 2.6 Incident Learning Pipeline

**Spec:** `specs/incident-learning/spec.md` | **Tasks:** 7.1–7.6

The continuous improvement loop:

**Resolved Incident Indexing** — every resolved incident (by agent or human) generates a structured record (root cause, symptoms, telemetry patterns, remediation actions, time to resolution, outcome) embedded as a vector and indexed within 15 minutes. For human-resolved incidents, the system prompts for root cause and remediation details to capture as feedback.

**Smart Runbook Generation** — when 3+ incidents with similar root causes are resolved using the same remediation steps, the system generates a draft runbook. Draft runbooks require human review before entering the production knowledge base (preventing compounding errors).

**Diagnostic Accuracy Tracking** — per-category correct/incorrect diagnosis rates, agent-vs-human comparison, with human overrides recorded as training signals for improved retrieval relevance.

**Mandatory Human Routing** — a configurable minimum (default 20%) of agent-capable incidents are randomly routed to human responders. Additionally, every SRE must manually handle at least 2 agent-capable incidents per on-call shift. This is a deliberate anti-atrophy mechanism.

### 2.7 Multi-Agent Coordination

**Spec:** `specs/agent-coordination/spec.md` | **Tasks:** 6.1–6.4

Prevents conflicts when SRE, cost-optimization, security, and compliance agents operate on shared infrastructure:

**Distributed Locking** (etcd/Redis-based) — when the SRE agent begins remediating a resource, it acquires a distributed lock. Other agents are blocked from modifying the same resource until the lock is released after successful post-action verification. Locks have a configurable maximum duration with automatic release and human escalation on timeout.

**Priority Hierarchy:** Security > SRE > Cost Optimization. When conflicting actions are detected, the higher-priority agent's action takes precedence and the lower-priority action is deferred or cancelled with notification.

**Oscillation Detection** — if a resource is scaled up/down (or equivalent contradictory actions) more than 3 times within 30 minutes by different agents, all agent actions on that resource are halted and human operators are alerted. The resource requires manual intervention to resume agent operations.

### 2.8 Notification & Escalation System

**Spec:** `specs/notifications/spec.md` | **Tasks:** 11.1–11.7

Multi-channel delivery with fallback:

- **PagerDuty** for on-call escalation with structured incident payloads (summary, diagnosis, confidence, evidence citations, dashboard links)
- **Slack** for incident channel notifications with action buttons (approve/reject/investigate)
- **Jira** for post-incident report creation on Sev 1–2 incidents

**Approval Flow:** When remediation requires human sign-off (Sev 1–2), the system sends an actionable notification with direct PR link, diagnosis, blast radius assessment. If no response within the configured timeout (e.g., 15 minutes), it re-notifies and escalates to secondary on-call.

**Fallback:** If the primary channel is unreachable, the system attempts delivery via configured fallback channels in priority order. If ALL channels fail, autonomous actions are halted until a human acknowledges.

**Resolution Summaries** are auto-generated within 5 minutes of resolution: timeline, root cause, actions taken, metric validation, total resolution time.

### 2.9 Operator Dashboard

**Spec:** `specs/operator-dashboard/spec.md` | **Tasks:** 12.1–12.5

Real-time operational visibility:

- **Agent status panel:** Current phase, active incidents (with stage: detecting/diagnosing/remediating/verifying), pending actions, kill switch status
- **Confidence visualization:** Evidence-weighted score decomposed into trace correlation, timeline match, RAG retrieval similarity, and validator agreement — color-coded green/yellow/red per component
- **Diagnostic accuracy dashboard:** Per-category correct/incorrect rates, agent-vs-human comparison view, rolling accuracy trends
- **Incident timeline drill-down:** Full chronological sequence per incident — alert trigger through resolution with expandable detail at each step
- **Graduation gate tracker:** Real-time criteria completion for next phase transition, with met criteria in green and unmet in red with gap highlighted

---

## 3. Key Technical Decisions

Five critical architectural choices are documented in `openspec/changes/autonomous-sre-agent/design.md`:

### 3.1 OpenTelemetry + eBPF Over Proprietary APM

**Decision:** Use OTel for application-level telemetry + eBPF for kernel-level telemetry.

**Rejected alternatives:**
- **Proprietary APM (Datadog/New Relic):** Vendor lock-in, higher cost, limited raw kernel-level data access
- **OTel-only (no eBPF):** Misses syscall-level visibility, in-mesh network flow tracing, and process behavior monitoring

**Rationale:** OTel provides **breadth** (vendor-neutral, full-stack correlation across metrics/logs/traces) while eBPF provides **depth** (kernel-level precision at ~1–2% CPU overhead without sidecars). The combination produces the highest-fidelity signal for both ML anomaly detection and agentic investigation.

**Practical implication:** Requires eBPF-capable Linux kernels on all cluster nodes and >80% OTel service coverage before the agent can operate effectively.

### 3.2 RAG with Vector Database Over Fine-Tuned LLM

**Decision:** Ground LLM reasoning in organizational history via Retrieval-Augmented Generation, rather than fine-tuning a model on incident data.

**Rejected alternatives:**
- **Fine-tuned LLM:** Data quality challenges, expensive retraining pipeline, can't easily add new incidents, risk of overfitting to historical patterns
- **Pure LLM reasoning (no RAG):** High hallucination risk, no organizational context, generic diagnoses

**Rationale:** RAG enables **dynamic knowledge updates** (new post-mortems indexed immediately), **provenance tracking** (agent cites exact sources), and avoids the data pipeline complexity of continuous fine-tuning. The primary architectural benefit is **hallucination mitigation** — the agent reasons from retrieved evidence rather than parametric memory.

**Trade-off acknowledged:** RAG introduces its own failure modes — stale knowledge bases, embedding drift, missing documentation — but these are addressable through TTL enforcement, embedding model versioning, and automated staleness detection (see Section 4).

### 3.3 Evidence-Weighted Confidence Over LLM Self-Reported Confidence

**Decision:** Score confidence based on structural evidence checks rather than the LLM's self-reported confidence.

**Rejected alternatives:**
- **LLM self-reported confidence thresholds (>85%):** LLMs are poorly calibrated; express 95% confidence on hallucinated outputs as readily as correct ones
- **Ensemble voting (multiple LLMs):** Higher latency, higher cost, marginal improvement over single-model + evidence checks

**Rationale:** Structural evidence checks are **objective and verifiable**: "Does the diagnosis have supporting trace data? Does the timeline correlate? Is there a matching RAG retrieval?" This is fundamentally more reliable than asking the model how confident it "feels."

**Components of the evidence-weighted score:**
1. Trace correlation strength — does trace data support the diagnosis?
2. Timeline match quality — does the event sequence align with the proposed root cause?
3. RAG retrieval similarity — how closely does the current incident match retrieved historical evidence?
4. Second-opinion validator agreement — do the primary and secondary models converge?

### 3.4 GitOps via ArgoCD Over Direct API Execution

**Decision:** Route deployment remediations through GitOps rather than direct kubectl/API calls.

**Rejected alternatives:**
- **Direct kubectl/API execution:** Faster but no audit trail, non-deterministic rollbacks, harder to review
- **PR-based GitOps with mandatory review:** Safest but too slow for incident response (human review bottleneck)

**Rationale:** ArgoCD Git revert provides **version-controlled, auditable, deterministic rollbacks**. The compromise: for Sev 3–4, the agent creates the Git revert commit directly (speed); for Sev 1–2, it creates a PR for human approval (safety). This balances response speed with change control.

### 3.5 Distributed Locks Over Centralized Orchestrator for Multi-Agent Coordination

**Decision:** Use distributed locks (etcd/Redis) on resources being remediated rather than a centralized agent orchestrator.

**Rejected alternatives:**
- **Centralized orchestrator/control plane:** Single point of failure, adds latency, complex to build
- **No coordination (best-effort):** Risk of oscillation loops (SRE scales up, cost agent scales down)

**Rationale:** Distributed locks are simpler, have no SPOF, and leverage existing infrastructure. Combined with a deterministic priority hierarchy (Security > SRE > Cost Optimization) for conflict resolution.

### 3.6 Open Questions (Unresolved Decisions)

Four decisions remain open per `design.md`:

1. **LLM provider:** Self-hosted (Llama) vs. cloud API (GPT/Claude/Gemini). Trade-off between latency, cost, data privacy, and model quality. Security-sensitive environments may require self-hosted.
2. **Vector database:** Pinecone (managed, scalable) vs. Weaviate (self-hosted, more control) vs. Chroma (lightweight, dev-friendly). Depends on scale and operational preference.
3. **Blast radius threshold tuning:** The 20% pod restart limit is a starting point. Optimal thresholds per action type need empirical tuning during Phase 1 (shadow mode).
4. **Phase graduation authority:** Who signs off on phase transitions? The spec requires dual sign-off (engineering leadership + SRE team lead), but the exact RACI needs definition.

---

## 4. Safety & Risk Mitigation

Safety is architected as a **three-tier framework** defined in `specs/safety-guardrails/spec.md` (tasks 5.1–5.11). Each tier addresses a different failure vector.

### 4.1 Tier 1: Action Execution Guardrails

These constrain **what the agent can do** and **how aggressively**:

| Guardrail | Mechanism | Failure Mode Addressed |
|---|---|---|
| **Evidence-weighted confidence gating** | Block autonomous action when structural evidence score < threshold; escalate with full breakdown | LLM hallucination → incorrect diagnosis → destructive action |
| **Blast radius hard limits** | Per-action-type maximums (e.g., never restart >20% of pods, scaling bounded by max replicas) | Agent acts at machine speed, amplifying bad decisions fleet-wide |
| **Canary execution** | Apply to configurable subset first (e.g., 5% of pods); validate health; then expand in batches. Halt if canary fails. | Incorrect remediation applied to entire fleet before detection |
| **Post-action monitoring + automatic rollback** | Monitor affected metrics for observation window; auto-revert if metrics degrade | Remediation worsens the incident |
| **Kill switch** | API endpoint + CLI + Slack integration; any team member can halt all actions instantly; no new actions until deactivated | Last-resort defense against any runaway behavior |

### 4.2 Tier 2: Knowledge & Reasoning Guardrails

These ensure **the agent reasons from verified evidence**:

| Guardrail | Mechanism | Failure Mode Addressed |
|---|---|---|
| **RAG grounding requirement** | Diagnosis must be supported by retrieved evidence above similarity threshold; below threshold → classify as "novel" and escalate | Pure LLM hallucination driving production actions |
| **Second-opinion validation** | Separate model/rule-based validator cross-checks primary diagnosis; disagreement → escalate, do NOT proceed | Single-model reasoning failure |
| **Provenance tracking** | Agent must cite exact documents used; full audit trail of reasoning chain | Unverifiable agent decisions; lack of accountability |
| **Knowledge base TTL** | 90-day expiry + re-validation; auto-detect staleness against live dependency graph | Agent acting on outdated architecture information |
| **Human review gate for runbooks** | Agent-generated runbooks require human approval before entering production knowledge base | Compounding errors in the knowledge base |

### 4.3 Tier 3: Security & Access Guardrails

These protect **the agent itself** from compromise or scope creep:

| Guardrail | Mechanism | Failure Mode Addressed |
|---|---|---|
| **Least-privilege IAM** | Scoped service accounts per action type; denied actions logged with required vs. actual permissions | Compromised agent as insider threat; excessive lateral impact |
| **Input sanitization** | Strip/neutralize prompt injection payloads from telemetry before LLM ingestion; sanitized entries logged for security review | Adversarial manipulation via crafted log entries |
| **Secrets management** | HashiCorp Vault / AWS Secrets Manager integration; no direct credential storage | API key exfiltration |
| **Comprehensive audit logging** | Every action, query, decision logged immutably and tamper-evidently | Forensic review; accountability |
| **Adversarial red-teaming** | Scheduled testing with crafted log payloads to validate sanitization | Undiscovered prompt injection vectors |

### 4.4 Risk Severity Matrix

From `design.md`, the catalogued risks with their mitigations:

| Risk | Severity | Primary Mitigation |
|---|---|---|
| LLM hallucination → destructive remediation | **Critical** | Evidence-weighted confidence + second opinion + canary + auto-rollback |
| Blast radius amplification at machine speed | **High** | Hard-coded limits + canary execution (5% first) + kill switch |
| RAG knowledge base staleness | **Medium-High** | 90-day TTL + staleness detection vs. live dependency graph + quarterly audit |
| Agent-on-agent oscillation | **Medium** | Mutual exclusion locks + priority hierarchy + oscillation detection |
| SRE skill atrophy | **Medium** | 20% mandatory human routing + quarterly agent-disabled chaos days + on-call manual quota |
| Adversarial prompt injection via logs | **Medium** | Input sanitization + adversarial red-teaming |
| Vector DB latency under high incident volume | **Medium** | Cache frequently retrieved post-mortems + async pre-warming for known alert patterns |
| OTel instrumentation gaps in legacy services | **Low-Medium** | Require >80% coverage before Phase 2; eBPF as fallback for uninstrumented services |

---

## 5. Operational Model

### 5.1 Four-Phase Rollout Strategy

Defined in `specs/phased-rollout/spec.md` (tasks 10.1–10.6), the rollout implements a state machine with enforced graduation gates:

#### Phase 1: OBSERVE (Months 1–3)

- Agent deploys in **read-only/shadow mode** — default on first deployment
- Produces diagnostic recommendations but takes **NO remediation actions**
- All recommendations logged for accuracy comparison against human decisions
- Match/mismatch tracking per incident category with rolling accuracy metric
- Purpose: build confidence, identify telemetry gaps, calibrate knowledge base

**Graduation Gate → Phase 2:**
- Agent diagnostic accuracy ≥90% vs. human decisions
- Evaluated over minimum 100 incidents
- Zero false-positive remediations that would have been destructive
- Knowledge base coverage verified for top 20 incident types

#### Phase 2: ASSIST (Months 4–6)

- **Sev 3–4 incidents:** Agent handles autonomously (subject to safety guardrails)
- **Sev 1–2 incidents:** Agent proposes remediations; human approves before execution
- **Observe mode:** All severity levels still blocked from autonomous action
- Continuous feedback loop: human corrections improve agent
- Establish blast-radius limits and confidence thresholds empirically

**Graduation Gate → Phase 3:**
- Autonomous Sev 3–4 resolution rate ≥95%
- Zero blast-radius breaches over continuous 60-day window
- Human override rate for Sev 1–2 proposals drops below 15%
- No agent-initiated action worsened an incident

#### Phase 3: AUTONOMOUS (Months 7–12)

- Agent handles **all well-understood incidents** autonomously
- Human-in-the-loop only for novel incidents or actions exceeding blast-radius thresholds
- Agent generates and maintains runbooks (with human review before KB insertion)
- 20% of agent-capable incidents still routed to humans for skill retention

**Graduation Gate → Phase 4:**
- Autonomous resolution rate ≥98% for well-understood incidents
- Agent-generated runbooks reviewed and approved by SRE team
- Quarterly agent-disabled chaos day completed successfully
- No multi-agent conflicts detected (if multiple agents deployed)

#### Phase 4: PREDICTIVE (Year 2+)

- Agent **predicts incidents before they occur** (capacity exhaustion, cert expiry, degradation trends)
- Proactive remediation: scale before the spike, rotate before expiry
- Cross-service causal reasoning for complex failure modes
- Agent proposes architectural improvements based on incident patterns

### 5.2 Phase Governance

**Dual Sign-Off:** Every phase transition requires explicit approval from both engineering leadership AND the on-call SRE team lead. The transition does not occur until both approvals are recorded.

**Automatic Phase Regression:** If the system is in Autonomous mode and a blast-radius breach or agent-worsened incident occurs, it **automatically reverts to Assist mode**. The agent cannot return to Autonomous without re-satisfying all graduation criteria. This is a critical safety net — the system can lose trust but must re-earn it.

**Mode Persistence:** Only one operational mode is active at any time, persisted across restarts.

### 5.3 Organizational Requirements

Beyond the technical system, the design mandates organizational guardrails:

- **20% mandatory human incident handling** — ensures SRE skill retention
- **Minimum 2 manual incidents per on-call shift** — regardless of random routing
- **Quarterly agent-disabled chaos days** — disable autonomous agent for a full business day; measure team response capability
- **SRE team training** on the agent's reasoning, capabilities, and limitations
- **Blameless post-mortems for agent actions** — same rigor applied to agent decisions as human responder decisions

---

## 6. Implementation Status

Based on `openspec/changes/autonomous-sre-agent/tasks.md`, the project is defined as **12 work streams** totaling **68 implementation tasks**. All tasks are currently in **NOT STARTED** state — this is a greenfield system in design phase.

### Work Stream Summary

| # | Work Stream | Task Count | Dependencies | Complexity |
|---|---|---|---|---|
| 1 | Telemetry Ingestion Pipeline | 6 tasks (1.1–1.6) | Foundation — no upstream deps | High (OTel + eBPF + correlation) |
| 2 | Anomaly Detection Engine | 5 tasks (2.1–2.5) | Depends on telemetry ingestion | High (ML models, baseline computation) |
| 3 | RAG Diagnostic Pipeline | 9 tasks (3.1–3.9) | Depends on anomaly detection; needs vector DB | Very High (LLM integration, confidence scoring, second-opinion) |
| 4 | Remediation Action Layer | 7 tasks (4.1–4.7) | Depends on diagnostics + severity classification | High (K8s API, ArgoCD, cert-manager, auto-rollback) |
| 5 | Safety Guardrails Framework | 11 tasks (5.1–5.11) | Cross-cutting — touches all subsystems | High (blast radius estimation, canary framework, kill switch, IAM) |
| 6 | Multi-Agent Coordination | 4 tasks (6.1–6.4) | Depends on remediation layer | Medium (distributed locking, priority enforcement) |
| 7 | Incident Learning Pipeline | 6 tasks (7.1–7.6) | Depends on diagnostics + remediation | Medium (indexing, pattern detection, mandatory routing) |
| 8 | Integration & Operational Readiness | 6 tasks (8.1–8.6) | Depends on all core subsystems | High (E2E testing, red-teaming, config management) |
| 9 | Severity Classification Engine | 5 tasks (9.1–9.5) | Depends on telemetry; feeds remediation | Medium (scoring model, service tier integration) |
| 10 | Phased Rollout Orchestrator | 6 tasks (10.1–10.6) | Depends on all core subsystems | Medium (state machine, gate evaluation, phase regression) |
| 11 | Notification & Escalation System | 7 tasks (11.1–11.7) | Depends on diagnostics + remediation | Medium (PagerDuty/Slack/Jira integrations) |
| 12 | Operator Dashboard | 5 tasks (12.1–12.5) | Depends on all subsystems for data | Medium (real-time UI, accuracy viz, timeline drill-down) |

### Critical Path

The recommended build order based on dependencies:

1. **Telemetry Ingestion** (foundation — everything depends on data)
2. **Anomaly Detection** (consumes telemetry, produces alerts)
3. **Severity Classification** (feeds authorization decisions to all downstream)
4. **RAG Diagnostics** (consumes alerts, produces diagnoses)
5. **Safety Guardrails** (must be in place before any autonomous action)
6. **Remediation Engine** (consumes diagnoses, gated by guardrails)
7. **Multi-Agent Coordination** (needed before production remediation)
8. **Phased Rollout Orchestrator** (controls operational mode)
9. **Notification System** (needed for escalation flows)
10. **Incident Learning Pipeline** (consumes resolved incidents)
11. **Operator Dashboard** (visualization layer, can be built incrementally)
12. **Integration & E2E Testing** (validates complete pipeline)

### Infrastructure Prerequisites

Before implementation begins, the following must be in place:
- OpenTelemetry deployed across >80% of services
- eBPF-capable Linux kernels on cluster nodes
- Vector database provisioned (Pinecone/Weaviate/Chroma — selection pending)
- LLM API access configured (provider selection pending)
- GitOps pipeline (ArgoCD/Flux) operational
- Kubernetes cluster access with appropriate service accounts
- Secrets management infrastructure (HashiCorp Vault or equivalent)
- Minimum 6 months of searchable incident history with post-mortems

### Formal Specifications

Each capability has a formal behavioral specification in `openspec/changes/autonomous-sre-agent/specs/` using WHEN/THEN/AND scenario syntax. These 11 spec files define the acceptance criteria for implementation:

```
specs/
├── telemetry-ingestion/spec.md    — 8 requirements, 12 scenarios
├── anomaly-detection/spec.md      — 5 requirements, 10 scenarios
├── rag-diagnostics/spec.md        — 5 requirements, 7 scenarios
├── remediation-engine/spec.md     — 3 requirements, 6 scenarios
├── safety-guardrails/spec.md      — 8 requirements, 10 scenarios
├── agent-coordination/spec.md     — 3 requirements, 5 scenarios
├── incident-learning/spec.md      — 4 requirements, 6 scenarios
├── severity-classification/spec.md — 4 requirements, 8 scenarios
├── phased-rollout/spec.md         — 5 requirements, 9 scenarios
├── notifications/spec.md          — 4 requirements, 7 scenarios
└── operator-dashboard/spec.md     — 5 requirements, 6 scenarios
```

---

*Source files: `openspec/changes/autonomous-sre-agent/proposal.md`, `design.md`, `tasks.md`, `specs/*/spec.md`, `Critical_Analysis_Autonomous_Incident_Response_and_Remediation.md`*