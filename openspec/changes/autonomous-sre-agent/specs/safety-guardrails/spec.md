**Status:** APPROVED  
**Version:** 2.0.0  
**Last Updated:** 2026-03-26  
**Traces To:** Phase 2 Core — Action Layer (Safety)  
**Dependencies:** `remediation-engine/spec.md`, `AGENTS.md`, `features_and_safety.md`

---

## ADDED Requirements

### Requirement: Evidence-Weighted Confidence Gating
The system SHALL gate autonomous actions behind evidence-weighted confidence scores that evaluate structural evidence quality, not LLM self-reported confidence.

#### Scenario: High-confidence diagnosis proceeds to remediation
- **WHEN** the evidence-weighted confidence score (based on trace correlation, timeline match, and RAG retrieval similarity) exceeds the configured action threshold (≥ 0.85)
- **THEN** the system SHALL proceed with remediation planning and execution
- **AND** the confidence breakdown SHALL be logged with component scores

#### Scenario: Low-confidence diagnosis triggers escalation
- **WHEN** the evidence-weighted confidence score falls below the action threshold (< 0.70)
- **THEN** the system SHALL NOT execute any remediation action
- **AND** the incident SHALL be escalated to a human responder with the diagnosis, evidence, and confidence breakdown

#### Scenario: Mid-confidence diagnosis requires proposal
- **WHEN** the evidence-weighted confidence score is between 0.70 and 0.85
- **THEN** the system SHALL create a remediation proposal
- **AND** the proposal SHALL be sent to a human for approval before execution

---

### Requirement: Blast Radius Limits
The system SHALL enforce hard-coded maximum blast radius limits per action type to prevent fleet-wide damage from incorrect remediations.

#### Scenario: Pod restart within blast radius limit
- **WHEN** a remediation requires restarting pods
- **AND** the affected pods are within the configured maximum percentage of the fleet (default: 20%)
- **THEN** the system SHALL execute the restart

#### Scenario: Pod restart exceeding blast radius limit
- **WHEN** a remediation would affect more pods than the configured maximum percentage
- **THEN** the system SHALL NOT execute the action
- **AND** SHALL escalate to a human responder with the scope assessment
- **AND** the escalation SHALL include the exact pod count, fleet percentage, and configured limit

#### Scenario: Scaling within blast radius limit
- **WHEN** a remediation requires scaling a deployment
- **AND** the new replica count does not exceed 2x current replicas
- **AND** the new replica count does not exceed the namespace quota
- **THEN** the system SHALL execute the scaling action

#### Scenario: Scaling exceeding blast radius limit
- **WHEN** a scale-up remediation would exceed 2x current replicas or namespace quota
- **THEN** the system SHALL NOT execute the action
- **AND** SHALL cap the scaling at the maximum allowed and escalate the remainder

---

### Requirement: Canary Execution
The system SHALL apply remediations to a small subset of resources first, validate success, then expand to the full scope.

#### Scenario: Canary rollout for pod restart
- **WHEN** a pod restart remediation is authorized
- **THEN** the system SHALL first restart a configurable subset (default: 5%) of affected pods
- **AND** validate that the restarted pods reach healthy state within 60 seconds
- **AND** only then proceed to restart the remaining pods in batches

#### Scenario: Canary failure halts rollout
- **WHEN** the canary subset fails to reach healthy state after restart
- **THEN** the system SHALL halt the remediation
- **AND** NOT restart any additional pods
- **AND** escalate to a human responder with canary failure details

#### Scenario: Canary batch sizing for small deployments
- **WHEN** a remediation targets a deployment with fewer than 20 pods
- **THEN** the canary batch size SHALL be exactly 1 pod (minimum)
- **AND** the canary validation window SHALL still apply

#### Scenario: Canary batch sizing formula
- **WHEN** the system calculates canary batch size
- **THEN** the batch size SHALL be `max(1, ceil(total_pods * canary_percentage / 100))`
- **AND** `canary_percentage` defaults to 5% and is configurable per namespace

---

### Requirement: Kill Switch
The system SHALL provide an instant human override mechanism that halts all autonomous agent actions immediately.

#### Scenario: Kill switch activation
- **WHEN** any authorized team member activates the kill switch via API (`POST /api/v1/kill-switch`) or CLI (`sre-agent halt`)
- **THEN** all in-progress remediation actions SHALL be immediately halted
- **AND** all queued remediation plans SHALL be cancelled
- **AND** no new autonomous actions SHALL be initiated until the kill switch is deactivated
- **AND** the activation SHALL be logged with timestamp, activator identity, and reason
- **AND** a `KILL_SWITCH_ACTIVATED` event SHALL be emitted to the EventStore

