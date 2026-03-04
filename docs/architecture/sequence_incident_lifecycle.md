# Sequence: Incident Lifecycle

**Status:** DRAFT
**Version:** 1.0.0

This diagram outlines the end-to-end flow of an incident, from initial detection through autonomous remediation and resolution verification.

```mermaid
sequenceDiagram
    participant Obs as Observability (OTel/eBPF)
    participant Det as Detection Layer
    participant Int as Intelligence (RAG)
    participant Gov as Orchestration (Locks)
    participant Act as Action Engine
    participant K8s as Target Infra (K8s/Argo)
    participant Hum as Human Operator
    
    Obs->>Det: Stream Metrics & Logs
    
    rect rgb(240, 248, 255)
        Note over Det: Detection Phase
        Det->>Det: Correlate Anomaly (CPU + Latency)
        Det-->>Int: Create Canonical Incident
    end

    rect rgb(255, 245, 238)
        Note over Int: Diagnostic Phase
        Int->>Int: Search Vector DB (Post-Mortems)
        Int->>Int: Generate Hypothesis & Confidence
        
        alt Sev 1-2 Incident
            Int->>Hum: Escalate immediately (High Severity)
        else Sev 3-4 Incident
            Int->>Int: Proceed to Autonomy Check
        end

        alt Confidence < Threshold
            Int->>Hum: Escalate (Low Confidence)
        else Confidence ≥ Threshold
            Int->>Gov: Request Remediation (Restart Pods)
        end
    end
    
    rect rgb(240, 255, 240)
        Note over Gov: Governance & Coordination
        Gov->>Gov: Check Blast Radius & Guardrails
        Gov->>Gov: Request Distributed Lock (Redis)
        Gov-->>Act: Lock Granted, Proceed
    end

    rect rgb(255, 240, 245)
        Note over Act,K8s: Execution & Verification
        Act->>K8s: Execute Action (Rollout Restart)
        Act->>K8s: Wait for Ready State
        
        K8s-->>Obs: New Telemetry Emitted
        Obs-->>Det: Metrics Update
        
        alt Metrics Normalize
            Det-->>Act: Verification Complete (Success)
            Act->>Gov: Release Distributed Lock
            Act->>Int: Record Successful Resolution
        else Metrics Degrade
            Det-->>Act: Verification Failed (Regression)
            Act->>K8s: Execute Rollback (GitOps Revert)
            
            alt Revert Successful
                Act->>Int: Record Resolution via Revert
            else Revert Fails
                Act->>Hum: Escalate (Rollback Failed)
            end
            Act->>Gov: Release Distributed Lock
        end
    end
```
