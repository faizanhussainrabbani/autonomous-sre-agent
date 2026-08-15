## Context

Phase 2 delivers the Intelligence Layer and notification integrations. Operators need a visual surface to evaluate agent trustworthiness during the Observe → Assist transition. The abstract `operator-dashboard` spec defines five requirement areas: real-time status, confidence visualization, accuracy metrics, timeline drill-down, and graduation tracking.

## Goals / Non-Goals

**Goals:**
- Deliver responsive React/Vite SPA with <200ms page load
- Real-time incident feed via WebSocket (<1s update delay)
- Confidence score decomposition with color-coded component breakdown
- Incident timeline drill-down with expandable entries
- Phase/graduation gate progress tracker
- Mobile-responsive layout

**Non-Goals:**
- User authentication/RBAC (deferred to Phase 3)
- Custom alert configuration UI
- Historical reporting/export
- Multi-tenant support

## Decisions

### Decision: Vite React package in monorepo artifacts
**Rationale:** The repository already uses a pnpm workspace with Vite-based frontend packages. A dedicated `artifacts/operator-dashboard` package keeps production runtime concerns separate from the design sandbox and aligns with existing build and test tooling.

### Decision: WebSocket for real-time updates (not SSE or polling)
**Rationale:** WebSocket provides bidirectional communication needed for future interactive features (kill switch activation from dashboard). SSE is unidirectional and polling wastes bandwidth.

### Decision: Tailwind CSS for dashboard styling
**Rationale:** Dashboard is an internal operations tool, not a public-facing product. Tailwind provides rapid prototyping with consistent design tokens. Trade-off: adds Tailwind dependency.

## Risks / Trade-offs

| Risk | Severity | Mitigation |
|---|---|---|
| WebSocket connection drops on network issues | Medium | Auto-reconnect with exponential backoff; show "disconnected" banner |
| Dashboard becomes stale data source | Medium | Timestamp on all data; "last updated" indicator; forced refresh button |
| Additional Vite package increases workspace maintenance surface | Low | Keep strict package boundaries and run package-scoped CI validation |
