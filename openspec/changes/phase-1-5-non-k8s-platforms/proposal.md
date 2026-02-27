## Why

Currently, the Autonomous SRE Agent is architecturally coupled to Kubernetes paradigms (e.g., Pods, Namespaces) and relies strictly on kernel-level eBPF telemetry for high-fidelity detection. This prevents adoption for organizations running significant workloads on Serverless (AWS Lambda, Azure Functions) or PaaS/VM targets (AWS ECS, EC2, Azure App Service).

We need a "Phase 1.5" to abstract compute mechanics, decouple from Kubernetes primitives in the canonical data model, gracefully degrade telemetry collection, and implement cloud-provider-specific operational adapters allowing the agent to remediate issues across the entire AWS and Azure compute spectrum.

## What Changes

- **BREAKING:** `ServiceLabels` in the Canonical Data Model will be refactored to remove hard-coded `namespace` and `pod` fields, replacing them with generic `resource_id` and `compute_mechanism` descriptors.
- **eBPF Graceful Degradation:** The Telemetry port and Anomaly Detection engine will add logic to bypass eBPF collection on Serverless/PaaS compute types without failing health checks.
- **Serverless Anomaly Logic:** The Detection engine will introduce "cold-start" suppression and ignore irrelevant heuristics (like OOM events) for serverless compute types.
- **CloudOperator Port:** A new Remediation interface parallel to the K8s API that abstracts `restart_compute_unit` and `scale_capacity`.
- **AWS Operators:** Implementations of `CloudOperatorPort` for boto3-managed ECS, EC2 Auto Scaling Groups, and Lambda.
- **Azure Operators:** Implementations of `CloudOperatorPort` for azure-mgmt-web managed App Services and Functions.

## Capabilities

### New Capabilities
- `serverless-anomaly-detection`: Suppression of cold starts and adaptation of anomaly heuristics for ephemeral compute environments.
- `aws-remediation-adapters`: Boto3-based adapters satisfying `CloudOperatorPort` for ECS, EC2 ASGs, and Lambda limits.
- `azure-remediation-adapters`: Azure SDK-based adapters satisfying `CloudOperatorPort` for App Service and Azure Functions.

### Modified Capabilities
- `telemetry-ingestion`: Support for graceful degradation (incomplete data quality) when eBPF `eBPFQuery` is unavailable on the target compute platform.

## Impact

- **Code:** Massive refactoring of `src/sre_agent/domain/models/canonical.py` impacting all downstream correlation and diagnostic systems.
- **Dependencies:** Requires new Python dependencies for `boto3` and `azure-mgmt-web` in the `pyproject.toml` (likely as optional extras).
- **Testing:** Many existing tests passing literal strings for namespaces and pods to `ServiceLabels` will break and require parameter updates.
