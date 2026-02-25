## ADDED Requirements

### Requirement: Resolved Incident Indexing
The system SHALL automatically index resolved incidents into the RAG knowledge base, enriching future diagnostic accuracy.

#### Scenario: Successful incident resolution triggers indexing
- **WHEN** an incident is resolved (by agent or human)
- **THEN** the system SHALL create a structured incident record containing: root cause, symptoms, telemetry patterns, remediation actions taken, time to resolution, and outcome
- **AND** the record SHALL be embedded as a vector and indexed in the vector database within 15 minutes of resolution

#### Scenario: Human-resolved incident includes feedback
- **WHEN** a human responder resolves an incident that the agent escalated
- **THEN** the system SHALL prompt the human for root cause and remediation details
- **AND** this feedback SHALL be indexed to improve future agent diagnostic capability for similar incidents

### Requirement: Smart Runbook Generation
The system SHALL generate runbook drafts from patterns observed across multiple resolved incidents of the same type.

#### Scenario: Pattern-based runbook generation
- **WHEN** the system detects that 3 or more incidents with similar root causes have been resolved using the same remediation steps
- **THEN** the system SHALL generate a draft runbook documenting the diagnostic steps and remediation procedure
- **AND** the draft SHALL be flagged for human review before entering the production knowledge base

#### Scenario: Runbook human review gate
- **WHEN** an agent-generated runbook draft is created
- **THEN** the system SHALL NOT add it to the production knowledge base until a human reviewer approves it
- **AND** the reviewer SHALL be notified via the configured notification channel

### Requirement: Diagnostic Accuracy Tracking
The system SHALL track diagnostic accuracy metrics over time, measuring how often agent diagnoses match actual root causes.

#### Scenario: Correct diagnosis tracking
- **WHEN** an agent-resolved incident's post-mortem confirms the agent's diagnosis was correct
- **THEN** the system SHALL increment the correct diagnosis counter for that incident category
- **AND** the overall diagnostic accuracy rate SHALL be computed and visible on the operational dashboard

#### Scenario: Incorrect diagnosis tracking
- **WHEN** a human responder overrides the agent's diagnosis during resolution
- **THEN** the system SHALL record the override with the agent's original diagnosis and the human's corrected diagnosis
- **AND** the correction SHALL be used as training signal to improve future retrieval relevance

### Requirement: Mandatory Human Incident Routing
The system SHALL randomly route a configurable minimum percentage (default 20%) of agent-capable incidents to human responders to prevent skill atrophy.

#### Scenario: Random routing to human for skill retention
- **WHEN** an incident is classified as within the agent's autonomous capability
- **AND** the random routing selector determines this incident falls within the human routing quota
- **THEN** the system SHALL route the incident to the on-call human responder
- **AND** the agent SHALL observe in shadow mode and record its own diagnosis for comparison

#### Scenario: On-call manual handling quota
- **WHEN** an SRE is on their on-call shift
- **THEN** the system SHALL ensure the SRE manually handles at least 2 agent-capable incidents during the shift regardless of random routing
