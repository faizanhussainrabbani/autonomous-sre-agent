## Why

Enterprise Kubernetes adoption requires standardized deployment mechanisms. Helm charts are the de facto standard for deploying applications on Kubernetes. Robusta (our closest open-source competitor) deploys via Helm. Self-hosted deployment differentiates us from SaaS-only competitors (Datadog, Dynatrace, Sedai) and enables adoption in air-gapped, on-prem, and regulated environments.

## What Changes

- **New Helm chart** (`charts/sre-agent/`): Production-quality Helm chart with configurable values for telemetry provider, cloud provider, phase, resource limits, secrets references, and replica management
- **New Kubernetes Operator** (`operator/`): Lifecycle management operator for automated upgrades, backup, and configuration reconciliation
- **Updated Docker multi-stage build**: Optimized for production deployment with minimal attack surface
- **New Artifact Hub metadata** (`charts/sre-agent/artifacthub-repo.yml`): For Helm chart discovery and distribution

## Capabilities

### New Capabilities
- `helm-deployment`: One-command deployment via `helm install sre-agent`
- `k8s-operator`: Lifecycle management for upgrades, backup, and configuration reconciliation

### Modified Capabilities
- `cloud-portability`: Helm chart supports all provider configurations (AWS/Azure/none)

## Impact

- **Dependencies**: Helm 3.x, kubectl, Kubernetes 1.24+
- **Testing**: Helm lint, `helm template` validation, `ct` (Chart Testing), kind/k3d for E2E
