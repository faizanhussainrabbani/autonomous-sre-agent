**Status:** APPROVED  
**Version:** 2.0.0  
**Last Updated:** 2026-03-26  
**Traces To:** Phase 2 Core — Action Layer  
**Dependencies:** `diagnosis.py`, `cloud_operator.py`, `events.py`, `canonical.py`, `AGENTS.md`

---

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

---

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

---

### Requirement: Post-Remediation Verification
The system SHALL monitor system metrics after executing a remediation action to verify the incident is resolving.

#### Scenario: Successful remediation verification
- **WHEN** a remediation action is executed
- **THEN** the system SHALL monitor the affected service's key metrics (latency, error rate, throughput) for a configurable observation window (default: 5 minutes)
- **AND** if metrics return to within 1σ of baseline the system SHALL mark the incident as resolved
- **AND** a `REMEDIATION_COMPLETED` event SHALL be emitted to the EventStore

#### Scenario: Remediation fails to improve metrics
- **WHEN** a remediation action is executed
- **AND** key metrics do NOT improve or worsen within the observation window
- **THEN** the system SHALL automatically rollback the remediation action
- **AND** a `REMEDIATION_ROLLED_BACK` event SHALL be emitted to the EventStore
- **AND** escalate the incident to a human responder with full context

---

### Requirement: Diagnosis-to-Remediation Strategy Selection
The system SHALL select the appropriate `RemediationStrategy` based on the `Diagnosis` root cause category and `AnomalyType`.

#### Scenario: OOM Kill maps to RESTART strategy
- **WHEN** a `Diagnosis` has `root_cause` containing "OOM" or "out of memory"
- **AND** the `AnomalyType` is `MEMORY_PRESSURE`
- **THEN** the `RemediationPlanner` SHALL select `RemediationStrategy.RESTART`
- **AND** the `RemediationPlan.target_resource` SHALL be the affected pod's `resource_id`

#### Scenario: Traffic spike maps to SCALE_UP strategy
- **WHEN** a `Diagnosis` has `root_cause` indicating traffic saturation
- **AND** the `AnomalyType` is `LATENCY_SPIKE` or `TRAFFIC_ANOMALY`
- **THEN** the `RemediationPlanner` SHALL select `RemediationStrategy.SCALE_UP`
- **AND** the `RemediationPlan` SHALL include `max_replicas` from deployment configuration

#### Scenario: Deployment regression maps to GITOPS_REVERT strategy
- **WHEN** a `Diagnosis` has `root_cause` indicating deployment-induced regression
- **AND** the `AnomalyType` is `DEPLOYMENT_INDUCED`
- **THEN** the `RemediationPlanner` SHALL select `RemediationStrategy.GITOPS_REVERT`
- **AND** the `RemediationPlan` SHALL include the problematic commit SHA

#### Scenario: Certificate expiry maps to CERTIFICATE_ROTATION strategy
- **WHEN** a `Diagnosis` has `root_cause` indicating certificate expiration
- **AND** the `AnomalyType` is `CERTIFICATE_EXPIRY`
- **THEN** the `RemediationPlanner` SHALL select `RemediationStrategy.CERTIFICATE_ROTATION`

#### Scenario: Disk exhaustion maps to LOG_TRUNCATION strategy
- **WHEN** a `Diagnosis` has `root_cause` indicating disk space exhaustion from log growth
- **AND** the `AnomalyType` is `DISK_EXHAUSTION`
- **THEN** the `RemediationPlanner` SHALL select `RemediationStrategy.LOG_TRUNCATION`
- **AND** the `RemediationPlan` SHALL include the target volume mount paths

---

### Requirement: Multi-Cloud Remediation Routing
The system SHALL route remediation actions to the correct `CloudOperatorPort` adapter based on the target resource's `ComputeMechanism` and `provider`.

#### Scenario: Kubernetes pod restart routed to KubernetesOperator
- **WHEN** a `RemediationPlan` targets a resource with `compute_mechanism=KUBERNETES`
- **AND** the strategy is `RESTART`
- **THEN** the `RemediationEngine` SHALL invoke the `KubernetesOperator.restart_compute_unit()`
- **AND** pass the pod's `resource_id` and namespace metadata

#### Scenario: AWS ECS task restart routed to ECSOperator
- **WHEN** a `RemediationPlan` targets a resource with `compute_mechanism=CONTAINER_INSTANCE` and `provider=aws`
- **AND** the strategy is `RESTART`
- **THEN** the `RemediationEngine` SHALL invoke `ECSOperator.restart_compute_unit()`
- **AND** pass the ECS task ARN as `resource_id`

#### Scenario: AWS Lambda throttle routed to LambdaOperator
- **WHEN** a `RemediationPlan` targets a resource with `compute_mechanism=SERVERLESS` and `provider=aws`
- **AND** the strategy is `SCALE_DOWN`
- **THEN** the `RemediationEngine` SHALL invoke `LambdaOperator.scale_capacity()`

