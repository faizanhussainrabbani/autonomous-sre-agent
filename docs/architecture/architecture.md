# System Architecture Overview

The SRE Agent is designed as a sophisticated, layered processing pipeline that translates raw infrastructure telemetry into actionable incidents, autonomous diagnoses, and safe remediation.

## High-Level System Architecture and Data Flow

The agent operates across four primary layers:
1. **Observability Layer:** Gathers raw signals.
2. **Intelligence Layer (SRE Agent Core):** The brain processing the signals.
3. **Action Layer:** Gating and execution.
4. **Target Infrastructure:** The environment being managed.

```mermaid
graph TD
    subgraph Observability ["Observability Layer"]
        OTel[OpenTelemetry Collector]
        eBPF[eBPF Programs]
    end

    subgraph Intelligence ["SRE Agent Core"]
        Ingest[Telemetry Ingestion Pipeline]
        Detect[ML Anomaly Detection Engine]
        Diag[RAG Diagnostic Pipeline]
        Severity[Severity Classification]
    end

    subgraph Actions ["Action Layer"]
        Remediation[Remediation Engine]
        Guardrails[Safety Guardrails]
    end

    subgraph Target ["Target Infrastructure"]
        K8s[Kubernetes API]
        GitOps[ArgoCD / GitOps]
    end

    %% Flow
    OTel -->|Metrics/Traces/Logs| Ingest
    eBPF -->|Kernel/Network| Ingest
    Ingest --> Detect
    Detect -->|Anomalies| Diag
    Detect -->|Alerts| Severity
    Diag -->|Hypothesis & Root Cause| Severity
    
    Severity -->|Sev 3-4 (Autonomous)| Guardrails
    Severity -->|Sev 1-2 (Propose)| Human[Human Operator]
    
    Human -->|Approve| Guardrails
    Guardrails -->|Authorized Action| Remediation
    Remediation --> K8s
    Remediation --> GitOps
```

## Abstracting the Backends: Provider Abstraction Layer
A core tenet of the SRE Agent's design is **Provider-Agnosticism**. 

The core anomaly detection and RAG logic *never* calls a specific tool's API directly (e.g., it never directly invokes a PromQL or an NRQL query). Instead, it communicates via a canonical internal data model using **Ports** (Interfaces). 

Specific **Adapters** implement these queries based on the target backend (e.g., `PrometheusAdapter`, `NewRelicAdapter`). This ensures the agent is highly portable and not locked into a single telemetry vendor or cloud provider.

## Subsystems

1. **Telemetry Ingestion:** Collects metrics, logs, traces (via OTel), and eBPF kernel telemetry.
2. **Anomaly Detection Engine:** ML-based baselining of metrics (no static thresholds). Combines multi-dimensional metrics to identify complex issues.
3. **RAG Diagnostic Pipeline:** Embeds the anomaly context and uses a Vector DB to search past incident histories. Feeds this data to an LLM Reasoning Engine to deduce root causes.
4. **Severity Classification Engine:** Scores impact and prioritizes alerts based on service tier and disruption.
5. **Remediation Action Layer:** Reverts Git commits (Argocd GitOps) or hits K8s APIs to fix the diagnosed issues.
6. **Safety Guardrails:** A comprehensive suite of limits and verifications that wrap any action. See [Features & Safety](./features_and_safety.md).
