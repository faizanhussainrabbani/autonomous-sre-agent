## GCP-001 — Cloud Operator Adapter (Critical Path)

- [ ] 1.1 Create `src/sre_agent/adapters/cloud/gcp/__init__.py`
- [ ] 1.2 Create `src/sre_agent/adapters/cloud/gcp/operator.py` implementing `CloudOperatorPort`
- [ ] 1.3 Implement GKE workload restart (delegates to standard K8s API)
- [ ] 1.4 Implement GKE workload scaling (delegates to standard K8s API)
- [ ] 1.5 Implement Cloud Functions concurrency management via `google-cloud-functions` API
- [ ] 1.6 Implement Cloud Run min/max instance scaling via `google-cloud-run` API
- [ ] 1.7 Wrap all GCP API calls with circuit breaker (reuse `resilience.py`)

## GCP-002 — Resource Metadata (Medium)

- [ ] 2.1 Create `src/sre_agent/adapters/cloud/gcp/resource_metadata.py`
- [ ] 2.2 Implement GKE cluster/workload discovery
- [ ] 2.3 Implement Cloud Functions function listing and metadata retrieval
- [ ] 2.4 Implement Cloud Run service listing and metadata retrieval

## GCP-003 — Secrets Adapter (Medium)

- [ ] 3.1 Create `src/sre_agent/adapters/cloud/gcp/secrets.py` implementing `SecretsPort`
- [ ] 3.2 Implement secret retrieval via Google Secret Manager
- [ ] 3.3 Support Workload Identity Federation authentication

## GCP-004 — Storage Adapter (Medium)

- [ ] 4.1 Create `src/sre_agent/adapters/cloud/gcp/storage.py` implementing `ObjectStoragePort`
- [ ] 4.2 Implement audit log write to Cloud Storage bucket
- [ ] 4.3 Implement encryption via Google-managed keys

## GCP-005 — Configuration and Registration (Medium)

- [ ] 5.1 Extend `CloudSettings` with GCP project ID, region, GKE cluster name, bucket name, secret prefix
- [ ] 5.2 Register GCP provider in cloud provider registry (`cloud_provider: "gcp"`)
- [ ] 5.3 Validate GCP credentials and connectivity on startup
- [ ] 5.4 Update Helm chart values.yaml with GCP configuration block

## GCP-006 — Testing (High)

- [ ] 6.1 Unit tests for all GCP adapters with mocked GCP API responses
- [ ] 6.2 E2E tests against GCP emulator (if available) or GCP Test project
- [ ] 6.3 Verify behavioral parity with AWS/Azure adapters for equivalent operations
