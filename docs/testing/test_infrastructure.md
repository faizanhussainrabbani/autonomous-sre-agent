# Test Infrastructure & Chaos Injection

**Status:** DRAFT
**Version:** 1.0.0

This document explains the tools and setups required to run the integration and E2E test suites for the SRE Agent.

## 1. Integration Testing via Testcontainers

Our Integration tests (30% of the test pyramid) validate the `adapters` connecting our core logic to external backends. We use `testcontainers-python` to spin up ephemeral infrastructure.

### Setup Requirements
*   A running Docker daemon.
*   `pip install testcontainers`

### Containers Utilized
*   **Redis:** For testing the `DistributedLockManager` adapter. Validates TTL expiration, preemption, and cooling-off state persistence.
*   **[PLANNED] PostgreSQL:** For testing the `PhaseStateRepository`.
*   **Prometheus:** Loaded with static fixture data to test the `PrometheusAdapter` querying accuracy.

*Example pattern in tests:*
```python
with PostgresContainer("postgres:15") as postgres:
    engine = sqlalchemy.create_engine(postgres.get_connection_url())
    # run adapter integration tests
```

## 2. End-to-End (E2E) & Chaos Injection

E2E tests (10% of the pyramid) validate the agent's behavior inside a real cluster loop.

### Setup Requirements
*   `k3d` or `kind` for local Kubernetes.

### Chaos Methodology
We rely on controlled fault injection to trigger the agent's detection layer. Supported synthetic faults:

1.  **OOM Injection:** Running a sidecar container that rapidly consumes `/dev/shm` until Linux OOM Killer triggers it, proving the agent detects eBPF signals.
2.  **Traffic Spiking:** Using `hey` or `k6` to rapidly flood the sample ingress, confirming the agent detects the latency degradation and autoscales the HPA.
3.  **Deployment Sabotage:** Intentionally applying a GitOps config that points to an invalid or crashing `image.tag` to verify the agent catches the 5xx spike and automatically triggers an ArgoCD revert.
4.  **[PLANNED] Certificate Expiry:** A cronjob that manipulates the system clock inside the test pod or explicitly issues a cert manager mock with an expiry set to 5 minutes in the future, proving the agent proactively triggers a cert renewal.
5.  **[PLANNED] Disk Exhaustion:** Spawning a process that sequentially writes to a massive `dd` file filling up the attached PVC above 85% capacity, causing the agent to safely truncate designated `/var/log` paths.

All E2E tests must clean up their own injected chaos after assertion to keep the test suite idempotent.
