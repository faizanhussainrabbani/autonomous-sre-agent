## Context

The SRE Agent has a Docker multi-stage build and environment variable configuration injection. This change packages the agent as a Helm chart for standard Kubernetes deployment and adds an operator for lifecycle management.

## Goals / Non-Goals

**Goals:**
- Production Helm chart deployable in <5 minutes
- Configurable values.yaml for all runtime settings (telemetry, cloud, phase, resources)
- RBAC templates with least-privilege permissions per phase
- Helm lint and Artifact Hub compliance
- K8s Operator for lifecycle management (upgrades, backup, config reconciliation)

**Non-Goals:**
- Multi-tenant deployment (single agent per cluster)
- Helm chart marketplace (Artifact Hub listing deferred to marketplace item 12)
- Custom Resource Definitions beyond the operator's own

## Decisions

### Decision: Helm 3 (not Helm 2 or Kustomize)
**Rationale:** Helm 3 is the standard. Kustomize is valid but less common for third-party distribution. Helm provides templating, dependency management, rollback, and release lifecycle.

### Decision: values.yaml schema with JSON Schema validation
**Rationale:** JSON Schema enables `helm lint` validation and IDE autocompletion, reducing misconfigurations.

## Risks / Trade-offs

| Risk | Severity | Mitigation |
|---|---|---|
| Helm chart configuration complexity | Medium | Provide sane defaults; document every value; include examples |
| RBAC permissions too broad | High | Phase-specific RBAC templates — Observe has read-only; Autonomous adds write |
| Operator adds deployment complexity | Low | Operator is optional; Helm chart works standalone |
