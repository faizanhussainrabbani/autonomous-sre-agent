## ADDED Requirements — Phase 3.2 GCP Support

> **Source:** [Competitively-Driven Roadmap](../../../../docs/project/roadmap_competitive_driven.md) — Item 10
> **Competitive Context:** Datadog, Dynatrace, and Sedai support tri-cloud. GCP gap limits TAM.
> **Extends:** [cloud-portability capability spec](../../autonomous-sre-agent/specs/cloud-portability/spec.md)

### Requirement: GKE Workload Remediation
The system SHALL remediate GKE workloads using the standard Kubernetes API.

#### Scenario: Agent runs on GKE
- **WHEN** the agent is deployed on a GKE cluster
- **THEN** all Kubernetes API interactions SHALL use the standard Kubernetes client API
- **AND** GCP-specific integrations (Workload Identity Federation, Cloud Storage, Secret Manager) SHALL be handled via the GCP cloud adapter

#### Scenario: GKE pod restart
- **GIVEN** an unhealthy deployment on GKE
- **WHEN** remediation engine invokes restart
- **THEN** the GCP adapter SHALL delegate to standard Kubernetes rollout restart
- **AND** the operation SHALL behave identically to self-managed K8s restart

### Requirement: Cloud Functions Remediation
The system SHALL manage Cloud Functions concurrency as a remediation action.

#### Scenario: Cloud Functions concurrency adjustment
- **GIVEN** a Cloud Function exceeds timeout proximity threshold
- **WHEN** remediation suggests concurrency adjustment
- **THEN** the GCP adapter SHALL call the `google.cloud.functions` API to update concurrency settings
- **AND** the action SHALL be recorded in the audit trail with function ARN, old value, new value

#### Scenario: Cloud Functions cold-start suppression
- **GIVEN** a Cloud Function is in cold-start window
- **WHEN** timeout proximity alert fires
- **THEN** the alert SHALL be suppressed per cold-start suppression policy
- **AND** suppression SHALL be logged

### Requirement: Cloud Run Scaling
The system SHALL manage Cloud Run service scaling as a remediation action.

#### Scenario: Cloud Run scale-up
- **GIVEN** a Cloud Run service is experiencing high latency due to insufficient instances
- **WHEN** remediation suggests scaling up
- **THEN** the GCP adapter SHALL call the `google.cloud.run` API to increase max instances
- **AND** the new instance count SHALL not exceed the blast radius limit

### Requirement: GCP Secrets Management
The system SHALL retrieve secrets from Google Secret Manager.

#### Scenario: Secrets from Google Secret Manager
- **WHEN** the cloud provider is configured as `"gcp"`
- **THEN** the system SHALL retrieve secrets via Google Secret Manager
- **AND** authenticate using Workload Identity Federation on GKE

### Requirement: GCP Audit Log Storage
The system SHALL persist audit logs to Cloud Storage.

#### Scenario: Audit log storage on GCP
- **WHEN** the cloud provider is `"gcp"`
- **THEN** audit logs SHALL be written to the configured Cloud Storage bucket
- **AND** encryption SHALL use Google-managed encryption keys (GMEK)

---

## Implementation References

* **Adapters:** `src/sre_agent/adapters/cloud/gcp/`
* **Ports:** `src/sre_agent/ports/cloud_operator.py`, `src/sre_agent/ports/secrets.py`, `src/sre_agent/ports/storage.py`
* **Extends:** `openspec/changes/autonomous-sre-agent/specs/cloud-portability/spec.md`