#### Scenario: Azure App Service restart routed to AppServiceOperator
- **WHEN** a `RemediationPlan` targets a resource with `compute_mechanism=VIRTUAL_MACHINE` and `provider=azure`
- **AND** the strategy is `RESTART`
- **THEN** the `RemediationEngine` SHALL invoke `AppServiceOperator.restart_compute_unit()`

#### Scenario: Unsupported compute mechanism triggers escalation
- **WHEN** a `RemediationPlan` targets a resource with an unregistered `ComputeMechanism`
- **THEN** the `RemediationEngine` SHALL NOT attempt execution
- **AND** SHALL escalate to a human responder with the unsupported mechanism details

---

### Requirement: Error Handling During Remediation
The system SHALL handle remediation execution failures gracefully without causing additional damage.

#### Scenario: Cloud API timeout during remediation
- **WHEN** a remediation action is invoked
- **AND** the cloud API does not respond within the configured timeout (default: 30s)
- **THEN** the system SHALL retry the action using exponential backoff (max 3 retries)
- **AND** if all retries fail, SHALL mark the action as `FAILED`
- **AND** escalate to a human responder with timeout details

#### Scenario: Circuit breaker prevents remediation during cloud outage
- **WHEN** a remediation action targets a cloud operator whose circuit breaker is OPEN
- **THEN** the system SHALL NOT attempt the action
- **AND** SHALL queue the action for retry when the circuit breaker transitions to HALF_OPEN
- **AND** emit a `REMEDIATION_FAILED` event with `reason="circuit_breaker_open"`

#### Scenario: Partial failure during batched remediation
- **WHEN** a canary remediation batch succeeds
- **AND** a subsequent batch fails mid-execution
- **THEN** the system SHALL halt the remaining batches
- **AND** SHALL NOT rollback the successfully completed batches (unless metrics degrade)
- **AND** escalate with a detailed report of which batches succeeded and which failed

---

### Requirement: Multi-Agent Lock Coordination
The system SHALL acquire distributed locks before executing remediation actions, following the AGENTS.md Multi-Agent Lock Protocol.

#### Scenario: Lock acquisition before remediation execution
- **WHEN** the `RemediationEngine` is ready to execute a plan
- **THEN** it SHALL request a distributed lock with the schema: `agent_id`, `resource_type`, `resource_name`, `namespace`, `compute_mechanism`, `resource_id`, `provider`, `priority_level=2`, `ttl_seconds=180`, `fencing_token`
- **AND** SHALL NOT execute the action until the lock is granted

#### Scenario: Lock preempted by higher-priority agent
- **WHEN** the SRE Agent (priority 2) holds a lock on a resource
- **AND** the SecOps Agent (priority 1) requests a lock on the same resource
- **THEN** the SRE Agent SHALL receive a lock revocation event
- **AND** SHALL immediately abort the in-progress remediation
- **AND** queue the remediation for retry after lock release

#### Scenario: Cooldown key written after remediation
- **WHEN** a remediation action completes (success or rollback)
- **AND** the distributed lock is released
- **THEN** the system SHALL write a cooldown key with format `cooldown:{namespace}:{resource_type}:{resource_name}` for K8s resources
- **OR** `cooldown:{provider}:{compute_mechanism}:{resource_id}` for non-K8s resources
- **AND** the cooldown TTL SHALL be configurable (default: 15 minutes)

---

### Requirement: Severity-Based Routing
The system SHALL route remediation plans based on incident severity, enforcing human-in-the-loop (HITL) for high-severity incidents.

#### Scenario: Sev 3-4 incident proceeds to autonomous remediation
- **WHEN** a `Diagnosis` has severity `SEV3` or `SEV4`
- **AND** the confidence level is `AUTONOMOUS` (≥ 0.85)
- **THEN** the `RemediationEngine` SHALL execute the plan without human approval
- **AND** emit a `REMEDIATION_STARTED` event with `approval_mode="autonomous"`

#### Scenario: Sev 1-2 incident requires human approval
- **WHEN** a `Diagnosis` has severity `SEV1` or `SEV2`
- **THEN** the system SHALL create a remediation proposal
- **AND** send an approval request via the `NotificationPort`
- **AND** SHALL NOT execute the remediation until human approval is received
- **AND** emit a `REMEDIATION_PLANNED` event with `approval_mode="hitl"`

---

### Requirement: Audit Trail
The system SHALL emit domain events for every remediation state transition to maintain a complete, immutable audit trail.

#### Scenario: Full remediation lifecycle emits events
- **WHEN** a remediation action proceeds through its lifecycle (planned → approved → started → completed)
- **THEN** the following events SHALL be emitted to the `EventStore` in sequence:
  1. `REMEDIATION_PLANNED` — with plan details, strategy, target resource
  2. `REMEDIATION_APPROVED` — with approval mode (autonomous or HITL), approver identity
  3. `REMEDIATION_STARTED` — with execution start timestamp, lock fencing token
  4. `REMEDIATION_COMPLETED` — with execution duration, verification result, metrics delta
- **AND** each event SHALL include the `aggregate_id` linking to the parent incident
