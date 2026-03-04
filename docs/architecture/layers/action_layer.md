# Action Layer Architecture

**Status:** DRAFT
**Version:** 1.0.0

This document details the final mile of the SRE Agent architecture: The Action & Guardrails Layer. This layer is responsible for translating the AI diagnosis into concrete infrastructure changes, enforcing strict safety limits, and orchestrating rollbacks if a remediation fails.

```mermaid
graph TD
    classDef input fill:#f9f9f9,stroke:#333,stroke-width:2px;
    classDef guardrail fill:#ffebee,stroke:#f44336,stroke-width:2px;
    classDef action fill:#e3f2fd,stroke:#2196f3,stroke-width:2px;
    classDef external fill:#eceff1,stroke:#607d8b,stroke-width:2px;

    subgraph Incoming ["From Intelligence Layer"]
        Routing[Action Policy Router]:::input
        DiagPayload[Diagnosis + Confidence + Severity + Recommendation]:::input
        Routing --> DiagPayload
    end

    subgraph ActionGuardrails ["Action & Guardrails Layer"]
        
        subgraph Safety ["Safety Guardrails Engine"]
            ConfCheck{Evidence Confidence Check}:::guardrail
            BlastRadius{Blast Radius Estimator}:::guardrail
            Policy[Organizational Policy Controls]:::guardrail
            HumanLoop[Human Approval Gate]:::guardrail
            MultiAgent[Agent Coordination Lock System]:::guardrail
            
            DiagPayload --> ConfCheck
            ConfCheck -->|Reject (Escalate/Halt)| EscalationRouter[Notifier]
            ConfCheck -->|Pass| BlastRadius
            BlastRadius -->|Fails Hard Limits| EscalationRouter
            BlastRadius -->|Pass| Policy
            Policy -->|Sev 1-2 or Novel| HumanLoop
            Policy -->|Sev 3-4 (Known)| MultiAgent
            
            HumanLoop -->|Reject| Halt[Halt Action]
            HumanLoop -->|Approve| MultiAgent
            MultiAgent -->|Acquire Resource Lock| Executor[Remediation Executor]
        end

        subgraph Execution ["Remediation Engine"]
            Executor:::action
            GitOps[GitOps PR / Revert Generator]:::action
            K8sDirect[Direct Kubernetes API Client]:::action
            PostMon[Post-Remediation Monitor]:::action
            AutoRevert[Auto-Rollback Trigger]:::action
            
            Executor -->|Configuration Changes| GitOps
            Executor -->|State Changes (Restart/Scale)| K8sDirect
            
            GitOps -->|Commit/PR| TargetGit[(Git Repository)]
            K8sDirect -->|API Calls| TargetK8s[(Kubernetes Cluster)]
            
            Executor -->|Start Observation| PostMon
            PostMon -->|Metrics Degraded| AutoRevert
            AutoRevert -->|Undo Action| GitOps
            AutoRevert -->|Undo Action| K8sDirect
            
            PostMon -->|Metrics Stabilized| Resolve[Incident Resolved → Knowledge Base]
        end

    end

    subgraph External ["Target Infrastructure"]
        TargetGit:::external
        TargetK8s:::external
        ArgoCD[ArgoCD Controller]:::external
        TargetGit -->|Sync| ArgoCD
        ArgoCD -->|Apply Config| TargetK8s
    end
```

## Component Details

1. **Safety Guardrails Engine:** Acts as the impenetrable shield. Contains check components such as the Confidence Gate, Blast Radius Evaluator, and the Multi-Agent Coordination lock (prevents oscillation or race conditions between multiple AI agents).
2. **Remediation Executor:** Routes authorized changes to either safe GitOps paths (e.g., reverting a bad commit via ArgoCD) or direct K8s API interactions (e.g., Pod Restarts, scaling up).
3. **Post-Remediation Monitor:** The critical feedback loop. After an action is executed, metrics are observed. If the system degrades further, the Auto-Rollback capability immediately reverts the changes and escalates the incident to a human operator.


---

## Detailed Architecture

# Action & Guardrails Layer: Detailed Breakdown

**Status:** DRAFT
**Version:** 1.0.0

This document provides a comprehensive breakdown of the **Action & Guardrails Layer** of the SRE Agent. It details the core features, external libraries, and integration points required to safely execute remediations in production, enforce strict business policies, and orchestrate rollbacks.

## 1. Core Features

The Action Layer is where the agent touches reality. Its primary goal is to ensure that *any* action taken is safe, auditable, and easily reversible.

### 1.1 Safety Guardrails Engine
*   **Confidence Gating:** Rejects any action if the Intelligence Layer's evidence-weighted confidence score falls beneath a hard-coded threshold (e.g., < 85%).
*   **Blast Radius Limiter:** Evaluates the proposed action against organizational limits. Example: "Never restart more than 20% of pods simultaneously in a single cluster."
*   **Multi-Agent Coordination (Locks):** Uses a distributed locking system to prevent the SRE Agent from conflict with a FinOps agent (e.g., SRE agent scales up, FinOps agent immediately scales down).

### 1.2 GitOps & API Execution
*   **Idempotent API Execution:** Executes immediate, low-risk state changes directly via Kubernetes APIs (e.g., standard pod restarts, horizontal scaling adjustments).
*   **GitOps PR Generation:** For configuration changes, infrastructure rollbacks, or complex patches, the agent generates a Pull Request (PR) or Git Revert commit, preserving a perfect audit trail.