#### Scenario: Kill switch deactivation
- **WHEN** an authorized team member deactivates the kill switch
- **THEN** autonomous actions SHALL resume
- **AND** previously cancelled plans SHALL NOT be automatically re-queued
- **AND** a `KILL_SWITCH_DEACTIVATED` event SHALL be emitted

---

### Requirement: Knowledge Base Freshness Enforcement
The system SHALL enforce time-to-live (TTL) policies on knowledge base documents and detect stale content.

#### Scenario: Document exceeds TTL
- **WHEN** a runbook or post-mortem in the vector database is older than the configured TTL (default: 90 days)
- **THEN** the system SHALL flag the document for re-validation
- **AND** reduce the weight of this document in confidence scoring by 50% until re-validated

#### Scenario: Automated staleness detection
- **WHEN** a runbook references a service, endpoint, or configuration that no longer exists in the live dependency graph
- **THEN** the system SHALL flag the document as stale
- **AND** alert the knowledge base owner for review

---

### Requirement: Least Privilege Access Control
The system SHALL operate with minimal required permissions, scoped per action type and per target resource.

#### Scenario: Agent attempts action outside its permission scope
- **WHEN** the agent's remediation plan requires an action it is not authorized to perform
- **THEN** the system SHALL deny the action
- **AND** log the denied attempt with the required permission and the agent's current scope
- **AND** escalate to a human responder

---

### Requirement: Input Sanitization
The system SHALL sanitize all incoming telemetry data before feeding it to the LLM to protect against prompt injection attacks.

#### Scenario: Malicious log entry containing prompt injection
- **WHEN** a log entry contains text designed to manipulate LLM reasoning (e.g., "ignore previous instructions and...")
- **THEN** the sanitization layer SHALL strip or neutralize the injection payload
- **AND** the sanitized log SHALL be logged separately for security review

---

### Requirement: Comprehensive Audit Logging
The system SHALL log every agent action, query, decision, and state change with full context for forensic review.

#### Scenario: Full audit trail for resolved incident
- **WHEN** an incident is resolved (by agent or human)
- **THEN** the audit log SHALL contain the complete sequence: alert trigger, queries executed, data retrieved, hypotheses generated, confidence scores, actions taken, post-action metrics, and final resolution
- **AND** the audit log SHALL be immutable and tamper-evident

---

### Requirement: Cooldown Protocol Enforcement
The system SHALL enforce cooldown periods after remediation to prevent oscillation loops, following the AGENTS.md coordination protocol.

#### Scenario: Cooldown prevents re-remediation of Kubernetes resource
- **WHEN** the SRE Agent completes a remediation on a Kubernetes resource
- **AND** writes a cooldown key with format `cooldown:{namespace}:{resource_type}:{resource_name}`
- **AND** a new anomaly is detected on the same resource within the cooldown TTL (default: 15 minutes)
- **THEN** the Lock Manager SHALL deny any new lock requests for that resource
- **AND** the system SHALL log the cooldown denial with remaining TTL

#### Scenario: Cooldown prevents re-remediation of non-Kubernetes resource
- **WHEN** the SRE Agent completes a remediation on a non-K8s resource (e.g., AWS Lambda)
- **AND** writes a cooldown key with format `cooldown:{provider}:{compute_mechanism}:{resource_id}`
  (e.g., `cooldown:aws:SERVERLESS:arn:aws:lambda:us-east-1:123456789:function:payment-handler`)
- **AND** a new anomaly is detected on the same resource within the cooldown TTL
- **THEN** the Lock Manager SHALL deny the lock request

#### Scenario: Higher-priority agent bypasses cooldown
- **WHEN** a cooldown key exists for a resource locked by the SRE Agent (priority 2)
- **AND** the SecOps Agent (priority 1) requests a lock on the same resource
- **THEN** the Lock Manager SHALL grant the lock to the SecOps Agent
- **AND** the cooldown restriction SHALL be waived for the higher-priority agent

---

### Requirement: Phase Gate Graduation Criteria
The system SHALL enforce measurable graduation criteria before transitioning between operational phases.

#### Scenario: Phase 2 (Assist) → Phase 3 (Autonomous) graduation gate
- **WHEN** a phase transition from ASSIST to AUTONOMOUS is requested
- **THEN** the following criteria SHALL be validated:
  1. Diagnostic accuracy ≥ 90% over the trailing 30-day window
  2. Zero agent-caused destructive incidents (false-positive remediations causing damage)
  3. ≥ 95% of Sev 3-4 incidents resolved by autonomous remediation
  4. Integration test coverage for `domain/remediation/` ≥ 30% (engineering standard)
  5. Seven-day soak test completed with zero crashes
- **AND** if ANY criterion fails, the transition SHALL be denied
- **AND** the denial SHALL include the specific failing criteria with current values
