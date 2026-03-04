# Operator (Presentation & Interface) Layer

**Status:** DRAFT
**Version:** 1.0.0

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


---

## Detailed Architecture

# Operator Layer: Detailed Breakdown

**Status:** DRAFT
**Version:** 1.0.0

This document provides a comprehensive breakdown of the **Operator (Presentation & Interface) Layer** of the SRE Agent. This layer exists to bridge the gap between autonomous ML/LLM decisions and the human engineering teams who ultimately own system health.

## 1. Core Features

The primary mandate of the Operator Layer is **Transparency**. The "black-box" nature of AI is detrimental in Site Reliability Engineering; humans must understand *why* the agent did what it did.

### 1.1 Custom Operator Dashboard (Real-Time UI)
*   **Confidence Visibility:** Breaks down the LLM's confidence score showing structural evidence (e.g., "92% confident because: trace correlates, historical post-mortem matched with 0.88 similarity, latency delta is +400ms").
*   **Incident Drill-Down:** Provides a specialized view of an active incident aggregating metrics, retrieved runbooks, generated hypotheses, and the pending/executed GitOps action in a single pane of glass.
*   **Graduation Gate Tracking:** A specialized view for leadership to monitor phase progression (e.g., tracking "100 consecutive incidents without a false positive" to graduate from Shadow to Assist mode).

### 1.2 Interactive ChatOps (Human-In-The-Loop)
*   **Approval Gates:** For Sev 1-2 incidents, the agent pauses processing, summarizes the diagnosis in Slack via Block Kit, and awaits an `Approve`, `Reject`, or `Extend Validation` button click from an on-call engineer.
*   **Resolution Summaries:** Once an autonomous action succeeds, a concise, human-readable summary of the root cause and the applied fix is published to a specific channel.

### 1.3 Asynchronous Escalation & Ticketing
*   **Hard Escalation:** Bypassing chat for severe incidents or when the agent lacks confidence. PagerDuty is triggered immediately.
*   **Automated Ticketing:** Creating Jira tickets post-remediation that contain the full diagnostic reasoning, enabling "Blameless Post-Mortems for AI."

---

## 2. External Libraries & Dependencies

### 2.1 The Dashboard Frontend

| Dependency | Component Type | Purpose in the SRE Agent |
| :--- | :--- | :--- |
| **Next.js (React)** | Frontend Framework | Provides the structure for the real-time custom dashboard. Selected for strong server-side rendering and API route integration. |
| **Tailwind CSS** | Styling Framework | Used for rapid, standardized UI component construction. |
| **D3.js / Recharts** | Visualization Libraries | Used to render topological service maps and timeline graphs directly in the dashboard, translating the agent's internal Dependency Graph into a human-readable visual. |
| **Server-Sent Events (SSE)** | Web Protocol | Used to stream live updates (metrics changing, agent transitioning from 'diagnosing' to 'remediating') directly to the browser without polling. |

### 2.2 ChatOps & External Integrations

| Dependency | Component Type | Purpose in the SRE Agent |
| :--- | :--- | :--- |
| **Slack Bolt SDK (Python)** | Chat Integration | A robust framework for building interactive Slack apps. Used to generate the rich Block Kit UI and handle the asynchronous webhook callbacks when a user clicks "Approve." |
| **PagerDuty API** | Alert Routing | The primary integration for waking humans up. The agent formats its diagnosis into the specific PagerDuty Incident schema before triggering. |
| **Jira API / Atlassian SDK** | Ticketing Integration | Creates issues, transitions statuses, and uploads the agent's generated runbooks as attachments. |