### 1.3 Post-Remediation Monitoring & Auto-Rollback
*   **Validation Window:** After executing an action, the agent enters a "wait and watch" state (e.g., 5-10 minutes) to monitor key metrics.
*   **Auto-Rollback:** If error rates spike or latency degrades further during the validation window, the agent automatically reverts the action (e.g., via ArgoCD rollback) and escalates to a human.

### 1.4 Interactive Escalation & Notification
*   **Human-in-the-Loop Routing:** For Sev 1-2 incidents, the agent pauses execution and pushes interactive buttons (Approve/Reject) to Slack.
*   **Audit Logging:** Records every decision, LLM prompt, retrieved document, and executed API call into an immutable ledger for post-incident review.

---

## 2. External Libraries & Dependencies

The Action Layer relies on declarative infrastructure tools and robust SDKs to safely interact with the target environment and human operators.

### 2.1 Infrastructure & Orchestration Execution

| Dependency | Component Type | Purpose in the SRE Agent |
| :--- | :--- | :--- |
| **Kubernetes (k8s) Client** | Target Infrastructure API | Used directly via the Python `kubernetes-client` to execute immediate state changes (like deleting a stuck pod or patching a deployment's scale). |
| **ArgoCD / Flux** | GitOps Controllers | The preferred execution path. The agent modifies Git, and these controllers safely reconcile the target Kubernetes state to match Git. Ensures perfect auditability. |
| **cert-manager** | K8s Add-on | The agent interfaces with this to automatically renew or rotate x509 certificates that are nearing expiration. |
| **Cloud Provider SDKs** | AWS `boto3` / Azure SDK | Used for remediations that fall outside of K8s, such as adjusting an ASG, modifying DNS routing (Route53), or resizing a cloud volume. |
| **CloudOperatorPort** (Phase 1.5) | Remediation Abstraction | Unified `restart_compute_unit()` / `scale_capacity()` interface for non-K8s targets. Adapters: `ECSOperator` (AWS ECS), `EC2ASGOperator` (EC2 ASG), `LambdaOperator` (Lambda concurrency), `AppServiceOperator` (Azure App Service), `FunctionsOperator` (Azure Functions). Selected at runtime via `CloudOperatorRegistry` based on `compute_mechanism` + provider. |

### 2.2 Security, Locking, & State Management

| Dependency | Component Type | Purpose in the SRE Agent |
| :--- | :--- | :--- |
| **HashiCorp Vault** (or AWS Secrets) | Secrets Manager | Critical for security. The agent must retrieve temporary tokens to execute K8s or GitHub actions. No API keys are stored in the agent's memory or config. |
| **Redis / etcd** | Distributed Datastore | Used to establish Mutual Exclusion Locks ("mutex"). Prevents the agent from acting on a service while another team (or another AI agent) is modifying it. |
| **Open Policy Agent (OPA)** | Policy Engine | Used optionally to define blast-radius rules declaratively (e.g., rego policies that deny an API call if it targets a "Tier-0" critical namespace). |

### 2.3 Notification & Human-in-the-loop

| Dependency | Component Type | Purpose in the SRE Agent |
| :--- | :--- | :--- |
| **Slack / MS Teams API** | ChatOps Integration | Used to deliver rich Block-Kit messages outlining the incident, the proposed remediation, and "Approve/Reject" buttons for human oversight. |
| **PagerDuty / OpsGenie** | Escalation Backend | Triggered when the agent encounters a novel incident, lacks confidence, or an auto-rollback fails. |
| **Jira / Linear SDK** | Issue Tracking | Used to automatically file detailed tickets wrapping up the incident timeline and actions taken for organizational record-keeping. |

### 2.4 Agent Internal Libraries (Python Core)

| Python Library | Purpose |
| :--- | :--- |
| `kubernetes` | The official Python client for interacting with the K8s API server. |
| `PyGithub` | Used to manipulate Git repositories, create branches, and open Pull Requests for GitOps-based remediations. |
| `redis-py` | Used to implement the distributed locking mechanism for Multi-Agent coordination. |
| `slack_sdk` | Used to construct the interactive notification payloads sent to human operators. |

---

## 3. Data Flow Example: Executing a Safe Rollback

1. **Authorization:** The Intelligence Layer passes a Sev-3 recommendation: "Rollback `payment-svc` to previous commit due to latency spike post-deploy."
2. **Guardrail Check:** The **Safety Guardrail Engine** verifies the confidence is > 90%. It checks **Redis** and confirms no other agent holds a lock on `payment-svc`.
3. **Execution Path:** Because this is a configuration/code issue, it routes to the GitOps executor.
4. **GitOps Action:** The agent uses `PyGithub` to open a PR against the infrastructure repo, reverting the specific commit hash.
5. **Reconciliation:** **ArgoCD** detects the merged PR and syncs the Kubernetes cluster, terminating the bad pods and spinning up the old, stable version.
6. **Validation & Resolution:** The **Post-Remediation Monitor** watches latency metrics via Prometheus. After 5 minutes, latency returns to the baseline.
7. **Audit:** The agent posts a summary to **Slack** ("Resolved payment-svc latency via ArgoCD rollback"), logs the total flow to an internal DB, and releases the Redis lock.
