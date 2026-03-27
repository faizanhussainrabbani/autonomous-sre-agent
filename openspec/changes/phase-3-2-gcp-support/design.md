## Context

The `CloudOperatorPort` interface and adapter pattern are established by AWS and Azure adapters. This change follows the same patterns, reducing implementation risk.

## Goals / Non-Goals

**Goals:**
- GKE workload restart and scale via Kubernetes API (same as self-managed K8s)
- Cloud Functions concurrency management via `google.cloud.functions` API
- Cloud Run min/max instance scaling via `google.cloud.run` API
- Google Secret Manager integration
- Cloud Storage for audit log persistence
- Workload Identity Federation authentication (no long-lived keys in GKE)

**Non-Goals:**
- GCP-specific anomaly detection (our engine is provider-agnostic)
- Cloud Monitoring metrics adapter (separate from `phase-2-8-datadog-adapter`)
- Compute Engine VM management (out of scope — focus on containerized/serverless)

## Decisions

### Decision: GKE remediation via standard Kubernetes API (not GKE-specific API)
**Rationale:** GKE is a CNCF-conformant Kubernetes distribution. All K8s remediation (pod restart, deployment scale, rollout restart) works identically to self-managed K8s. GCP-specific API only needed for GKE cluster-level operations.

### Decision: Separate adapter files following AWS/Azure pattern
```
adapters/cloud/gcp/
├── __init__.py
├── operator.py          # CloudOperatorPort (GKE + Functions + Run)
├── resource_metadata.py # Resource discovery
├── secrets.py           # SecretsPort → Secret Manager
└── storage.py           # ObjectStoragePort → Cloud Storage
```

## Risks / Trade-offs

| Risk | Severity | Mitigation |
|---|---|---|
| Cloud Functions API different from Lambda model | Medium | Abstract behind common `ServerlessOperations` interface in `CloudOperatorPort` |
| Cloud Run scaling model different from ECS | Medium | Document mapping: Cloud Run instances ↔ ECS tasks |
| Workload Identity Federation configuration complexity | Low | Provide Terraform module and Helm chart values for setup |
