# Operational Readiness Review (ORR)

**Service:** Autonomous SRE Agent
**Status:** DRAFT (Pre-Production Phase 1)
**Reviewer:** [TBD]

## 1. Architecture & Capacity Planning

### 1.1 Compute Requirements
The agent runs as a unified deployment within the management Kubernetes cluster.
*   **CPU:** Base: 2 vCPU. Scales linearly with incident correlation load.
*   **Memory:** Base: 4GB RAM (heavy ML heuristic processing caching). Spikes to 8GB during active massive RAG context window generation.
*   **Storage:** 50GB Ephemeral for localized vector DB caching and temporary log aggregation during investigation.

### 1.2 Scaling Characteristics
*   **Bottleneck:** Vector Database similarity search and LLM context generation latency.
*   **Scaling Trigger:** Number of concurrent active incidents across the fleet. HPA configured to scale agent replicas at 70% CPU utilization.

## 2. Failure Modes & Degradation

### 2.1 Dependencies & SLAs
| Dependency | Criticality | SLA Expectation | Failure Behavior |
|------------|-------------|-----------------|------------------|
| Kubernetes API | Critical | 99.99% | Agent halts remediation. Fails **Closed** (safe). |
| OTel Collector | Critical | 99.99% | Agent stops receiving signals. Fails **Closed**. |
| LLM API Provider | High | 99.9% | Agent cannot diagnose new incidents. Halts autonomous action, falls back to static PagerDuty routing. |
| Vector DB | High | 99.9% | Cannot execute RAG. Same as LLM failure. |
| Distributed Lock (Redis) | Critical | 99.99% | Cannot acquire safety locks. Agent refuses to act. Fails **Closed**. |

### 2.2 Global Kill Switch
*   **Mechanism:** Immediate state-flag toggle in Redis + API endpoint `/api/v1/system/halt`.
*   **Recovery:** Requires manual un-toggling via authenticated API call and dual SRE sign-off.

## 3. Observability & Auditing

### 3.1 Emitted Metrics
*   `sre_agent_active_incidents`: Gauge of currently managed incidents.
*   `sre_agent_remediation_success_rate`: Counter tracking successful vs rolled-back autonomous actions.
*   `sre_agent_rag_latency_ms`: Histogram of diagnostic reasoning speeds.

### 3.2 Audit Logging
*   All agent decisions (metrics evaluated, documents retrieved, LLM prompt and response, confidence score) are written immutably to S3/GCS.
*   Log retention is 7 years for compliance tracking of automated infrastructure changes.

## 4. Operational Runbooks
*   [Agent Failure Runbook](runbooks/agent_failure_runbook.md)
*   [Incident Response Runbook](runbooks/incident_response.md)

## 5. Sign-off
*   [ ] Primary Engineer
*   [ ] Security Review
*   [ ] SRE Lead
