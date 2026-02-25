## ADDED Requirements

### Requirement: Real-Time Agent Status View
The system SHALL provide a real-time dashboard showing the autonomous agent's current operational state, active incidents, and pending actions.

#### Scenario: Dashboard displays current rollout phase
- **WHEN** an operator opens the dashboard
- **THEN** the dashboard SHALL display the current operational phase (Observe / Assist / Autonomous / Predictive)
- **AND** show the graduation criteria progress for the next phase with percentage completion

#### Scenario: Active incident overview
- **WHEN** the agent is actively investigating or remediating one or more incidents
- **THEN** the dashboard SHALL display each active incident with: service name, severity, current stage (detecting / diagnosing / remediating / verifying), evidence-weighted confidence score, and elapsed time

#### Scenario: Kill switch status indicator
- **WHEN** the kill switch is activated
- **THEN** the dashboard SHALL prominently display a visual indicator that all agent actions are halted
- **AND** show the timestamp, activator identity, and reason for the kill switch activation

### Requirement: Diagnostic Confidence Visualization
The system SHALL display the evidence breakdown that forms the agent's confidence score for each active and recent incident.

#### Scenario: Confidence breakdown for active incident
- **WHEN** an operator drills into an active incident on the dashboard
- **THEN** the dashboard SHALL display the evidence-weighted confidence score decomposed into: trace correlation strength, timeline match quality, RAG retrieval similarity score, and second-opinion validator agreement
- **AND** each component SHALL be color-coded (green/yellow/red) based on its contribution to overall confidence

#### Scenario: Historical confidence trends
- **WHEN** an operator views the confidence analytics section
- **THEN** the dashboard SHALL display a rolling chart of average confidence scores over time
- **AND** overlay the human override rate to visualize correlation between low confidence and human intervention

### Requirement: Diagnostic Accuracy Dashboard
The system SHALL display aggregate diagnostic accuracy metrics, enabling SRE leadership to evaluate agent trustworthiness over time.

#### Scenario: Overall accuracy rate display
- **WHEN** an operator views the accuracy section
- **THEN** the dashboard SHALL display: total incidents evaluated, correct diagnoses, incorrect diagnoses, and overall accuracy percentage
- **AND** accuracy SHALL be broken down by incident category (OOM, traffic spike, deployment regression, cert expiry, disk exhaustion)

#### Scenario: Agent vs. human comparison view
- **WHEN** the system is in Observe or Assist mode
- **THEN** the dashboard SHALL display a side-by-side comparison of agent diagnoses vs. human decisions for incidents where both are available
- **AND** highlight patterns where the agent consistently agrees or disagrees with human judgment

### Requirement: Incident Timeline View
The system SHALL provide a detailed, navigable timeline for each incident showing the full investigation and remediation sequence.

#### Scenario: Full incident timeline drill-down
- **WHEN** an operator selects a specific incident from the dashboard
- **THEN** the system SHALL display a chronological timeline including: alert trigger, telemetry queries executed, RAG documents retrieved (with similarity scores), hypotheses generated, confidence scores at each step, remediation actions taken, post-action metric changes, and final resolution
- **AND** each timeline entry SHALL be expandable to show full detail

### Requirement: Graduation Gate Progress Tracker
The system SHALL display real-time progress toward the graduation criteria for the next phase transition.

#### Scenario: Progress toward Observe → Assist gate
- **WHEN** the system is in Observe mode
- **THEN** the dashboard SHALL display each graduation criterion with current progress:
  - Diagnostic accuracy: current% / 90% required
  - Incidents evaluated: current count / 100 minimum
  - Destructive false positives: current count (must be 0)
  - KB coverage: verified count / top 20 incident types
- **AND** criteria that are met SHALL be marked green; unmet SHALL be marked red with the gap highlighted
