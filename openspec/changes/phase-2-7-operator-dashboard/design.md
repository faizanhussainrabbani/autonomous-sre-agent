## Context

Phase 2 delivers the Intelligence Layer and notification integrations. Operators need a visual surface to evaluate agent trustworthiness during the Observe → Assist transition. The abstract `operator-dashboard` spec defines five requirement areas: real-time status, confidence visualization, accuracy metrics, timeline drill-down, and graduation tracking.

## Goals / Non-Goals

**Goals:**
- Deliver responsive React/Next.js SPA with <200ms page load
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

### Decision: Next.js 15 with App Router
**Rationale:** Next.js provides SSR for initial page load performance, API routes for proxying backend calls, and React Server Components for data-heavy views. App Router is the current standard.

### Decision: WebSocket for real-time updates (not SSE or polling)
**Rationale:** WebSocket provides bidirectional communication needed for future interactive features (kill switch activation from dashboard). SSE is unidirectional and polling wastes bandwidth.

### Decision: Tailwind CSS for dashboard styling
**Rationale:** Dashboard is an internal operations tool, not a public-facing product. Tailwind provides rapid prototyping with consistent design tokens. Trade-off: adds Tailwind dependency.

## Risks / Trade-offs

| Risk | Severity | Mitigation |
|---|---|---|
| WebSocket connection drops on network issues | Medium | Auto-reconnect with exponential backoff; show "disconnected" banner |
| Dashboard becomes stale data source | Medium | Timestamp on all data; "last updated" indicator; forced refresh button |
| Next.js adds significant bundle to deployment | Low | Dashboard is a separate deployment unit; does not affect agent binary |
