## ADDED Requirements

### Requirement: Safe Remediation Action Execution
The system SHALL execute targeted remediation actions for well-understood incidents, limited to safe, reversible operations.

#### Scenario: Pod restart for OOM kill
- **WHEN** the diagnosis identifies an OOM-killed pod
- **AND** the evidence-weighted confidence exceeds the threshold
- **THEN** the system SHALL restart the affected pod via Kubernetes API
- **AND** log the action with pod name, namespace, timestamp, and diagnosis reference

#### Scenario: Horizontal scaling for traffic spike
- **WHEN** the diagnosis identifies a traffic surge exceeding current capacity
- **THEN** the system SHALL increase the replica count for the affected deployment
- **AND** the scaling action SHALL NOT exceed the configured maximum replica limit

#### Scenario: Certificate rotation for expiration
- **WHEN** the system detects a certificate approaching expiration (within configured threshold)
- **THEN** the system SHALL trigger certificate renewal via the configured certificate manager
- **AND** verify the new certificate is valid and active before marking the incident resolved

### Requirement: Deployment Rollback via GitOps
The system SHALL perform deployment rollbacks by reverting to a known-good Git commit via ArgoCD, ensuring version-controlled and auditable remediation.

#### Scenario: Rollback for Sev 3-4 incident
- **WHEN** the diagnosis identifies a deployment-induced regression with severity 3 or 4
- **AND** the evidence-weighted confidence exceeds the threshold
- **THEN** the system SHALL create a Git revert commit targeting the problematic deployment
- **AND** ArgoCD SHALL reconcile the cluster to the reverted state
- **AND** no human approval SHALL be required

#### Scenario: Rollback proposal for Sev 1-2 incident
- **WHEN** the diagnosis identifies a deployment-induced regression with severity 1 or 2
- **THEN** the system SHALL create a pull request with the proposed Git revert
- **AND** the pull request SHALL include the full diagnosis, evidence, and impact assessment
- **AND** a human MUST approve the PR before ArgoCD applies the rollback

### Requirement: Post-Remediation Verification
The system SHALL monitor system metrics after executing a remediation action to verify the incident is resolving.

#### Scenario: Successful remediation verification
- **WHEN** a remediation action is executed
- **THEN** the system SHALL monitor the affected service's key metrics (latency, error rate, throughput) for a configurable observation window
- **AND** if metrics return to baseline the system SHALL mark the incident as resolved

#### Scenario: Remediation fails to improve metrics
- **WHEN** a remediation action is executed
- **AND** key metrics do NOT improve or worsen within the observation window
- **THEN** the system SHALL automatically rollback the remediation action
- **AND** escalate the incident to a human responder with full context
