# Autonomous SRE Agent Constitution

## Core Principles

### I. Safety-First Autonomy (NON-NEGOTIABLE)
Every agent capability MUST be gated by safety guardrails before it can take production action. The three-tier safety framework (Action Execution → Knowledge & Reasoning → Security & Access) is the highest-priority architectural concern. No feature ships without its safety constraints implemented and tested.

- Evidence-weighted confidence gating on all autonomous actions — never use LLM self-reported confidence
- Hard-coded blast radius limits per action type — no single agent action may affect more than 20% of a fleet
- Canary execution pattern: apply to subset first, validate, then expand
- Kill switch accessible to any authorized team member at all times
- If in doubt, escalate to human — the agent must prefer false negatives over false positives

### II. Human-in-the-Loop by Default
The system augments SRE teams; it does not replace them. Autonomous operation is earned through phased graduation, not granted by configuration.

- Phase 1 (Observe): Agent takes ZERO actions — shadow mode only
- Humans must explicitly approve phase transitions via dual sign-off
- 20% of agent-capable incidents are always routed to humans (skill retention)
- Minimum 2 manual incidents per on-call shift regardless of routing
- Automatic phase regression on any safety violation (blast-radius breach, worsened incident)

### III. RAG-Grounded Reasoning (NON-NEGOTIABLE)
All diagnostic reasoning MUST be grounded in organizational evidence retrieved via RAG. Pure LLM generation without RAG source citations is never acceptable as a basis for production action.

- Every diagnosis must cite specific retrieved documents with similarity scores
- Novel incidents (no RAG match above threshold) are escalated, never guessed
- Second-opinion validation required before any remediation proceeds
- Knowledge base documents carry 90-day TTL with automated staleness detection
- Agent-generated runbooks require human review before entering the production knowledge base

### IV. Reversibility & Idempotency
The system only automates actions that are safe, reversible, and idempotent. Stateful changes, data mutations, and irreversible operations are permanently excluded from autonomous scope.

- All remediation actions must have a defined rollback path
- Post-remediation verification monitors metrics and auto-reverts if degradation occurs
- GitOps (ArgoCD) for deployment rollbacks — ensures version-controlled, auditable changes
- Scope is limited to 5 well-understood incident types: OOM, traffic spikes, deployment regressions, cert expiry, disk exhaustion

### V. Observable & Auditable
Every agent action, query, decision, and state change must be logged immutably and be fully inspectable by any team member.

- Complete provenance tracking: which documents, data, and reasoning steps informed each diagnosis
- Tamper-evident audit logs for every action and decision
- Operator dashboard with real-time agent status, confidence breakdown, and accuracy metrics
- Resolution summaries auto-generated within 5 minutes of resolution

### VI. Test-Driven & Spec-Driven Development
All implementation follows the specifications defined in OpenSpec. Acceptance criteria are the WHEN/THEN scenarios from spec files. No code is merged without corresponding test coverage.

- OpenSpec specs define WHAT to build; Spec Kit plans define HOW to build it
- Every requirement has at least one testable scenario
- Integration tests validate end-to-end pipeline (detect → diagnose → remediate → verify → learn)
- Adversarial red-teaming validates prompt injection defenses

## Technology Constraints

- **Telemetry:** OpenTelemetry (vendor-neutral) + eBPF for kernel-level depth; no proprietary APM lock-in (with graceful degradation on Serverless/PaaS platforms lacking eBPF support per Phase 1.5)
- **Knowledge Base:** Vector database (Pinecone/Weaviate/Chroma) for RAG — selection open
- **LLM Provider:** Self-hosted or cloud API — selection open; must support provenance tracking
- **Deployment:** GitOps via ArgoCD/Flux for deterministic, auditable rollbacks
- **Coordination:** Distributed locks (etcd/Redis) for multi-agent mutual exclusion
- **Infrastructure Minimum:** >80% OTel service coverage, eBPF-capable Linux kernels (except for supported Serverless environments), 6+ months of searchable incident history
- **Compute Targeting:** Must support agnostic remediation via `CloudOperatorPort` definitions (AWS ECS, EC2, Lambda; Azure App Service, Functions) in addition to Kubernetes-native APIs.

## Development Workflow

1. **Plan:** Use Spec Kit (`/speckit.specify` → `/speckit.plan` → `/speckit.tasks`) to create phase-scoped implementation plans
2. **Spec Validation:** Cross-reference all implementation against OpenSpec scenario acceptance criteria
3. **Build:** Implement in dependency order (telemetry → detection → diagnostics → remediation → safety → coordination → rollout)
4. **Test:** Unit tests + integration tests + adversarial red-teaming before any phase graduation
5. **Deploy:** Shadow mode first in all environments; graduate through phases with measured criteria

## Governance

- This constitution supersedes all other development practices for the autonomous SRE agent
- Amendments require documented rationale, team review, and impact assessment
- Safety principles (I, II, III) are non-negotiable and cannot be weakened without executive sign-off
- All code reviews must verify compliance with the safety-first principles above

**Version**: 1.0.0 | **Ratified**: 2026-02-25 | **Last Amended**: 2026-02-25
