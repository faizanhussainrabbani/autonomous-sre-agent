# Dependency Graph Architecture

**Status:** DRAFT
**Version:** 1.0.0

The Dependency Graph is a critical component of the SRE Agent's Intelligence Layer. It provides the topological context necessary to evaluate the "Blast Radius" of a proposed remediation action.

## 1. Graph Construction

The SRE Agent does not rely on static, manually maintained CMDBs (Configuration Management Databases) which are notoriously prone to drift. Instead, the graph is built via **Continuous Auto-Discovery**.

*   **Primary Source:** OpenTelemetry (OTel) distributed traces. By analyzing parent-child span relationships and `net.peer.name` attributes over a rolling 24-hour window, the agent infers actual runtime dependencies.
*   **Secondary Source:** Kubernetes API (`OwnerReferences`). Maps Pods -> ReplicaSets -> Deployments -> Namespaces. Provides the structural hierarchy of the compute layer.
*   **Tertiary Source:** Istio/Cilium eBPF network flows (optional, for environments lacking full OTel instrumentation).

## 2. Storage Format

*   **In-Memory Representation:** The agent processes the graph using a Canonical `ServiceGraph` Pydantic model (`domain/models/canonical.py`) composed of `ServiceDependency` directional edges. Microservices can have cycles (A -> B -> C -> A), and cycle detection is a valid signal for blast radius evaluation.
*   **[PLANNED] Persistent Storage:** The graph is periodically serialized to a PostgreSQL Metadata Store as an adjacency list JSON blob.
*   **[PLANNED] Visual Representation:** Exported to the Operator Layer Dashboard and rendered via `D3.js` or `Recharts`.

## 3. Update Cadence & Staleness Detection

Because microservice architectures are highly dynamic, the graph must remain evergreen.

*   **Continuous Batching:** The `GraphBuilder` background worker polls the Observability Layer (e.g., Jaeger/Tempo) every 15 minutes.
*   **Staleness Triggers:** If an edge (dependency) has not been observed in any trace for >7 days, it is marked as "stale." After 14 days, it is pruned.
*   **Event-Driven Updates:** A Kubernetes `Deployment` creation/deletion event webhook instantly invalidates the cache for that specific namespace subgraph.

### 3.1 Cold-Start / Bootstrap Strategy
On the first deployment of the SRE Agent when no historical trace data exists, the agent operates in a "Cold-Start" mode:
*   The agent relies exclusively on the Secondary Source (Kubernetes `OwnerReferences` and Service mappings) to infer the initial baseline graph.
*   The agent refuses to execute any autonomous actions for the first 24 hours, remaining strictly in Phase 1 (Data Foundation) / Shadow Mode until sufficient OTel tracing telemetry populates the edges.

### 3.2 Graph Snapshotting & Auditing
For compliance and audit purposes ("What did the graph look like when decision X was made?"):
*   A versioned snapshot of the dependency sub-graph is appended to the `Diagnosis` entity precisely when the agent generates its root cause hypothesis.
*   **[PLANNED]** These snapshots are stored immutably in the PostgreSQL/Metadata Store alongside the `AuditEntry`.

## 4. Blast Radius Evaluation

When the agent proposes a `RemediationAction` (e.g., "Restart the `auth-service` deployment"):

1.  It queries the internal Directed Graph for all upstream nodes dependent on `auth-service`.
2.  It calculates the aggregate Tier level of those dependents.
3.  If a Tier-1 service (e.g., "Payment Gateway") depends on the target, the agent enforces a stricter confidence threshold or immediately escalates to a human, overriding standard Phase 3 autonomy.
