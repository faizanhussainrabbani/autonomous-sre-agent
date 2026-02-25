## ADDED Requirements

### Requirement: Phased Rollout Mode Selection
The system SHALL support four distinct operational modes (Observe, Assist, Autonomous, Predictive) that progressively expand the agent's authority, and only one mode SHALL be active at any time.

#### Scenario: System starts in Observe mode
- **WHEN** the autonomous SRE agent is first deployed
- **THEN** the system SHALL operate in Observe (shadow) mode by default
- **AND** the agent SHALL produce diagnostic recommendations but take NO remediation actions
- **AND** all recommendations SHALL be logged for accuracy comparison against human decisions

#### Scenario: Operator manually selects a mode
- **WHEN** an authorized operator sets the operational mode to Assist
- **THEN** the system SHALL immediately transition to Assist mode
- **AND** all subsequent incidents SHALL be handled according to Assist mode rules
- **AND** the mode change SHALL be logged with timestamp, operator identity, and reason

### Requirement: Shadow Mode Diagnostic Comparison
The system SHALL track diagnostic accuracy during Observe mode by comparing agent recommendations against actual human decisions.

#### Scenario: Agent recommendation matches human decision
- **WHEN** the agent produces a diagnosis and recommended remediation in shadow mode
- **AND** the human responder independently reaches the same diagnosis
- **THEN** the system SHALL record a "match" for that incident category
- **AND** update the rolling diagnostic accuracy metric

#### Scenario: Agent recommendation diverges from human decision
- **WHEN** the agent produces a diagnosis that differs from the human responder's actual diagnosis
- **THEN** the system SHALL record a "mismatch" with both the agent's and human's reasoning
- **AND** the mismatch SHALL be flagged for review to improve future diagnostic accuracy

### Requirement: Severity-Scoped Authorization
The system SHALL restrict which incident severity levels the agent is authorized to handle autonomously, based on the current rollout phase.

#### Scenario: Assist mode limits autonomous action to Sev 3-4
- **WHEN** the system is in Assist mode
- **AND** a severity 3 or 4 incident is detected
- **THEN** the agent SHALL handle the incident autonomously (subject to safety guardrails)

#### Scenario: Assist mode requires human approval for Sev 1-2
- **WHEN** the system is in Assist mode
- **AND** a severity 1 or 2 incident is detected
- **THEN** the agent SHALL propose a remediation but SHALL NOT execute it
- **AND** a human responder MUST approve the proposed action before execution

#### Scenario: Observe mode blocks all autonomous actions
- **WHEN** the system is in Observe mode
- **AND** any incident is detected regardless of severity
- **THEN** the agent SHALL NOT execute any remediation action
- **AND** the agent SHALL only produce diagnostic recommendations for logging

### Requirement: Phase Graduation Gates
The system SHALL enforce measurable, non-negotiable criteria that MUST be satisfied before transitioning from one phase to the next.

#### Scenario: Observe → Assist graduation
- **WHEN** an operator requests transition from Observe to Assist mode
- **THEN** the system SHALL verify all graduation criteria are met:
  - Agent diagnostic accuracy ≥90% vs. human decisions
  - Evaluated over a minimum of 100 incidents
  - Zero false-positive remediations that would have been destructive
  - Knowledge base coverage verified for top 20 incident types
- **AND** if any criterion is NOT met the transition SHALL be blocked with a report of unmet criteria

#### Scenario: Assist → Autonomous graduation
- **WHEN** an operator requests transition from Assist to Autonomous mode
- **THEN** the system SHALL verify:
  - Autonomous Sev 3-4 resolution rate ≥95%
  - Zero blast-radius breaches over a continuous 60-day window
  - Human override rate for Sev 1-2 proposals below 15%
  - No agent-initiated action worsened an incident
- **AND** if any criterion is NOT met the transition SHALL be blocked

#### Scenario: Autonomous → Predictive graduation
- **WHEN** an operator requests transition from Autonomous to Predictive mode
- **THEN** the system SHALL verify:
  - Autonomous resolution rate ≥98% for well-understood incidents
  - Agent-generated runbooks reviewed and approved by SRE team
  - Quarterly agent-disabled chaos day completed successfully
  - No multi-agent conflicts detected (if multiple agents deployed)
- **AND** if any criterion is NOT met the transition SHALL be blocked

### Requirement: Phase Graduation Sign-Off
The system SHALL require explicit sign-off from designated stakeholders before advancing to a new phase.

#### Scenario: Dual sign-off required for phase advancement
- **WHEN** all graduation criteria are met for a phase transition
- **THEN** the system SHALL require sign-off from both engineering leadership AND the on-call SRE team lead
- **AND** the transition SHALL NOT occur until both approvals are recorded
- **AND** the sign-off SHALL be logged with approver identities and timestamps

### Requirement: Phase Regression
The system SHALL support reverting to a lower phase if safety conditions degrade.

#### Scenario: Automatic regression on safety violation
- **WHEN** the system is in Autonomous mode
- **AND** a blast-radius breach or agent-worsened incident occurs
- **THEN** the system SHALL automatically revert to Assist mode
- **AND** alert engineering leadership and the on-call SRE team with full incident context
- **AND** the agent SHALL NOT return to Autonomous mode without re-satisfying graduation criteria
