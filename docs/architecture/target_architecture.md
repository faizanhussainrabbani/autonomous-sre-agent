# Target Architecture (Phase 4 Final State)

This document visualizes the complete end-state architecture of the SRE Agent after Phase 4 (PREDICTIVE) is fully rolled out. It expands upon the initial architecture to include predictive tracking, structural degradation detection, and the feedback loop for the autonomous knowledge base.

```mermaid
graph TD
    subgraph Observability ["Observability Layer"]
        OTel[OpenTelemetry Collector]
        eBPF[eBPF Programs]
        Cloud[Cloud Provider APIs]
    end

    subgraph Intelligence ["SRE Agent Core (Cognitive & Predictive)"]
        Ingest[Telemetry Ingestion Pipeline]
        
        subgraph Detection ["Analysis & Detection"]
            Detect[ML Anomaly Detection Engine]
            Predictive[Predictive Analytics Engine]
            Trend[Trend & Resource Forecaster]
        end
        
        Diag[RAG Diagnostic Pipeline]
        VectorDB[(Diagnostic Knowledge Base)]
        Severity[Severity Classification & Impact Scoring]
    end

    subgraph Actions ["Action & Guardrails Layer"]
        Guardrails[Safety Guardrails & Policy Engine]
        Workflow[Autonomous Routing Workflow]
        Remediation[Remediation & GitOps Engine]
    end

    subgraph Target ["Target Infrastructure"]
        K8s[Kubernetes API]
        GitOps[ArgoCD / IaC Controllers]
        Infra[Cloud Infrastructure]
    end

    %% Flow - Ingestion
    OTel -->|Metrics/Traces/Logs| Ingest
    eBPF -->|Kernel/Network| Ingest
    Cloud -->|Infrastructure Events| Ingest

    %% Analysis
    Ingest --> Detect
    Ingest --> Predictive
    Predictive --> Trend

    %% Diagnosis
    Detect -->|Real-time Anomalies| Diag
    Trend -->|Predicted Exhaustion/Degradation| Diag
    Detect -->|Alerts| Severity
    
    %% RAG & KB
    Diag <-->|Historical Context & Similar Incidents| VectorDB
    Diag -->|Hypothesis & Root Cause| Severity
    
    %% Action Routing
    Severity -->|Prioritized Incidents & Predictions| Guardrails
    Guardrails --> Workflow
    
    %% Phase 3 & 4 Gating
    Workflow -->|Known Incident/Predicted Trend| Remediation
    Workflow -->|Novel/Unrecognized Scenario| Human[Human Operator]
    Workflow -->|Random 20 Percent Audit - Skill Atrophy Prevention| Human
    
    Human -->|Approve/Override| Remediation
    
    %% Remediation Execution
    Remediation -->|State Changes / Scaling / Reverts| K8s
    Remediation -->|Config Updates| GitOps
    Remediation -->|Capacity Adjustments| Infra
    
    %% Feedback Loop
    Remediation -->|Action Outcome & Telemetry Delta| VectorDB
```
