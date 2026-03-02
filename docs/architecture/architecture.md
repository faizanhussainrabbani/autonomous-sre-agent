# System Architecture Overview

The SRE Agent is designed as a sophisticated, layered processing pipeline that translates raw infrastructure telemetry into actionable incidents, autonomous diagnoses, and safe remediation.

## High-Level System Architecture and Data Flow

The agent operates across five primary layers:
1. **Observability Layer:** Collection, forwarding, and storage of raw signals (OTel Collector, Prometheus, Loki).
2. **Detection Layer:** Baselining, anomaly scoring, and multi-dimensional metric correlation.
3. **Intelligence Layer (SRE Agent Core):** RAG reasoning, confidence scoring, and severity classification.
4. **Action Layer:** Safety gating and remediation execution.
5. **Target Infrastructure:** The environment being managed.

```mermaid
graph TD
    subgraph Observability ["Observability Layer"]
        OTel[OpenTelemetry Collector]
        Prom[Prometheus / Loki]
        eBPF[eBPF Programs]
    end

    subgraph Detection ["Detection Layer"]
        Ingest[Telemetry Ingestion & Windowing]
        Detect[ML Anomaly Detection]
        Correlate[Multi-Dimensional Correlation]
    end

    subgraph Intelligence ["Intelligence Layer (Core)"]
        Diag[RAG Diagnostic Pipeline]
        Severity[Severity Classification]
    end

    subgraph Actions ["Action Layer"]
        Guardrails[Safety Guardrails]
        Remediation[Remediation Engine]
    end

    subgraph Target ["Target Infrastructure"]
        K8s[Kubernetes API]
        GitOps[ArgoCD / GitOps]
    end

    %% Flow
    OTel -->|Metrics/Traces/Logs| Prom
    eBPF -->|Kernel/Network| Prom
    Prom --> Ingest
    Ingest --> Detect
    Detect -->|Anomalies| Correlate
    Correlate -->|Correlated Alert / Incident| Diag
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

1. **Telemetry Collection (Observability):** Gathers metrics, logs, traces (via OTel), and eBPF kernel telemetry.
2. **Anomaly Detection Engine (Detection):** ML-based baselining of metrics (no static thresholds). Combines multi-dimensional metrics to identify complex issues.
3. **RAG Diagnostic Pipeline (Intelligence):** Embeds the anomaly context and uses a Vector DB to search past incident histories. Feeds this data to an LLM Reasoning Engine to deduce root causes.
4. **Severity Classification Engine (Intelligence):** Scores impact and prioritizes alerts based on service tier and disruption.
5. **Remediation Action Engine (Action):** Reverts Git commits (Argocd GitOps) or hits K8s APIs to fix the diagnosed issues.
6. **Safety Guardrails (Action):** A comprehensive suite of limits and verifications that wrap any action. See [Features & Safety](./features_and_safety.md).
