# Phase 1 Improvement Areas

While the **Phase 1: Data Foundation** implementation successfully meets all structural acceptance criteria, the following architectural weaknesses and improvement areas have been identified for future refinement. Addressing these gaps will ensure the Autonomous SRE Agent is production-ready, scalable, and resilient.

## 1. In-Memory State & Scalability Constraints

Currently, the `AlertCorrelationEngine` stores all `_active_incidents` in a simple Python memory list (`_active_incidents: list[CorrelatedIncident]`).

*   **The Problem:** If the SRE Agent pod crashes, is evicted, or restarts, all active correlation state is completely wiped out. Furthermore, because state is strictly local, you **cannot horizontally scale** the agent. Running more than one replica will cause "split-brain" correlation, where different agents handle different alerts independently without global deduplication.
*   **Proposed Fix:** Extract the incident state out of local memory and into a distributed cache or key-value store. While Redis/etcd locking was loosely planned for Phase 4 (Remediation), moving incident state tracking to a robust persistent backend should be prioritized earlier to ensure high availability.

## 2. Tight Kubernetes Coupling

The canonical data model (`ServiceLabels`) and the eBPF adapter (`PixieAdapter`) strictly rely on Kubernetes-specific taxonomy (`pod` and `namespace`).

*   **The Problem:** The agent's core ingestion pipeline will fail if pointed at standard EC2 instances, AWS Lambda functions, Azure App Services, or ECS/Fargate containers because it assumes a K8s topology.
*   **Proposed Fix:** Abstract the underlying compute concepts. The `ServiceLabels` and the ingestion adapters need to be refactored to handle generic compute environments, gracefully processing data without rigid K8s namespace/pod requirements.

## 3. API Reliability & Throttling

In the `PixieAdapter` (and potentially standard OTel/Prometheus queries), we rely on `httpx.AsyncClient` to query cloud APIs for telemetry and kernel events.

*   **The Problem:** There are currently no retry mechanisms (with jitter or exponential backoff) or circuit breakers implemented. If Pixie's API (or New Relic's NerdGraph) throttles our queries or experiences a momentary blip, the ingestion pipeline will drop the signal and fail immediately.
*   **Proposed Fix:** Implement a generalized resilience library (such as `Tenacity`) to wrap all external HTTP and gRPC calls within the provider adapters.

## 4. Telemetry Downgrade Paths

The current `PixieAdapter` assumes eBPF capabilities are ubiquitously available.

*   **The Problem:** If a monitored application is deployed to a node operating an older Linux kernel (pre 5.8) that doesn't support eBPF primitives, the `PixieAdapter` will throw an error and fail to ingest data for those nodes.
*   **Proposed Fix:** The `SignalCorrelator` and the telemetry abstractions need a graceful downgrade path. The adapter should expose an `is_supported()` check. If eBPF kernel features are unavailable on specific nodes, the system should gracefully fall back to relying purely on OTel instrumentation, appropriately tagging the data with `DataQuality.INCOMPLETE` instead of failing outright.

---

*These improvement areas are currently classified as high-priority tech debt, to be addressed either in interim minor releases or integrated into the formal Phase 2 architecture.*
