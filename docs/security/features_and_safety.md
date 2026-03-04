# Features & Safety Guardrails

**Status:** DRAFT
**Version:** 1.0.0

The SRE Agent targets well-understood, repeatable infrastructure incidents. Because the agent executes modifications autonomously, **safety is the most critical feature.**

## Supported Use Cases
The agent currently focuses on 5 highly repeatable incident types, which have idempotent and safe remediation paths. 

See the **[Incident Taxonomy Table](../architecture/models/incident_taxonomy.md)** for a complete breakdown of detection signals, approved remediations, blast-radius limits, and rollback strategies.

*Explicit Non-Goals:* The agent does not attempt to resolve novel failures lacking historical data, stateful database schema changes, business logic errors, or complex security incidents.

## Severity Classification Engine
Incidents are classified into severity levels, dynamically shifting the agent's permission boundaries:

| Severity | Description | Agent Capability |
|----------|-------------|------------------|
| **Sev 1** | Enterprise-wide impact, revenue loss. | **Human Only**. No autonomous action. |
| **Sev 2** | Critical service degraded. | Propose remediation. **Requires human approval**. |
| **Sev 3** | Single non-critical service degraded. | **Autonomous action** (Subject to guardrails). |
| **Sev 4** | Sub-component failure, easily idempotent limit. | **Autonomous action**. |

## Safety Guardrails Framework

Our three-tiered safety framework guarantees that the agent's actions remain within bounded blast radiuses while minimizing LLM hallucinations.

### Tier 1: Action Execution Guardrails
These wrap the execution phase directly (see [Guardrails Configuration](guardrails_configuration.md) for exact limits):
1. **Evidence-Weighted Confidence:** The RAG diagnostic engine must present concrete evidence from the historical KB. If the confidence score is below threshold, action falls back to humans.
2. **Blast Radius Hard Limits:** Hard-coded limits per action (e.g., the agent can never restart >20% of pods fleet-wide).
3. **Canary Execution:** Remediation is applied to 5% of traffic/instances first and verified before fleet-wide rollout.
4. **Auto-Rollback:** If target metrics degrade following a remediation, the agent will roll back and alert a human.
5. **Global Kill Switch:** An API/Slack accessible switch that instantly halts all agent actions globally.

### Tier 2: Knowledge & Reasoning Guardrails
These target the RAG subsystem to prevent catastrophic LLM hallucinations:
1. **[PLANNED] Mandatory Citations:** Root-cause hypothesis *must* cite retrieved evidence vectors.
2. **[PLANNED] Second-Opinion Validation:** An independent validator cross-checks the LLM's primary diagnosis. Disagreement causes human escalation.
3. **[PLANNED] Knowledge Base Expiry (TTL):** Architecture changes constantly; documents older than 90 days trigger staleness recalculation.

### Tier 3: Security & Access Limitations
1. **[PLANNED] Least-Privilege Roles:** Kubernetes ServiceAccounts are tightly scoped. 
2. **Multi-Agent Locking:** In severe outages, multiple agents running in parallel use distributed locks (etcd/Redis) to prevent contradictory "oscillation" behaviors.
3. **[PLANNED] No Direct Secret Access:** Externalized secret management via Hashicorp Vault/AWS SM.
