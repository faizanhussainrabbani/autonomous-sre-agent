# Intelligence Layer Architecture

This document details the "brain" of the SRE Agent: The Intelligence Layer. This layer is responsible for ingesting enriched telemetry, detecting anomalies via ML baselines, diagnosing root causes using an LLM and Retrieval-Augmented Generation (RAG), and classifying incident severity.

```mermaid
graph TD
    classDef input fill:#f9f9f9,stroke:#333,stroke-width:2px;
    classDef ml fill:#e8f5e9,stroke:#4caf50,stroke-width:2px;
    classDef llm fill:#ce93d8,stroke:#9c27b0,stroke-width:2px;
    classDef storage fill:#fff3e0,stroke:#ff9800,stroke-width:2px;

    subgraph Incoming ["From Observability Layer"]
        Stream[Enriched Telemetry Stream]:::input
        Topology[Service Topology DB]:::input
    end

    subgraph Intelligence ["Intelligence Layer (SRE Agent Core)"]
        
        subgraph Detection ["Anomaly Detection Engine"]
            Baseline[Rolling Baseline ML Models]:::ml
            Detector[Multi-Dimensional Anomaly Detector]:::ml
            AlertCorr[Alert Correlation Engine]:::ml
            
            Stream --> Baseline
            Baseline --> Detector
            Stream --> Detector
            Detector -->|Raw Anomalies| AlertCorr
            Topology -->|Context| AlertCorr
            AlertCorr -->|Correlated Alert / Incident Threshold| Trigger[Incident Trigger]
        end

        subgraph Diagnostics ["RAG Diagnostic Pipeline"]
            VectorSearch[Vector Database Search]:::storage
            KB[(Historical Incidents / Runbooks)]:::storage
            PromptGen[Contextual Prompt Generator]:::llm
            Reasoning[LLM Reasoning Engine]:::llm
            Validator[Second-Opinion Validator]:::ml
            
            Trigger -->|Embedding Query| VectorSearch
            KB <--> VectorSearch
            VectorSearch -->|Top-K Matches| PromptGen
            Trigger -->|Context| PromptGen
            Topology -->|Context| PromptGen
            
            PromptGen --> Reasoning
            Reasoning -->|Hypothesis + Initial Confidence| Validator
            Validator -->|Confidence Score Adjustment| Diagnosis[Final Diagnosis & Recommendation]
        end

        subgraph Classification ["Severity Classification"]
            ImpactScorer[Impact Scorer]:::ml
            TierLookup[Service Tier Lookup]:::storage
            
            Diagnosis --> ImpactScorer
            Topology --> ImpactScorer
            TierLookup --> ImpactScorer
            ImpactScorer -->|Classified Incident Sev 1-4| OutputDecision[Action Policy Router]
        end
    end

    %% Outgoing to Action Layer
    OutputDecision -->|Payload: Diagnosis + Sev + Recommendation| ActionRouter[Action Layer: Guardrails]
```

## Component Details

1. **Anomaly Detection Engine:** Replaces static thresholds. It computes rolling baselines for metrics and flags multi-dimensional anomalies (e.g., latency spikes combined with error surges). The Alert Correlation Engine groups related anomalies using the Dependency Graph to prevent alert storms.
2. **RAG Diagnostic Pipeline:** Uses semantic search against a Vector DB containing past post-mortems and runbooks to ground the LLM's reasoning. A second-opinion validator acts as a check against LLM hallucination, adjusting the confidence score based on concrete evidence.
3. **Severity Classification:** Determines the business impact using service tiers and blast radius, categorizing the incident from Sev 1 (Critical, Human Only) to Sev 4 (Minor, Fully Autonomous).
