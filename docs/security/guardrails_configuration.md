# Guardrails Configuration

This document defines the quantitative, hard-coded boundaries that restrict the SRE Agent's autonomous actions. These Tier 1 execution guardrails act as the absolute safety net, regardless of the Intelligence Layer's confidence.

| Guardrail | Parameter Scope | Allowed Value | Rationale |
|-----------|-----------------|---------------|-----------|
| **Max concurrent pod restarts** | per-namespace | 3 | Prevent cascading failures or service unavailability during rolling restarts |
| **Max fleet-wide restarts** | global | 10% of total | Protect global cluster capacity |
| **Confidence threshold (escalate)** | global | < 0.70 | Immediate escalation to human without proposing action |
| **Confidence threshold (propose)** | global | >= 0.70, < 0.85 | Agent proposes a PR / ChatOps button, waits for human |
| **Confidence threshold (act)** | global | >= 0.85 | Agent acts autonomously (if in Phase 3) based on Phase 2 calibration |
| **Cooling off period** | per-resource | 15 min | Prevents oscillation (e.g., repeatedly restarting a crashing pod). The agent cannot act on the same resource within this window. |
| **Max scale-up factor** | per-deployment | 2x current replicas | Financial/Budget constraint to prevent infinite scaling loops |
| **Max rollback depth** | global | 1 Git commit | Prevent reverting a deployment too far back and losing critical database migrations |
| **Agent action timeout** | per-action | 180 seconds | If the action (e.g., GitOps sync) hangs, the lock is released and humans are alerted |
