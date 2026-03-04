# Service Level Objectives (SLOs) & Error Budgets

**Service:** Autonomous SRE Agent
**Status:** DRAFT
**Version:** 1.0.0

As an autonomous Tier-1 infrastructure component, the SRE Agent must be held to extremely strict performance and safety standards. This document defines the SLOs and the Error Budget policies that govern its development speed vs. reliability.

---

## 1. Service Level Indicators (SLIs) & Objectives (SLOs)

### 1.1 Availability SLO
**Target: 99.99% per month (4.32 minutes of allowed downtime/month)**
*   **SLI:** The percentage of successful `HTTP 200 OK` health check responses over total health checks sent to the `/healthz` endpoint every 10 seconds.
*   **Rationale:** The agent is the first line of defense during outages. If the agent is down when an application fails, MTTR spikes dramatically.

### 1.2 Diagnostic & Remediation Latency SLO
**Target: 99th percentile < 30 seconds**
*   **SLI:** The time elapsed from `EventType.ANOMALY_DETECTED` to `EventType.REMEDIATION_ACTION_PROPOSED` or `IncidentPhase.REMEDIATING` (the moment an API call is made to a `CloudOperatorPort` or K8s API).
*   **Rationale:** The core value proposition of the agent is acting at machine speed. Slow RAG context generation defeats the purpose of the platform.

### 1.3 Accuracy & Safety SLO (False Positives)
**Target: 99.9% Safe Actions**
*   **SLI:** The ratio of *successful remediations* (no auto-rollback triggered, no human intervention required to fix the agent's action) to total autonomous actions taken.
*   **Rationale:** False positives are extremely dangerous. Restarting the wrong database node is worse than not acting at all.

---

## 2. Error Budgets and Consequences

### 2.1 The Error Budget Drop
If any SLO target is breached in a rolling 30-day window, the Error Budget is considered **exhausted**.

### 2.2 Repercussions of Exhaustion
When the agent's error budget drops below 0:
1.  **Halt Feature Development:** All work on Phase 1.5, Phase 2, or new capabilities must cease.
2.  **Phase Regression:** The agent is automatically downgraded one Operational Phase (e.g., from *Autonomous* down to *Assist* mode), requiring human approval for all actions.
3.  **Mandatory Reliability Sprint:** The engineering team must divert 100% of capacity to fixing the root cause of the SLO breach (e.g., improving RAG caching to fix latency, or tuning ML heuristics to fix false positives).

The agent may only return to normal operational phases once the 30-day rolling window recovers the error budget above zero.
