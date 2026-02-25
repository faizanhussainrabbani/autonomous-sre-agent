## ADDED Requirements

### Requirement: Evidence-Weighted Confidence Gating
The system SHALL gate autonomous actions behind evidence-weighted confidence scores that evaluate structural evidence quality, not LLM self-reported confidence.

#### Scenario: High-confidence diagnosis proceeds to remediation
- **WHEN** the evidence-weighted confidence score (based on trace correlation, timeline match, and RAG retrieval similarity) exceeds the configured action threshold
- **THEN** the system SHALL proceed with remediation planning and execution
- **AND** the confidence breakdown SHALL be logged

#### Scenario: Low-confidence diagnosis triggers escalation
- **WHEN** the evidence-weighted confidence score falls below the action threshold
- **THEN** the system SHALL NOT execute any remediation action
- **AND** the incident SHALL be escalated to a human responder with the diagnosis, evidence, and confidence breakdown

### Requirement: Blast Radius Limits
The system SHALL enforce hard-coded maximum blast radius limits per action type to prevent fleet-wide damage from incorrect remediations.

#### Scenario: Pod restart within blast radius limit
- **WHEN** a remediation requires restarting pods
- **AND** the affected pods are within the configured maximum percentage of the fleet (e.g., 20%)
- **THEN** the system SHALL execute the restart

#### Scenario: Pod restart exceeding blast radius limit
- **WHEN** a remediation would affect more pods than the configured maximum percentage
- **THEN** the system SHALL NOT execute the action
- **AND** SHALL escalate to a human responder with the scope assessment

### Requirement: Canary Execution
The system SHALL apply remediations to a small subset of resources first, validate success, then expand to the full scope.

#### Scenario: Canary rollout for pod restart
- **WHEN** a pod restart remediation is authorized
- **THEN** the system SHALL first restart a configurable subset (e.g., 5%) of affected pods
- **AND** validate that the restarted pods reach healthy state
- **AND** only then proceed to restart the remaining pods in batches

#### Scenario: Canary failure halts rollout
- **WHEN** the canary subset fails to reach healthy state after restart
- **THEN** the system SHALL halt the remediation
- **AND** NOT restart any additional pods
- **AND** escalate to a human responder

### Requirement: Kill Switch
The system SHALL provide an instant human override mechanism that halts all autonomous agent actions immediately.

#### Scenario: Kill switch activation
- **WHEN** any authorized team member activates the kill switch
- **THEN** all in-progress and queued agent actions SHALL be immediately halted
- **AND** no new autonomous actions SHALL be initiated until the kill switch is deactivated
- **AND** the activation SHALL be logged with timestamp, activator identity, and reason

### Requirement: Knowledge Base Freshness Enforcement
The system SHALL enforce time-to-live (TTL) policies on knowledge base documents and detect stale content.

#### Scenario: Document exceeds TTL
- **WHEN** a runbook or post-mortem in the vector database is older than the configured TTL (e.g., 90 days)
- **THEN** the system SHALL flag the document for re-validation
- **AND** reduce the weight of this document in confidence scoring until re-validated

#### Scenario: Automated staleness detection
- **WHEN** a runbook references a service, endpoint, or configuration that no longer exists in the live dependency graph
- **THEN** the system SHALL flag the document as stale
- **AND** alert the knowledge base owner for review

### Requirement: Least Privilege Access Control
The system SHALL operate with minimal required permissions, scoped per action type and per target resource.

#### Scenario: Agent attempts action outside its permission scope
- **WHEN** the agent's remediation plan requires an action it is not authorized to perform
- **THEN** the system SHALL deny the action
- **AND** log the denied attempt with the required permission and the agent's current scope
- **AND** escalate to a human responder

### Requirement: Input Sanitization
The system SHALL sanitize all incoming telemetry data before feeding it to the LLM to protect against prompt injection attacks.

#### Scenario: Malicious log entry containing prompt injection
- **WHEN** a log entry contains text designed to manipulate LLM reasoning (e.g., "ignore previous instructions and...")
- **THEN** the sanitization layer SHALL strip or neutralize the injection payload
- **AND** the sanitized log SHALL be logged separately for security review

### Requirement: Comprehensive Audit Logging
The system SHALL log every agent action, query, decision, and state change with full context for forensic review.

#### Scenario: Full audit trail for resolved incident
- **WHEN** an incident is resolved (by agent or human)
- **THEN** the audit log SHALL contain the complete sequence: alert trigger, queries executed, data retrieved, hypotheses generated, confidence scores, actions taken, post-action metrics, and final resolution
- **AND** the audit log SHALL be immutable and tamper-evident
