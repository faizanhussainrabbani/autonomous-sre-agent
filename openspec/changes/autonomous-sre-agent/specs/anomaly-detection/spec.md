## ADDED Requirements

### Requirement: Time-Series Anomaly Detection
The system SHALL apply ML-based anomaly detection on streaming time-series metrics to identify infrastructure anomalies without relying on static thresholds.

#### Scenario: Latency spike detection
- **WHEN** p99 latency for a service exceeds 3 standard deviations from its rolling baseline for more than 2 minutes
- **THEN** the system SHALL generate an anomaly alert with severity, affected service, and anomaly magnitude
- **AND** the alert SHALL be generated within 60 seconds of the anomaly onset

#### Scenario: Error rate surge detection
- **WHEN** the error rate for a service increases by more than 200% from its rolling baseline
- **THEN** the system SHALL generate an anomaly alert
- **AND** the alert SHALL distinguish between client errors (4xx) and server errors (5xx)

#### Scenario: Absence of false positive alert storms
- **WHEN** a planned deployment causes a brief metric perturbation lasting less than 30 seconds
- **THEN** the system SHOULD suppress the alert and NOT trigger an investigation
- **AND** the suppression SHALL be logged with reasoning for audit purposes

### Requirement: Configurable Sensitivity
The system SHALL allow operators to configure anomaly detection sensitivity per service and per metric type.

#### Scenario: Sensitivity adjustment for high-traffic service
- **WHEN** an operator sets anomaly sensitivity to "low" for the payments service
- **THEN** the system SHALL require a larger deviation from baseline before alerting on that service
- **AND** the configuration change SHALL take effect within 5 minutes

### Requirement: Alert Noise Reduction
The system SHALL correlate related anomaly alerts into a single incident to prevent alert storms.

#### Scenario: Multiple services affected by the same root cause
- **WHEN** anomalies are detected on services A, B, and C within a 5-minute window
- **AND** the service dependency graph shows A depends on B which depends on C
- **THEN** the system SHALL correlate these into a single incident rooted at service C
- **AND** individual alerts SHALL reference the correlated incident ID

### Requirement: Proactive Resource Exhaustion Detection
The system SHALL detect approaching resource exhaustion (memory, disk, certificates) before failure occurs, enabling preemptive remediation.

#### Scenario: Memory pressure detection before OOM kill
- **WHEN** a pod's memory usage exceeds 85% of its configured limit for more than 5 minutes
- **AND** the memory usage trend is increasing
- **THEN** the system SHALL generate a proactive anomaly alert with severity based on service tier
- **AND** the alert SHALL include the projected time-to-OOM based on the current consumption trend

#### Scenario: Disk space exhaustion detection
- **WHEN** a volume's used disk space exceeds 80% capacity
- **OR** the consumption rate projects full capacity within 24 hours
- **THEN** the system SHALL generate an anomaly alert
- **AND** the alert SHALL include current usage, growth rate, and projected time-to-full

#### Scenario: Certificate expiration detection
- **WHEN** a TLS certificate is within 14 days of expiration
- **THEN** the system SHALL generate a proactive alert
- **AND** if the certificate is within 3 days of expiration the severity SHALL be escalated

### Requirement: Multi-Dimensional Anomaly Correlation
The system SHALL detect anomalies that only manifest when multiple metrics shift simultaneously, even if no single metric exceeds its individual anomaly threshold.

#### Scenario: Combined latency and error rate anomaly
- **WHEN** p99 latency increases by 50% (below individual anomaly threshold)
- **AND** error rate increases by 80% (below individual anomaly threshold)
- **AND** both shifts occur on the same service within a 5-minute window
- **THEN** the system SHALL generate a correlated anomaly alert
- **AND** the alert SHALL note that individual metrics were within normal bounds but the combination is anomalous

### Requirement: Deployment-Aware Anomaly Detection
The system SHALL correlate detected anomalies with recent deployments to identify deployment-induced regressions.

#### Scenario: Anomaly within deployment blast radius
- **WHEN** an anomaly is detected on a service within 60 minutes of a deployment to that service or its direct dependencies
- **THEN** the system SHALL flag the anomaly as "potentially deployment-induced"
- **AND** include the deployment details (commit SHA, deployer, changed services) in the alert context

#### Scenario: Anomaly on unrelated service during deployment window
- **WHEN** an anomaly is detected on a service that has NO dependency relationship with a recently deployed service
- **THEN** the system SHALL NOT flag it as deployment-induced
- **AND** the incident SHALL be investigated independently
