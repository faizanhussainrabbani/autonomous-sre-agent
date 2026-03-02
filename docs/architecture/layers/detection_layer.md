# Detection Layer Architecture

This diagram illustrates how raw telemetry is processed into an actionable Incident by the Detection Layer.

```mermaid
flowchart TD
    %% External Inputs
    Prom[Prometheus/Metrics] --> Windowing[Metric Windowing]
    Loki[Loki/Logs] --> LogParser[Log Parser]
    eBPF[Cilium/eBPF] --> EventStream[System Event Stream]

    subgraph Detection [Detection Layer (Anomaly Engine)]
        Windowing --> FeatureStore[(Temporal Feature Store)]
        
        FeatureStore --> StatBaseline[Statistical Baselining]
        FeatureStore --> MLBaseline[ML Isolation Forests]
        
        LogParser --> ErrorRate[Error Rate Extractor]
        EventStream --> OOMWatch[OOM/Crash Watcher]
        
        StatBaseline --> Correlator{Multi-Dimensional\nCorrelator}
        MLBaseline --> Correlator
        ErrorRate --> Correlator
        OOMWatch --> Correlator
    end

    %% Outputs
    Correlator -- "Confidence > Threshold" --> IncidentGen[Incident Generator]
    IncidentGen -- "Canonical Incident" --> Intelligence[Intelligence Layer / RAG]
    
    %% Styling
    classDef layer fill:#f9f9f9,stroke:#333,stroke-width:2px;
    class Detection layer;
```
