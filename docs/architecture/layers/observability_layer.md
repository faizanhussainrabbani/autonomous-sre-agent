# Observability Layer Architecture

This document details the first layer of the SRE Agent architecture: The Observability Layer. Its primary responsibility is gathering high-fidelity telemetry across the entire stack, correlating it, and constructing the service dependency graph before passing the data to the Intelligence Layer.

```mermaid
graph TD
    classDef external fill:#f9f9f9,stroke:#333,stroke-width:2px;
    classDef processing fill:#e1f5fe,stroke:#03a9f4,stroke-width:2px;
    classDef storage fill:#fff3e0,stroke:#ff9800,stroke-width:2px;

    subgraph Target System ["Target Infrastructure / Application Stack"]
        App[Application Services]
        Mesh[Service Mesh / Proxies]
        Kernel[Linux Kernel]
    end

    subgraph Observability ["Observability Layer"]
        subgraph Collection ["Data Collection"]
            OTelSDK[OpenTelemetry SDKs]:::external
            eBPF[eBPF Probes & Programs]:::processing
            
            OTelCol[OpenTelemetry Collector]:::processing
            
            App -->|Metrics/Logs/Traces| OTelSDK
            OTelSDK --> OTelCol
            
            Kernel -->|Syscalls/Network Flows| eBPF
            Mesh -->|L7 Traffic| eBPF
        end

        subgraph Correlation ["Signal Processing"]
            SignalCorr[Signal Correlation Service]:::processing
            DepGraphBuilder[Dependency Graph Builder]:::processing
            
            OTelCol -->|Normalized Telemetry| SignalCorr
            eBPF -->|Kernel/Network Telemetry| SignalCorr
            
            SignalCorr -->|Join by TraceID/Time| EnrichedStream[Enriched Telemetry Stream]
            SignalCorr --> DepGraphBuilder
        end

        subgraph Storage ["Observability Backends (Provider Abstraction)"]
            Prometheus[(Metrics Store)]:::storage
            Jaeger[(Trace Store)]:::storage
            Loki[(Log Store)]:::storage
            GraphDB[(Service Topology)]:::storage
            
            OTelCol --> Prometheus
            OTelCol --> Jaeger
            OTelCol --> Loki
            DepGraphBuilder --> GraphDB
        end
    end

    %% Outgoing to Intelligence Layer
    EnrichedStream -->|Streaming Data| Ingest[Intelligence Layer: Ingestion Pipeline]
    GraphDB -->|Topology Queries| Ingest
```

## Component Details

1. **OpenTelemetry Collection:** Handles application-layer metrics, structured logs, and distributed traces. 
2. **eBPF Programs:** Adds deep kernel-level visibility (network flows, process behavior, syscalls) without requiring sidecar proxies or code changes, operating at a ~1-2% CPU overhead.
3. **Signal Correlation Service:** The critical junction where application traces and kernel spans are joined by TraceID and time windows, creating a unified view of the system.
4. **Dependency Graph Builder:** Continuously analyzes trace spans to map out the real-time service topology, which is essential for determining blast radius and alert correlation later in the pipeline.
