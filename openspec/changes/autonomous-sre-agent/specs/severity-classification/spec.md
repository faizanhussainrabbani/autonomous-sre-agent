## ADDED Requirements

### Requirement: Automated Severity Classification
The system SHALL automatically assign an incident severity level (Sev 1 through Sev 4) based on observable impact dimensions, determining the agent's authorization level for autonomous action.

#### Scenario: Sev 1 — Critical business impact
- **WHEN** an incident meets ANY of the following criteria:
  - Revenue-generating services are fully unavailable to >50% of users
  - Data loss or corruption is detected or imminent
  - Security breach is active
- **THEN** the system SHALL classify the incident as Severity 1
- **AND** the agent SHALL NOT take autonomous action regardless of rollout phase (human-only resolution)

#### Scenario: Sev 2 — Major impact with degradation
- **WHEN** an incident meets ANY of the following criteria:
  - A critical service is significantly degraded (>25% error rate or >3x latency)
  - Multiple non-critical services are simultaneously affected
  - A single service affecting >10,000 users is degraded but not fully down
- **THEN** the system SHALL classify the incident as Severity 2
- **AND** the agent SHALL propose remediation but require human approval before execution (in Assist and Autonomous phases)

#### Scenario: Sev 3 — Moderate impact, isolated
- **WHEN** an incident meets ALL of the following criteria:
  - A single non-critical service is degraded
  - Fewer than 10,000 users are affected
  - No data loss or security risk is present
  - A known, reversible remediation exists in the knowledge base
- **THEN** the system SHALL classify the incident as Severity 3
- **AND** the agent SHALL be authorized for autonomous remediation (in Assist and Autonomous phases, subject to safety guardrails)

#### Scenario: Sev 4 — Low impact, routine
- **WHEN** an incident meets ALL of the following criteria:
  - Impact is limited to a single pod, container, or non-user-facing component
  - No user-visible degradation is detected
  - The remediation is fully idempotent (e.g., pod restart, log rotation)
- **THEN** the system SHALL classify the incident as Severity 4
- **AND** the agent SHALL be authorized for autonomous remediation (in Assist and Autonomous phases)

### Requirement: Service Tier Weighting
The system SHALL incorporate service tier classification into severity determination, ensuring that incidents on business-critical services are escalated higher than equivalent incidents on internal services.

#### Scenario: OOM kill on Tier 1 (revenue-critical) service
- **WHEN** an OOM kill is detected on a service classified as Tier 1 (revenue-critical)
- **THEN** the system SHALL classify the incident as at least Severity 2, regardless of the number of pods affected
- **AND** the tier classification SHALL be sourced from the service catalog or dependency graph annotations

#### Scenario: OOM kill on Tier 3 (internal tooling) service
- **WHEN** an OOM kill is detected on a service classified as Tier 3 (internal tooling)
- **AND** only a single pod is affected
- **THEN** the system SHALL classify the incident as Severity 4
- **AND** the agent SHALL be fully authorized for autonomous pod restart

### Requirement: Severity Override
The system SHALL allow human responders to override the automated severity classification at any time during incident handling.

#### Scenario: Human escalates severity
- **WHEN** a human responder determines that an auto-classified Sev 3 incident is actually Sev 1
- **THEN** the system SHALL immediately reclassify the incident to Severity 1
- **AND** halt any in-progress autonomous remediation
- **AND** log the override with the original classification, new classification, and override reason

#### Scenario: Human downgrades severity
- **WHEN** a human responder determines that an auto-classified Sev 1 incident is actually Sev 3
- **THEN** the system SHALL reclassify the incident to Severity 3
- **AND** the agent SHALL resume handling according to Sev 3 authorization rules

### Requirement: Multi-Dimensional Impact Scoring
The system SHALL compute a composite impact score from multiple dimensions to inform severity classification rather than relying on a single metric.

#### Scenario: Multi-dimensional scoring for ambiguous incident
- **WHEN** an incident does not clearly map to a single severity level
- **THEN** the system SHALL compute a composite score from:
  - User impact (number of affected users, percentage of traffic)
  - Service criticality (tier classification from service catalog)
  - Blast radius (number of services/pods/nodes affected)
  - Financial impact (estimated revenue at risk per minute)
  - Remediation reversibility (is the known fix idempotent?)
- **AND** classify severity based on the composite score according to configurable thresholds

### Requirement: Multi-Dimensional Impact Scoring Formula
The system SHALL utilize a deterministic formula to calculate the composite impact score, normalizing across the 5 dimensions.

#### Scenario: Calculating the final numerical severity
- **WHEN** the system calculates multi-dimensional impact
- **THEN** it SHALL use a weighted sum formula: `Score = (W1 * UserImpact) + (W2 * TierCrit) + (W3 * BlastRadius) + (W4 * FinImpact) - (W5 * Reversibility)`
- **AND** the weights (`W1` through `W5`) SHALL be configurable globally via the agent settings
- **AND** incidents with a `Score > Threshold_Sev1` become Sev 1, `Threshold_Sev2` become Sev 2, etc.

### Requirement: Service Tier Data Sourcing
The system SHALL obtain authoritative service tier classifications from a dedicated, reliable external system of record.

#### Scenario: Resolving service tiers during incident classification
- **WHEN** an incident occurs on a specific service
- **THEN** the system SHALL query external metadata annotations (e.g., Kubernetes `metadata.labels['service-tier']` or an external service catalog like Backstage)
- **AND** if the service tier is missing or unreachable, the system SHALL default to Tier 1 (fail-safe) to avoid inadvertently classifying critical apps as low priority
