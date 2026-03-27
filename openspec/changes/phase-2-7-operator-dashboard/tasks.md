## DASH-001 — API Endpoints (Critical Path)

- [ ] 1.1 Create `GET /api/v1/incidents` — list active and recent incidents with pagination
- [ ] 1.2 Create `GET /api/v1/incidents/{id}` — incident detail with diagnosis, confidence, evidence
- [ ] 1.3 Create `GET /api/v1/incidents/{id}/timeline` — chronological event timeline
- [ ] 1.4 Create `GET /api/v1/phases/status` — current phase and graduation gate progress
- [ ] 1.5 Create `GET /api/v1/accuracy/summary` — aggregate accuracy metrics by category
- [ ] 1.6 Create `WebSocket /api/ws/incidents` — real-time incident event stream

## DASH-002 — Dashboard Foundation (High)

- [ ] 2.1 Initialize Next.js 15 project in `dashboard/` with TypeScript
- [ ] 2.2 Configure Tailwind CSS with SRE Agent design tokens (colors, spacing, typography)
- [ ] 2.3 Create layout component with sidebar navigation, header with phase indicator, and kill switch status badge
- [ ] 2.4 Implement WebSocket client with auto-reconnect and connection status indicator

## DASH-003 — Incident Feed View (High)

- [ ] 3.1 Create incident list component with real-time updates via WebSocket
- [ ] 3.2 Display per-incident: service name, severity badge, stage indicator, confidence score, elapsed timer
- [ ] 3.3 Implement severity-based filtering and sorting
- [ ] 3.4 Implement incident detail modal/page with full diagnosis and evidence

## DASH-004 — Confidence Visualization (High)

- [ ] 4.1 Create confidence decomposition component (trace correlation, timeline match, RAG similarity, validator agreement)
- [ ] 4.2 Color-code each component (green ≥0.8, yellow 0.5–0.8, red <0.5)
- [ ] 4.3 Create historical confidence trend chart (rolling average over time)

## DASH-005 — Incident Timeline View (Medium)

- [ ] 5.1 Create chronological timeline component with expandable entries
- [ ] 5.2 Display: alert trigger, telemetry queries, RAG documents, hypotheses, remediation actions, post-action metrics
- [ ] 5.3 Link evidence entries to source documents/dashboards

## DASH-006 — Phase and Graduation Tracker (Medium)

- [ ] 6.1 Create phase status component showing current phase with visual indicator
- [ ] 6.2 Create graduation criteria checklist with progress bars (current% / required%)
- [ ] 6.3 Color-code met (green) vs unmet (red) criteria

## DASH-007 — Testing (High)

- [ ] 7.1 Unit tests for all API endpoints (FastAPI TestClient)
- [ ] 7.2 Component tests for React components (React Testing Library)
- [ ] 7.3 E2E browser test: load dashboard, verify incident appears, drill into timeline
