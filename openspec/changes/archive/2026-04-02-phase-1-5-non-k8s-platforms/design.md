## Context

The Autonomous SRE Agent is currently tightly coupled to Kubernetes architectures. While this provided a strong foundation for Phase 1, it alienated users on Serverless (Lambda, Functions) and PaaS/VM (ECS, EC2, App Service) environments. The `ServiceLabels` data model enforces K8s ontology, and the anomaly detection engine treats the absence of eBPF telemetry as a fatal error.

## Goals / Non-Goals

**Goals:**
- Provide a unified, compute-agnostic Canonical Data Model (`ServiceLabels`).
- Abstract proactive remediation into a `CloudOperatorPort` interface compatible with boto3 (AWS) and azure-mgmt-web (Azure).
- Gracefully handle serverless environments without eBPF capabilities.

**Non-Goals:**
- Provisioning or managing the infrastructure itself (e.g., creating new EC2 instances). Re-scaling existing ASGs is allowed.
- Translating proprietary application logs into canonical formats (depends on OTel adoption).
- Modifying Phase 2 (RAG Diagnostic) capabilities.

## Decisions

### 1. Unified Compute Enum over Polymorphic Classes
We will introduce a `ComputeMechanism` enum (`KUBERNETES`, `SERVERLESS`, `VIRTUAL_MACHINE`, `CONTAINER_INSTANCE`) inside `ServiceLabels` rather than creating class hierarchies (`KubernetesServiceLabels`, `ServerlessServiceLabels`). 
*   **Rationale:** Changing a core dataclass into a polymorphic type would break dozens of type signatures in the `AnomalyDetector` and `SignalCorrelator` which expect simple data. A single class with an untyped `platform_metadata` dict is much easier to migrate.

### 2. Graceful eBPF Degradation instead of Dual Pipelines
Instead of creating a separate "low-fidelity detection pipeline," we will adapt the existing `AnomalyDetector` and `SignalCorrelator` to accept `DataQuality.INCOMPLETE` flags when `eBPFQuery` capabilities are missing.
*   **Rationale:** Code duplication is the enemy of maintenance. The agent should run through the exact same logic loops, simply skipping heuristics (like syscall checks) when the data quality indicates eBPF is unavailable.

### 3. Serverless Lifecycle Handling in Anomaly Detector
We will implement "cold start" awareness directly in the Anomaly Detector logic.
*   **Rationale:** Serverless compute scaling drops latency bombs during cold starts. Without logic to suppress alerts during the first `N` seconds/invocations of a serverless application, the agent will fire continuous false positives. 

## Risks / Trade-offs

- **Risk:** Type-safety loss in `ServiceLabels.platform_metadata`. → **Mitigation:** Use Pydantic or TypedDict schemas inside the adapters to validate the metadata dictionary locally before making API calls.
- **Risk:** Silent failures when eBPF is missing unintentionally. → **Mitigation:** The `has_degraded_observability` flag on `CorrelatedSignals` explicitly surfaces this in the UI to prevent silent failures on environments that *should* have eBPF (like K8s).

## Migration Plan
- This is an internal architectural refactor (Phase 1.5). During the next minor release, existing K8s config files will be automatically migrated to set `compute_mechanism = "KUBERNETES"` to maintain backward compatibility for existing users.
