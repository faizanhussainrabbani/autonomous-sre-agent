# Operator (Presentation & Interface) Layer

This document details the interface layer where human engineers interact with the SRE Agent. It's designed to provide transparency, facilitate human-in-the-loop approvals, and offer high-level operational metrics.

```mermaid
graph TD
    classDef external fill:#eceff1,stroke:#607d8b,stroke-width:2px;
    classDef ui fill:#e8eaf6,stroke:#3f51b5,stroke-width:2px;
    classDef api fill:#fdf1v6,stroke:#ffb300,stroke-width:2px;
    
    subgraph Core ["SRE Agent Core"]
        AlertBus[Incident Event Bus]:::api
        ApprovalWebhooks[Approval Webhook Receiver]:::api
        MetricsProxy[System Metrics Exporter]:::api
    end

    subgraph OperatorLayer ["Operator / Interface Layer"]
        
        subgraph RealTimeDash ["Custom Operator Dashboard (React/Next.js)"]
            StatusPanel[Real-Time Agent Status]:::ui
            ConfViz[Confidence Score Visualization]:::ui
            Timeline[Incident Timeline Drill-Down]:::ui
            PhaseTracker[Graduation Gate Tracker]:::ui
        end
        
        subgraph ChatOps ["ChatOps Integration (Slack/Teams)"]
            ChatNotifier[Incident Summary Bot]:::ui
            InteractiveBlock[Approval / Reject Buttons]:::ui
        end
        
        subgraph Ticketing ["Incident Management (PagerDuty/Jira)"]
            PagerDuty[Escalation Paging]:::external
            Jira[Post-Mortem Auto-Ticketing]:::external
        end
    end
    
    subgraph Human ["Human Responders"]
        SRE[On-Call SRE Engineer]:::external
        Manager[Engineering Leadership]:::external
    end

    %% Data Flow
    MetricsProxy --> RealTimeDash
    AlertBus --> ChatOps
    AlertBus --> Ticketing
    
    %% Dashboard Flows
    StatusPanel --> SRE
    ConfViz --> SRE
    Timeline --> SRE
    PhaseTracker --> Manager
    
    %% Interactive Flow
    ChatNotifier --> SRE
    InteractiveBlock -->|Action Required (Sev 1-2)| SRE
    SRE -->|Click 'Approve' or 'Reject'| InteractiveBlock
    InteractiveBlock -->|Payload| ApprovalWebhooks
    
    %% External Ticketing
    PagerDuty -->|Novel/Critical Alert| SRE
    Jira -->|Root Cause Documentation| SRE

```
