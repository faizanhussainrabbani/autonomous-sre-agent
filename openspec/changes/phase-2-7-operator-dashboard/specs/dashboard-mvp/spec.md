## ADDED Requirements — Phase 2.7 Dashboard MVP

> **Source:** [Competitively-Driven Roadmap](../../../../../docs/project/roadmap_competitive_driven.md) — Item 4
> **Competitive Context:** Datadog, Dynatrace, and Sedai all have polished operational dashboards. This is expected by all operator users.
> **Extends:** [operator-dashboard capability spec](../../../autonomous-sre-agent/specs/operator-dashboard/spec.md)

### Requirement: Dashboard Page Load Performance
The dashboard SHALL load within a strict latency budget to ensure operator productivity.

#### Scenario: Initial page load
- **GIVEN** operator navigates to the dashboard URL
- **WHEN** the page renders
- **THEN** First Contentful Paint SHALL occur within 200ms
- **AND** incident feed SHALL be populated within 500ms of initial load

#### Scenario: Page load with 50+ active incidents
- **GIVEN** 50 incidents are currently active
- **WHEN** the dashboard loads
- **THEN** all incidents SHALL render in the feed within 1 second
- **AND** UI SHALL remain responsive (no frozen frame >100ms)

### Requirement: Real-Time Incident Feed Updates
The dashboard SHALL display new incidents in real-time without manual page refresh.

#### Scenario: New incident appears in feed
- **GIVEN** the dashboard is open and connected via WebSocket
- **WHEN** a new incident is created by the detection engine
- **THEN** the incident SHALL appear in the feed within 1 second
- **AND** a subtle animation SHALL indicate the new entry

#### Scenario: Incident status changes in real-time
- **GIVEN** an incident transitions from "diagnosing" to "remediating"
- **WHEN** the status change event is emitted
- **THEN** the incident card SHALL update its stage indicator within 1 second
- **AND** no page refresh SHALL be required

#### Scenario: WebSocket disconnection recovery
- **GIVEN** the WebSocket connection drops due to network interruption
- **WHEN** connectivity is restored
- **THEN** the dashboard SHALL automatically reconnect within 5 seconds
- **AND** display a "Reconnected" notification
- **AND** fetch and reconcile any missed events

### Requirement: Responsive Layout
The dashboard SHALL be fully functional on desktop and tablet screen sizes.

#### Scenario: Desktop layout
- **GIVEN** a viewport width ≥1024px
- **WHEN** the dashboard renders
- **THEN** sidebar navigation, incident feed, and detail panel SHALL be visible simultaneously

#### Scenario: Tablet layout
- **GIVEN** a viewport width 768–1024px
- **WHEN** the dashboard renders
- **THEN** layout SHALL collapse to single-column with expandable navigation
- **AND** all features SHALL remain accessible

---

## Implementation References

* **API:** `src/sre_agent/api/main.py` (new endpoints), `src/sre_agent/api/ws/incidents.py` (WebSocket)
* **Dashboard:** `dashboard/` (Next.js application)
* **Extends:** `openspec/changes/autonomous-sre-agent/specs/operator-dashboard/spec.md`
