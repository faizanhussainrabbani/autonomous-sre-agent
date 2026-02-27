# Action Layer Architecture

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
