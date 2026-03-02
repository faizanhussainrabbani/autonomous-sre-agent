# Engineering Standards & Code Organization

**Status:** DRAFT
**Version:** 1.0.0

This document serves to align new contributors with the architectural philosophy, test strategy, and definitive codebase structure for the SRE Agent.

## 1. Directory Structure

The repository exclusively utilizes the **Hexagonal Architecture** pattern (Ports & Adapters) inside the `src/` tree.

```text
autonomous-sre-agent/
├── docs/                 # System design, runbooks, and gap-free knowledge base
├── openspec/             # BDD Specifications, Acceptance Criteria, and Tasks
├── src/
│   └── sre_agent/
│       ├── domain/       # Core: Anomaly detection, RAG logic, Severity classification
│       ├── ports/        # Interfaces expected by the domain (e.g., ActionExecutor)
│       ├── adapters/     # Implementations wrapping SDKs (e.g., K8sClient, SlackApp)
│       ├── api/          # Entrypoints: Webhooks (FastAPI) and CLI commands
│       └── events/       # Internal pub/sub for decoupled component messaging
├── tests/
│   ├── unit/             # Domain tests heavily utilizing mock adapters
│   ├── integration/      # Adapter tests relying on testcontainers (Redis, PG)
│   └── e2e/              # Full lifecycle tests using local k3d + injected chaos
```
*(Note: If older documents reference `adapters/actions/` or `adapters/telemetry/`, they are referring to the canonical `src/sre_agent/adapters/` namespace.)*

## 2. The Test Pyramid (60 / 30 / 10)

Because this agent possesses production write-access, testing is our strongest guardrail.

*   **60% Unit Tests (`tests/unit`):** Fast, isolated tests validating the mathematical algorithms in the anomaly detector, or ensuring the RAG pipeline correctly parses an expected payload. No network calls.
*   **30% Integration Tests (`tests/integration`):** These tests ensure our Adapters work against real infrastructure. We use [Testcontainers](../operations/test_infrastructure.md) to dynamically spin up Redis, Postgres, and mocked external APIs locally. Code coverage here validates networking resilience, retries, and schema validation.
*   **10% End-to-End Tests (`tests/e2e`):** The final safety gate. These operate against a complete, localized Kubernetes deployment containing a fully configured agent interacting with an actual target service. We employ deliberate [Chaos Injection](../operations/test_infrastructure.md) to trigger anomalies and verify the agent resolves them within SLOs.

## 3. Development Workflow

1.  Review the BDD scenarios in `openspec/`.
2.  Write isolated Unit tests targeting `domain/` models.
3.  Write Integration tests for any new `adapters/` requiring external dependencies.
4.  Submit a Pull Request. All tests must pass the [CI/CD Pipeline Gates](../operations/ci_cd_pipeline.md) before merging.
