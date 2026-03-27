## Why

Every commercial AIOps competitor — Datadog, Dynatrace, Sedai, BigPanda — offers a visual dashboard for operators to monitor incidents, review agent decisions, and track operational metrics. The Autonomous SRE Agent currently has no UI. Operators must rely on API calls, log inspection, and Slack notifications to understand agent state. This creates a significant usability gap, particularly for SRE leadership evaluating agent trustworthiness and graduation readiness.

The existing `operator-dashboard` capability spec defines abstract requirements (real-time status, confidence visualization, accuracy metrics, timeline drill-down, graduation tracking). This change delivers the MVP implementation.

## What Changes

- **New React/Next.js dashboard application** (`dashboard/`): Single-page application with real-time incident feed, confidence visualization, and audit log viewer
- **New FastAPI WebSocket endpoint** (`api/ws/incidents`): Real-time incident event stream for dashboard consumption
- **New API endpoints**: GET `/api/v1/incidents`, GET `/api/v1/incidents/{id}/timeline`, GET `/api/v1/phases/status`, GET `/api/v1/accuracy/summary`
- **Updated API Layer**: Additional REST endpoints for dashboard data consumption
- **New Docker Compose service**: Dashboard served alongside API in development environment

## Capabilities

### New Capabilities
- `dashboard-incident-feed`: Real-time incident list with status, severity, confidence, and elapsed time
- `dashboard-confidence-viz`: Evidence-weighted confidence score decomposition with component-level breakdown
- `dashboard-timeline-view`: Chronological incident investigation drill-down
- `dashboard-phase-tracker`: Graduation gate progress visualization

### Modified Capabilities
- `operator-dashboard`: Abstract spec now has concrete MVP implementation
- `api-layer`: Additional REST and WebSocket endpoints for dashboard data
