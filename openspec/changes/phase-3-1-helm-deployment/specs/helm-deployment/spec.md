## ADDED Requirements — Phase 3.1 Helm Deployment

> **Source:** [Competitively-Driven Roadmap](../../../../docs/project/roadmap_competitive_driven.md) — Item 7
> **Competitive Context:** Robusta deploys via Helm. Self-hosted deployment differentiates from SaaS-only competitors.

### Requirement: One-Command Deployment
The system SHALL be deployable on any CNCF-conformant Kubernetes cluster via a single Helm install command.

#### Scenario: Fresh installation
- **GIVEN** a Kubernetes cluster with Helm 3 installed
- **WHEN** operator runs `helm install sre-agent ./charts/sre-agent`
- **THEN** the agent SHALL be deployed and healthy within 5 minutes
- **AND** readiness probe `/healthz` SHALL return 200

#### Scenario: Installation with custom telemetry provider
- **GIVEN** operator sets `telemetryProvider: datadog` in values.yaml
- **WHEN** `helm install` executes
- **THEN** the Datadog telemetry adapter SHALL be configured
- **AND** Prometheus adapter SHALL NOT be loaded

#### Scenario: Installation with custom cloud provider
- **GIVEN** operator sets `cloudProvider: aws` and provides EKS-specific configuration
- **WHEN** `helm install` executes
- **THEN** AWS cloud operator adapter SHALL be configured
- **AND** IRSA service account annotations SHALL be applied

### Requirement: Zero-Downtime Upgrades
Helm upgrades SHALL not cause service interruption.

#### Scenario: Rolling upgrade
- **GIVEN** SRE Agent v1 is running
- **WHEN** operator runs `helm upgrade sre-agent --set image.tag=v2`
- **THEN** new pods SHALL start before old pods terminate (rolling update)
- **AND** no inflight diagnosis or remediation SHALL be interrupted

### Requirement: Phase-Appropriate RBAC
The Helm chart SHALL generate Kubernetes RBAC resources matching the agent's current operational phase.

#### Scenario: Observe phase RBAC
- **GIVEN** `phase: observe` in values.yaml
- **WHEN** chart renders RBAC templates
- **THEN** ClusterRole SHALL grant only read permissions (get, list, watch)
- **AND** no write permissions (create, update, delete, patch) SHALL be included

#### Scenario: Autonomous phase RBAC
- **GIVEN** `phase: autonomous` in values.yaml
- **WHEN** chart renders RBAC templates
- **THEN** ClusterRole SHALL include read AND write permissions for configured namespaces
- **AND** write permissions SHALL be scoped to remediation-relevant resources only (pods, deployments, statefulsets)

### Requirement: Helm Chart Quality
The chart SHALL pass standard tooling validation.

#### Scenario: Helm lint validation
- **WHEN** `helm lint charts/sre-agent/` is run
- **THEN** zero errors and zero warnings SHALL be reported

#### Scenario: Artifact Hub readiness
- **WHEN** chart is evaluated against Artifact Hub criteria
- **THEN** chart SHALL pass all required checks (README, NOTES.txt, icon, maintainers)

---

## Implementation References

* **Chart:** `charts/sre-agent/`
* **Docker:** `Dockerfile` (existing multi-stage build)
