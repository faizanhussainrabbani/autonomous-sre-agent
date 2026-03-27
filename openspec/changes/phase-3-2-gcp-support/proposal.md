## Why

Our agent has partial multi-cloud support today (AWS/Azure adapters and provider abstractions are implemented), but no GCP operator support. Enterprises with GCP-primary infrastructure (GKE, Cloud Functions, Cloud Run) cannot adopt us end-to-end. Datadog, Dynatrace, and Sedai all support tri-cloud. This gap limits our Total Addressable Market.

The existing `cloud-portability` spec and `CloudOperatorPort` interface define the adapter pattern. This change adds GCP as a third cloud provider, following the established AWS/Azure adapter patterns.

## What Changes

- **New GCP cloud operator** (`adapters/cloud/gcp/operator.py`): Implements `CloudOperatorPort` for GKE workload restart/scale, Cloud Functions concurrency, Cloud Run scaling
- **New GCP resource metadata** (`adapters/cloud/gcp/resource_metadata.py`): GCP-specific resource discovery and metadata retrieval
- **New GCP secrets adapter** (`adapters/cloud/gcp/secrets.py`): Google Secret Manager integration via `SecretsPort`
- **New GCP storage adapter** (`adapters/cloud/gcp/storage.py`): Cloud Storage integration via `ObjectStoragePort`
- **Updated configuration**: `CloudSettings` extended with GCP project ID, region, GKE cluster

## Capabilities

### New Capabilities
- `gcp-cloud-operator`: GKE workload remediation, Cloud Functions concurrency management, Cloud Run scaling
- `gcp-secrets`: Google Secret Manager integration
- `gcp-storage`: Cloud Storage for audit logs

### Modified Capabilities
- `cloud-portability`: Extended to tri-cloud (AWS + Azure + GCP)

## Impact

- **Dependencies**: `google-cloud-container`, `google-cloud-functions`, `google-cloud-run`, `google-cloud-secret-manager`, `google-cloud-storage`
- **Authentication**: Google Workload Identity Federation for GKE; Service Account key for non-GKE
