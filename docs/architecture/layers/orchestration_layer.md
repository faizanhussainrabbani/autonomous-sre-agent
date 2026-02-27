# Orchestration & Governance Layer

This document details the Orchestration and Governance Layer of the SRE Agent. This layer does not diagnose specific incidents; rather, it governs the overall behavior of the agent, ensuring it adheres to its authorized autonomy level and does not conflict with other automated systems.

```mermaid
graph TD
    classDef input fill:#f9f9f9,stroke:#333,stroke-width:2px;
    classDef state fill:#ffe0b2,stroke:#f57c00,stroke-width:2px;
    classDef lock fill:#e1bee7,stroke:#8e24aa,stroke-width:2px;
    classDef external fill:#eceff1,stroke:#607d8b,stroke-width:2px;

    subgraph Inputs ["Signals & Telemetry"]
        IncMetric[Incident Outcomes & Accuracy Metrics]:::input
        Time[Time & Duration Metrics]:::input
        OtherAgents[External Agent Action Intents]:::input
    end

    subgraph GovernanceLayer ["Orchestration & Governance Layer"]
        
        subgraph PhasedRollout ["Phased Rollout State Machine"]
            PhaseState[Current Phase State Store]:::state
            GateEval[Graduation Gate Evaluator]:::state
            RegressionMon[Safety Regression Monitor]:::state
            
            IncMetric --> GateEval
            Time --> GateEval
            
            GateEval -->|Criteria Met| PhaseState
            RegressionMon -->|Criteria Failed| PhaseState
            
            PhaseState -->|Current Mode: Shadow/Assist/Auto| PolicyConfig[Global Authorization Policy]
        end
        
        subgraph MutiAgentCoord ["Multi-Agent Coordination (Lock Manager)"]
            PriorityEngine[Priority Resolution Engine]:::lock
            MutexDB[(Distributed Lock DB - Redis/etcd)]:::lock
            OscillationDet[Oscillation & Conflict Detector]:::lock
            
            OtherAgents --> PriorityEngine
            PriorityEngine -->|Acquire/Wait/Deny| MutexDB
            
            MutexDB --> OscillationDet
            OscillationDet -->|Conflict Detected| HaltAll[Global Safety Halt]
        end

    end

    subgraph Consumers ["Downstream Core Components"]
        Diag[Intelligence Layer: Severity Classifier]:::external
        Action[Action Layer: Guardrails Engine]:::external
    end

    %% Data Flow
    PolicyConfig -->|Enforce Policy| Diag
    PolicyConfig -->|Enforce Policy| Action
    HaltAll --> Action
    Action -->|Request Lock| PriorityEngine
```
