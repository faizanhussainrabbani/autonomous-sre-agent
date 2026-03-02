# CI/CD Pipeline & Test Gates

**Target Audience:** All Contributors
**Status:** DRAFT

## Overview
Because the SRE Agent manages tier-0 infrastructure, every pull request goes through rigorous automated testing gates before merging. We enforce a strict continuous integration policy to guarantee stability.

## Pull Request Pipeline

When a developer opens a Pull Request to the `main` branch, the following GitHub Actions pipeline executes:

### 1. Static Analysis & Linting (Gate 1)
*   **Target:** `make lint`
*   **Checks:** `flake8`, `black`, `mypy` (strict mode), and `isort`.
*   **Security:** `bandit` scanning for hardcoded secrets or unsafe Python execution (e.g., `os.system`).
*   **Failure:** Blocks merge immediately.

### 2. Unit Testing (Gate 2)
*   **Target:** `pytest tests/unit --cov=src`
*   **Requirement:** 100% pass rate.
*   **Coverage:** Code coverage must not drop below 90% globally, and 100% for the `domain/` package.

### 3. Integration Testing (Gate 3)
*   **Target:** `pytest tests/integration`
*   **Environment:** Ephemeral Docker containers are spun up via `testcontainers-python` (Redis, Prometheus, Postgres).
*   **Requirement:** 100% pass rate. Asserts that the adapters correctly communicate with the mocked backends.

### 4. E2E & Chaos Testing (Gate 4)
*   **Target:** `pytest tests/e2e`
*   **Environment:** An ephemeral `k3d` Kubernetes cluster is provisioned.
*   **Execution:** A mock application is deployed, and an anomaly (e.g., OOM kill) is synthetically injected. The agent must detect and remediate it within the defined SLO.
*   **Failure:** Blocks merge. E2E flakes require a post-mortem.

## Deployment Pipeline (Continuous Delivery)

1.  **Tagging:** Merging to `main` auto-generates a semantic version tag (e.g., `v1.2.3`).
2.  **Container Build:** Builds the `sre-agent` Docker image, signs it with Sigstore/Cosign, and pushes to our private registry.
3.  **GitOps Sync:** A PR is automatically created against the `infra-config` repository updating the Helm chart `image.tag`.

No direct applies to production Kubernetes are permitted; everything must flow through the GitOps delivery process.
