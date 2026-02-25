## Context

Modern SRE teams manage hundreds of microservices with complex interdependencies. When incidents occur, engineers must manually query multiple observability backends (Prometheus, Jaeger, ELK), correlate signals across layers, consult historical post-mortems, and execute remediation actions — a process that averages 45+ minutes even for well-understood incidents. The current state relies on static alerting (PagerDuty/OpsGenie), manual investigation, and ad-hoc runbook execution.

This design proposes an autonomous SRE agent system that automates the detect → investigate → diagnose → remediate → learn pipeline for well-understood, repeatable incidents with safe, reversible remediations.

## Goals / Non-Goals

**Goals:**
- Reduce MTTR by 40–50% for well-understood incidents (OOM kills, traffic spikes, deployment regressions, certificate expirations, disk exhaustion)
- Provide RAG-grounded diagnostic reasoning that prevents LLM hallucination from driving production actions
- Implement three-tier safety guardrails (action execution, knowledge/reasoning, security/access) that constrain autonomous behavior
- Support a phased rollout (shadow mode → assisted → autonomous → predictive) with measurable graduation gates
- Prevent multi-agent conflicts when SRE, cost-optimization, security, and compliance agents operate on shared infrastructure

**Non-Goals:**
- Replacing SRE teams or handling novel, never-before-seen failure modes autonomously
- Automating stateful/irreversible actions (data migration rollbacks, schema changes)
- Automating security incident response (requires forensic evidence preservation)
- Multi-team coordination incidents requiring human judgment and communication
- Business-logic error remediation requiring domain expertise beyond infrastructure patterns

## Decisions

### Decision: OpenTelemetry + eBPF for Telemetry (over proprietary APM agents)

OpenTelemetry provides vendor-neutral, standardized instrumentation for metrics, logs, and traces. eBPF adds kernel-level telemetry without sidecar overhead (~1-2% CPU).

**Alternatives considered:**
- **Proprietary APM (Datadog/New Relic):** Vendor lock-in; higher cost; limited access to raw kernel-level data
- **OTel-only (no eBPF):** Misses syscall-level visibility, network flow tracing within service meshes, and process behavior monitoring

**Rationale:** OTel gives breadth (full-stack correlation), eBPF gives depth (kernel-level precision). The combination provides the highest-fidelity signal for ML anomaly detection and agentic investigation.

### Decision: RAG with Vector Database (over fine-tuned LLM)

Use Retrieval-Augmented Generation to ground LLM reasoning in organizational historical data, rather than fine-tuning a model on incident data.

**Alternatives considered:**
- **Fine-tuned LLM on incident data:** Data quality challenges; expensive to maintain; can't easily add new incidents; risk of overfitting to historical patterns
- **Pure LLM reasoning (no RAG):** High hallucination risk; no organizational context; generic diagnoses

**Rationale:** RAG allows dynamic knowledge updates (new post-mortems indexed immediately), provides provenance tracking (agent cites exact sources), and avoids the data pipeline complexity of fine-tuning. Hallucination mitigation is the primary architectural benefit.

### Decision: Evidence-Weighted Confidence (over LLM self-reported confidence)

Score confidence based on structural evidence checks (trace correlation, timeline matching, RAG retrieval quality) rather than the LLM's self-reported confidence score.

**Alternatives considered:**
- **LLM self-reported confidence thresholds (e.g., >85%):** LLMs are poorly calibrated; express 95% confidence on hallucinated outputs; not a reliable gating mechanism
- **Ensemble voting (multiple LLMs):** Higher latency; higher cost; marginal improvement over single-model + evidence checks

**Rationale:** Structural evidence checks are objective and verifiable: "Does the diagnosis have supporting trace data? Does the timeline correlate? Is there a matching RAG retrieval?" This is fundamentally more reliable than asking the model how confident it feels.

### Decision: GitOps via ArgoCD (over direct kubectl/API execution) for deployment remediation

Route deployment-related remediations through GitOps rather than direct API calls.

**Alternatives considered:**
- **Direct kubectl/API execution:** Faster but no audit trail, non-deterministic rollbacks, harder to review
- **PR-based GitOps with mandatory review:** Safest but too slow for incident response (human review bottleneck)

**Rationale:** ArgoCD Git revert provides version-controlled, auditable, deterministic rollbacks. The agent creates the Git revert commit directly (no PR review for Sev 3-4 incidents); for Sev 1-2, it creates a PR for human approval. This balances speed with safety.

### Decision: Mutual Exclusion Locks for Multi-Agent Coordination (over centralized orchestrator)

Use distributed locks on resources being remediated, rather than a centralized agent orchestrator.

**Alternatives considered:**
- **Centralized orchestrator/control plane:** Single point of failure; adds latency; complex to build
- **No coordination (best-effort):** Risk of oscillation loops (SRE scales up, cost agent scales down)

**Rationale:** Distributed locks are simpler to implement, have no single point of failure, and leverage existing distributed systems infrastructure (etcd/Redis). Combine with a priority hierarchy (Security > SRE > Cost Optimization) for deterministic conflict resolution.

## Risks / Trade-offs

| Risk | Severity | Mitigation |
|------|----------|------------|
| LLM hallucination leads to incorrect diagnosis and destructive remediation | Critical | Evidence-weighted confidence + "second opinion" pattern + canary execution + automatic rollback |
| Blast radius amplification — agent acts at machine speed | High | Hard-coded blast radius limits per action type + canary execution (5% first) + kill switch |
| RAG knowledge base becomes stale as architecture evolves | Medium-High | 90-day TTL on documents + automated staleness detection against live dependency graph + quarterly audit |
| Agent-on-agent oscillation (SRE vs. cost optimization) | Medium | Mutual exclusion locks + priority hierarchy + oscillation pattern detection |
| SRE skill atrophy from over-reliance on agent | Medium | 20% mandatory human routing + quarterly agent-disabled chaos days + on-call manual quota |
| Adversarial prompt injection via crafted log entries | Medium | Input sanitization on all telemetry before LLM ingestion + adversarial red-teaming |
| Vector database latency during high-incident-volume periods | Medium | Cache frequently retrieved post-mortems + async pre-warming of similarity search for known alert patterns |
| OpenTelemetry instrumentation gaps in legacy services | Low-Medium | Require >80% service coverage before Phase 2; use eBPF for uninstrumented services as fallback |

## Open Questions

1. **LLM provider selection:** Self-hosted (Llama) vs. cloud API (GPT/Claude/Gemini)? Trade-off between latency, cost, data privacy, and model quality. Security-sensitive environments may require self-hosted.
2. **Vector database selection:** Pinecone (managed, scalable) vs. Weaviate (self-hosted, more control) vs. Chroma (lightweight, dev-friendly)? Depends on scale and operational preference.
3. **Blast radius threshold tuning:** The 20% pod restart limit is a starting point. What's the right threshold per action type? Likely needs empirical tuning during Phase 1 (shadow mode).
4. **Phase graduation authority:** Who signs off on phase transitions? Engineering leadership + SRE team lead + on-call SRE rotation? Need clear RACI.
