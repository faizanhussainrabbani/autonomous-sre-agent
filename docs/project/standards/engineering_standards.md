# Engineering Standards & Code Organization

**Status:** APPROVED  
**Version:** 2.0.0

This document serves to align new contributors with the architectural philosophy, design principles, test strategy, and definitive codebase structure for the Autonomous SRE Agent. Adherence to these standards is mandatory for all contributions.

---

## 1. Directory Structure

The repository exclusively utilizes the **Hexagonal Architecture** pattern (Ports & Adapters) inside the `src/` tree.

```text
autonomous-sre-agent/
├── docs/                 # System design, runbooks, and gap-free knowledge base
├── openspec/             # BDD Specifications, Acceptance Criteria, and Tasks
├── src/
│   └── sre_agent/
│       ├── domain/       # Core: Anomaly detection, RAG logic, Severity classification
│       │   ├── models/   # Canonical data types, enums, domain events
│       │   ├── detection/# Anomaly detection, baselines, signal correlation
│       │   ├── diagnostics/ # (Phase 2) RAG root-cause analysis
│       │   ├── remediation/ # (Phase 3) Action execution, rollback, saga
│       │   └── safety/   # (Phase 3) Guardrails, blast radius, HITL gates
│       ├── ports/        # Abstract interfaces (ABCs) expected by the domain
│       ├── adapters/     # Implementations wrapping SDKs (telemetry, cloud, LLM)
│       ├── api/          # Entrypoints: Webhooks (FastAPI) and CLI commands (Click)
│       ├── events/       # Internal pub/sub for decoupled component messaging
│       └── config/       # Settings, logging, plugin registration
├── tests/
│   ├── unit/             # Domain tests heavily utilizing mock adapters
│   ├── integration/      # Adapter tests relying on testcontainers (Redis, PG)
│   └── e2e/              # Full lifecycle tests using local k3d + injected chaos
```
*(Note: If older documents reference `adapters/actions/` or `adapters/telemetry/`, they are referring to the canonical `src/sre_agent/adapters/` namespace.)*

---

## 2. Software Design Principles

### 2.1 SOLID Principles

All object-oriented code in this repository **must** adhere to the SOLID principles. These are the foundational standard for maintainable, testable, and extensible software.

> **References:** Robert C. Martin, *Agile Software Development: Principles, Patterns, and Practices*; [Real Python — SOLID Principles in Python](https://realpython.com/solid-principles-python/)

#### S — Single Responsibility Principle (SRP)

> *"A class should have only one reason to change."*

Each class in the codebase owns exactly one responsibility:

| Class | Single Responsibility |
|---|---|
| `AnomalyDetector` | Detect threshold violations from canonical metrics |
| `BaselineComputer` | Compute and maintain rolling statistical baselines |
| `SignalCorrelator` | Join multi-signal telemetry into correlated views |
| `AlertCorrelation` | Group related anomalies into deduplicated incidents |
| `PrometheusAdapter` | Translate PromQL queries into canonical metrics |
| `CloudOperatorRegistry` | Route remediation actions to the correct cloud adapter |

**Anti-pattern to avoid:** A "God class" that handles detection, correlation, and notification in one place. If a class has more than ~200 LOC or handles more than one concern, split it.

#### O — Open/Closed Principle (OCP)

> *"Software entities should be open for extension, but closed for modification."*

New telemetry backends, cloud providers, or detection algorithms are added by implementing existing abstract interfaces — never by modifying existing classes.

**Enforcement in this project:**
- New telemetry provider → implement `TelemetryProvider` ABC in `ports/telemetry.py`
- New cloud target → implement `CloudOperatorPort` ABC in `ports/cloud_operator.py`
- New detection heuristic → add a `_detect_*` method in `AnomalyDetector` following the existing pattern; do not modify existing detection methods

#### L — Liskov Substitution Principle (LSP)

> *"Subtypes must be substitutable for their base types."*

Any adapter implementing a port interface must be substitutable without the domain knowing which concrete adapter is active. For example, `OTelProvider` and `NewRelicProvider` both implement `TelemetryProvider` and can be swapped at runtime via configuration — the domain detection layer is never modified.

**Enforcement:** Integration tests must validate that swapping provider A for provider B produces structurally identical canonical output (see AC-5.6).

#### I — Interface Segregation Principle (ISP)

> *"Clients should not be forced to depend upon methods that they do not use."*

Telemetry interfaces are segregated by concern:

| Interface | Responsibility |
|---|---|
| `MetricsQuery` | Metric retrieval only |
| `TraceQuery` | Distributed trace retrieval |
| `LogQuery` | Log retrieval |
| `eBPFQuery` | Kernel-level telemetry |
| `DependencyGraphQuery` | Service topology queries |
| `BaselineQuery` | Baseline data access |

A telemetry adapter that does not support eBPF (e.g., New Relic) implements only the relevant interfaces — it never raises `NotImplementedError` on methods it cannot fulfill.

#### D — Dependency Inversion Principle (DIP)

> *"Abstractions should not depend upon details. Details should depend upon abstractions."*

The **domain layer** (`domain/`) depends only on **port interfaces** (`ports/`), never on concrete adapters. The **adapter layer** (`adapters/`) depends on port interfaces from below and external SDK libraries from outside. The **bootstrap module** (`adapters/bootstrap.py`) is the sole composition root where concrete implementations are wired to abstract ports.

```
domain/ ──depends-on──▸ ports/ (abstract)
adapters/ ──implements──▸ ports/ (concrete)
bootstrap.py ──wires──▸ adapters/ into domain/
```

### 2.2 Domain-Driven Design (DDD)

> **References:** Eric Evans, *Domain-Driven Design: Tackling Complexity in the Heart of Software*; Vaughn Vernon, *Implementing Domain-Driven Design*

This project applies tactical DDD patterns to keep business logic isolated and testable.

#### Bounded Contexts

| Context | Location | Responsibility |
|---|---|---|
| **Detection** | `domain/detection/` | Anomaly detection, baselines, signal correlation, alert grouping |
| **Diagnostics** | `domain/diagnostics/` | RAG root-cause analysis, severity classification (Phase 2) |
| **Remediation** | `domain/remediation/` | Action planning, execution, rollback (Phase 3) |
| **Safety** | `domain/safety/` | Guardrails, blast radius, confidence gating (Phase 3) |

#### Value Objects

Immutable data structures that carry no identity. In this project, all canonical types are value objects implemented as frozen `@dataclass` or `NamedTuple`:

- `CanonicalMetric`, `CanonicalTrace`, `TraceSpan`, `CanonicalLogEntry`
- `ServiceLabels`, `ServiceNode`, `ServiceEdge`

**Rule:** Value objects must be immutable (`frozen=True`), comparable by structure, and contain no business logic beyond validation.

#### Domain Events

State changes are communicated via typed domain events through the `EventBus` port:

```python
@dataclass(frozen=True)
class DomainEvent:
    event_type: str
    timestamp: datetime
    payload: dict
```

**Rule:** Domain events are fire-and-forget. The event producer must not depend on downstream consumers.

#### Aggregates

The `AnomalyDetector` serves as the Detection aggregate root — all detection operations flow through it. External code should not directly invoke `BaselineComputer` or `SignalCorrelator` except through the detector.

### 2.3 Hexagonal Architecture (Ports & Adapters)

> **References:** Alistair Cockburn, *Hexagonal Architecture*; Netflix Engineering blog, *Ready for changes with Hexagonal Architecture*

The hexagonal architecture enforces a strict dependency direction: **inward only**.

```
┌──────────────────────────────────────────────┐
│                  API Layer                    │  ← FastAPI, CLI (Click)
│           (api/main.py, api/cli.py)          │
├──────────────────────────────────────────────┤
│              Adapter Layer                    │  ← OTel, NewRelic, AWS, Azure
│        (adapters/telemetry/, cloud/)         │
├──────────────────────────────────────────────┤
│               Port Layer                     │  ← ABCs: TelemetryProvider,
│         (ports/telemetry.py, etc.)           │     CloudOperatorPort, EventBus
├──────────────────────────────────────────────┤
│              Domain Layer                    │  ← Pure business logic
│    (domain/detection/, models/, events/)     │  ← No external dependencies
└──────────────────────────────────────────────┘
```

**Hard rules:**
1. `domain/` must **never** import from `adapters/` or `api/`
2. `ports/` must contain **only** abstract base classes (ABCs) and type definitions
3. `adapters/` must implement port ABCs and may import external libraries
4. `api/` orchestrates domain and adapters — it is the entry point, not the logic owner
5. `bootstrap.py` is the **sole composition root** — all dependency injection happens here

### 2.4 Event Sourcing & CQRS

> **References:** Martin Fowler, *Event Sourcing*; Greg Young, *CQRS Documents*; Microsoft Azure Architecture Patterns — [Event Sourcing](https://learn.microsoft.com/en-us/azure/architecture/patterns/event-sourcing), [CQRS](https://learn.microsoft.com/en-us/azure/architecture/patterns/cqrs)

This project uses **Event Sourcing** as the primary audit mechanism:

- Every state transition (anomaly detected, incident created, action taken, rollback triggered) is recorded as an immutable `DomainEvent` via the `EventStore` port.
- The event log is the single source of truth for incident lifecycle reconstruction.
- Events are published through the `EventBus` port for decoupled consumption.

**CQRS Separation:**
- **Commands** (write-side): Detection engine emits `AnomalyAlert` events; remediation engine emits action events
- **Queries** (read-side): API endpoints read from the current state projection, not from the event stream directly

**Defined Event Types:**
```python
class EventTypes:
    ANOMALY_DETECTED = "anomaly.detected"
    INCIDENT_CREATED = "incident.created"
    DIAGNOSIS_COMPLETE = "diagnosis.complete"
    REMEDIATION_STARTED = "remediation.started"
    REMEDIATION_COMPLETE = "remediation.complete"
    ROLLBACK_TRIGGERED = "rollback.triggered"
    PHASE_CHANGED = "phase.changed"
    KILL_SWITCH_ACTIVATED = "kill_switch.activated"
```

### 2.5 The Twelve-Factor App

> **References:** Adam Wiggins, [The Twelve-Factor App](https://12factor.net/)

This agent is designed as a cloud-native service. All twelve factors apply:

| Factor | Application in This Project |
|---|---|
| **I. Codebase** | Single repository (`AiOps/`), multiple deploys (dev, staging, prod) |
| **II. Dependencies** | Explicitly declared in `pyproject.toml` with optional extras (`[aws]`, `[azure]`, `[dev]`) |
| **III. Config** | Stored in environment variables; `config/settings.py` uses Pydantic `BaseSettings` for env-based configuration |
| **IV. Backing Services** | Prometheus, Jaeger, Loki, Redis, PostgreSQL are all treated as attached resources, swappable via config |
| **V. Build/Release/Run** | Strict separation: `pyproject.toml` build → Docker image + Cosign signature → GitOps deploy |
| **VI. Processes** | The agent runs as a stateless process; state is externalized to Redis (locks), PostgreSQL (phase state), and event stores |
| **VII. Port Binding** | FastAPI exports the HTTP service via port binding (no external web server required) |
| **VIII. Concurrency** | Scale out via process model — multiple agent replicas with distributed locking prevent conflicts |
| **IX. Disposability** | Fast startup (< 5s); graceful shutdown with lock release and in-flight action completion |
| **X. Dev/Prod Parity** | Testcontainers provide production-identical backends in dev; k3d mirrors production K8s |
| **XI. Logs** | Treated as event streams — `structlog` outputs JSON to stdout; collected by Loki |
| **XII. Admin Processes** | CLI commands (`api/cli.py`) for one-off admin tasks: `halt`, `resume`, `status` |

---

## 3. Cloud Design Patterns

> **References:** Microsoft Azure Architecture Center — [Cloud Design Patterns](https://learn.microsoft.com/en-us/azure/architecture/patterns/)

The following cloud design patterns are actively used or planned for this project:

| Pattern | Usage | Status |
|---|---|---|
| **Circuit Breaker** | `adapters/cloud/resilience.py` — prevents cascading failures when cloud APIs are unresponsive | ✅ Implemented |
| **Retry** | `adapters/cloud/resilience.py` — exponential backoff with jitter for transient failures | ✅ Implemented |
| **Bulkhead** | Provider isolation — OTel failure does not affect NewRelic adapter or cloud operators | ✅ Implemented |
| **Health Endpoint Monitoring** | `/health` and `/api/v1/status` endpoints in `api/main.py` | ✅ Implemented |
| **Event Sourcing** | Immutable event log via `EventStore` port for audit and state reconstruction | ✅ Implemented |
| **CQRS** | Write-side (event emission) separated from read-side (API status queries) | ✅ Implemented |
| **Ambassador** | OTel Collector acts as a sidecar ambassador for telemetry collection | ✅ Infrastructure |
| **Anti-Corruption Layer** | Canonical data model (`canonical.py`) prevents provider-specific types from leaking into the domain | ✅ Implemented |
| **Sidecar** | eBPF programs deployed as node-level sidecars for kernel telemetry | ✅ Infrastructure |
| **Saga** | (Phase 3) Remediation with compensating transactions (rollback on failure) | 🔲 Planned |
| **Leader Election** | (Phase 3) Distributed lock manager for multi-agent coordination | 🔲 Planned |
| **Throttling** | (Phase 3) Rate limiting on remediation actions via cooling-off periods | 🔲 Planned |
| **Compensating Transaction** | (Phase 3) Auto-rollback when post-remediation metrics degrade | 🔲 Planned |

---

## 4. Error Handling Standards

### 4.1 Exception Hierarchy

All custom exceptions must inherit from a base exception class:

```python
class SREAgentError(Exception):
    """Base exception for all SRE Agent errors."""

class TelemetryError(SREAgentError):
    """Errors during telemetry ingestion or querying."""

class DetectionError(SREAgentError):
    """Errors in the anomaly detection pipeline."""

class CloudOperatorError(SREAgentError):
    """Errors during cloud API remediation calls."""

class ConfigurationError(SREAgentError):
    """Invalid or missing configuration."""
```

### 4.2 Error Handling Rules

1. **Never swallow exceptions silently.** Every `except` block must log the error with full context via `structlog`.
2. **Use specific exception types.** Catch the narrowest exception possible; never use bare `except:`.
3. **Fail fast on configuration errors.** Invalid config detected at startup must raise `ConfigurationError` and halt the agent.
4. **Degrade gracefully on runtime errors.** Telemetry backend failures trigger circuit breaker → degraded mode, not agent crash.
5. **Propagate unrecoverable errors.** If an error cannot be handled at the current level, re-raise it for the caller.
6. **Include context in exceptions.** All raised exceptions must include the resource name, operation, and root cause:
   ```python
   raise CloudOperatorError(
       f"Failed to restart ECS task {task_arn}: {e}"
   ) from e
   ```

### 4.3 Error Boundaries

| Boundary | Strategy |
|---|---|
| **Domain layer** | Raise domain-specific exceptions; never catch infra-level errors |
| **Adapter layer** | Catch SDK exceptions, wrap in domain exceptions, apply retry/circuit-breaker |
| **API layer** | Catch domain exceptions, return structured HTTP error responses |
| **Event bus** | Dead-letter queue for failed event handlers; never crash the bus |

---

## 5. Logging Standards

> **Tool:** [structlog](https://www.structlog.org/) for structured, machine-readable JSON logging

### 5.1 Log Levels

| Level | Usage |
|---|---|
| `DEBUG` | Detailed diagnostic information (metric values, query parameters) — disabled in production |
| `INFO` | Normal operations: anomaly detected, baseline computed, provider healthy |
| `WARNING` | Degraded operation: eBPF unavailable, late data arrival, approaching resource limits |
| `ERROR` | Operation failed but recoverable: API call timeout, adapter circuit breaker opened |
| `CRITICAL` | Unrecoverable: kill switch activated, agent unable to start, data loss detected |

### 5.2 Structured Log Fields

Every log entry **must** include:

| Field | Description |
|---|---|
| `event` | Human-readable event description |
| `level` | Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL) |
| `timestamp` | ISO 8601 UTC timestamp |
| `service` | Affected service name (if applicable) |
| `component` | Emitting component (e.g., `anomaly_detector`, `prometheus_adapter`) |
| `trace_id` | Distributed trace ID for correlation (if available) |

**Optional context fields:** `namespace`, `compute_mechanism`, `resource_id`, `provider`, `anomaly_type`, `confidence_score`

### 5.3 Logging Anti-Patterns

- **Never** log secrets, API keys, or bearer tokens
- **Never** log raw user input without sanitization
- **Never** use `print()` statements — always use `structlog`
- **Never** log at `INFO` level inside tight loops (use `DEBUG` or sample)
- **Avoid** string concatenation in log calls — use structlog's key-value binding:
  ```python
  # Bad
  logger.info(f"Detected anomaly on {service}")
  
  # Good
  logger.info("anomaly_detected", service=service, anomaly_type=anomaly_type)
  ```

---

## 6. API Design Standards

### 6.1 REST API Conventions

| Principle | Standard |
|---|---|
| **URL Structure** | `/api/v{N}/{resource}` — versioned, noun-based, lowercase, kebab-case |
| **HTTP Methods** | GET (read), POST (create/action), PUT (replace), PATCH (partial update), DELETE (remove) |
| **Status Codes** | 200 OK, 201 Created, 400 Bad Request, 401 Unauthorized, 404 Not Found, 409 Conflict, 500 Internal Server Error |
| **Response Format** | JSON with consistent envelope: `{"status": "ok|error", "data": {...}, "error": {...}}` |
| **Pagination** | Cursor-based pagination for list endpoints: `?cursor=...&limit=50` |
| **Idempotency** | All POST actions must accept an `Idempotency-Key` header for safe retries |

### 6.2 API Versioning

- API version is embedded in the URL path: `/api/v1/...`
- Breaking changes require a new version (`/api/v2/...`) with a deprecation period for the old version
- Non-breaking additions (new fields, new endpoints) do not require version bumps

### 6.3 Health Endpoints

Every deployed instance **must** expose:

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness probe — returns 200 if the process is alive |
| `GET /api/v1/status` | Readiness probe — returns current phase, provider status, active incidents |

---

## 7. The Test Pyramid (60 / 30 / 10)

Because this agent possesses production write-access, testing is our strongest guardrail.

*   **60% Unit Tests (`tests/unit`):** Fast, isolated tests validating the mathematical algorithms in the anomaly detector, or ensuring the RAG pipeline correctly parses an expected payload. No network calls.
*   **30% Integration Tests (`tests/integration`):** These tests ensure our Adapters work against real infrastructure. We use [Testcontainers](../../testing/test_infrastructure.md) to dynamically spin up Redis, Postgres, and mocked external APIs locally. Code coverage here validates networking resilience, retries, and schema validation.
*   **10% End-to-End Tests (`tests/e2e`):** The final safety gate. These operate against a complete, localized Kubernetes deployment containing a fully configured agent interacting with an actual target service. We employ deliberate [Chaos Injection](../../testing/test_infrastructure.md) to trigger anomalies and verify the agent resolves them within SLOs.

### 7.1 Test Naming Conventions

```
test_{method_or_behavior}_{scenario}_{expected_outcome}
```

Examples:
- `test_detect_latency_spike_above_threshold_fires_alert`
- `test_cold_start_suppression_lambda_no_alert_generated`
- `test_ecs_operator_restart_task_returns_success`

### 7.2 Test Structure (Arrange-Act-Assert)

> **Reference:** Martin Fowler, [GivenWhenThen](https://martinfowler.com/bliki/GivenWhenThen.html)

Every test must follow the AAA pattern:

```python
def test_error_surge_detection():
    # Arrange — Set up test data and dependencies
    detector = AnomalyDetector(config=test_config)
    metrics = create_error_surge_metrics(rate=0.15)

    # Act — Execute the behavior under test
    alerts = detector.detect(metrics)

    # Assert — Verify the expected outcome
    assert len(alerts) == 1
    assert alerts[0].anomaly_type == AnomalyType.ERROR_SURGE
```

### 7.3 Test Isolation Rules

1. **Unit tests** must never make network calls, touch the filesystem, or depend on external state
2. **Integration tests** must use Testcontainers or equivalent — never connect to shared/persistent infrastructure
3. **E2E tests** must create their own ephemeral cluster and clean up after themselves
4. **Tests must not depend on execution order** — each test sets up its own state
5. **Mock at port boundaries only** — mock the port interface, never internal domain classes

### 7.4 Coverage Requirements

| Scope | Minimum Coverage |
|---|---|
| `domain/` package | 100% line coverage |
| `adapters/` package | 90% line coverage |
| `api/` package | 85% line coverage |
| Global | 90% line coverage |

---

## 8. Dependency Injection & Composition

### 8.1 Composition Root

All dependency wiring happens in **one place**: `adapters/bootstrap.py`. This file:

1. Reads configuration from `config/settings.py`
2. Instantiates concrete adapters based on configuration
3. Injects adapters into domain services via constructor injection
4. Returns a fully assembled application context

**Rule:** No adapter or domain class should construct its own dependencies. All dependencies are injected via constructor parameters.

```python
# Good — Constructor injection
class AnomalyDetector:
    def __init__(self, telemetry: TelemetryProvider, config: DetectionConfig):
        self._telemetry = telemetry
        self._config = config

# Bad — Self-construction
class AnomalyDetector:
    def __init__(self):
        self._telemetry = PrometheusAdapter()  # Violates DIP
```

### 8.2 Configuration Injection

All configuration flows through Pydantic `BaseSettings`:

```python
class AgentSettings(BaseSettings):
    telemetry_provider: str = "otel"
    cloud_provider: str = "kubernetes"
    detection_sensitivity: float = 3.0

    class Config:
        env_prefix = "SRE_AGENT_"
```

Environment variables override defaults: `SRE_AGENT_TELEMETRY_PROVIDER=newrelic`

---

## 9. Security Coding Standards

### 9.1 Secrets Management

- **Never** hardcode secrets, API keys, tokens, or credentials in source code
- **Never** commit `.env` files to version control (must be in `.gitignore`)
- Secrets must be injected via environment variables or secrets management backends (Vault, AWS SM, Azure KV)
- `bandit` static analysis enforces no hardcoded secrets in CI pipeline

### 9.2 Input Validation

- All external input (API requests, telemetry payloads, webhook bodies) must be validated via Pydantic models before processing
- Telemetry data must be sanitized before LLM ingestion (Phase 2) to prevent prompt injection
- Never use `eval()`, `exec()`, or `os.system()` with user-controllable input

### 9.3 Least Privilege

- Service accounts must have the minimum IAM permissions required for their function
- Kubernetes RBAC must scope agent permissions to specific namespaces and verbs
- Cloud operator adapters document their required IAM permissions in code comments

### 9.4 Audit Logging

- Every remediation action must be logged to the immutable event store
- Every kill switch activation/deactivation must be logged with operator identity
- Audit logs must be retained for a minimum of 7 years per compliance requirements

---

## 10. Code Style & Formatting

### 10.1 Python Style

| Tool | Purpose | Configuration |
|---|---|---|
| `black` | Opinionated code formatter | Default settings, line length 88 |
| `isort` | Import sorting | Compatible with black profile |
| `flake8` | Linting | Max line length 88, E501 disabled |
| `mypy` | Static type checking | Strict mode |
| `bandit` | Security linting | Default rules |

### 10.2 Type Annotations

- All public functions and methods **must** have complete type annotations
- Use `Optional[T]` for nullable parameters
- Use `Protocol` or `ABC` for interface definitions
- Return types must always be declared — no implicit `None` returns

### 10.3 Docstring Standard

All public classes and functions must have Google-style docstrings:

```python
def detect_latency_spike(
    self,
    metrics: list[CanonicalMetric],
    baseline: BaselineData,
) -> list[AnomalyAlert]:
    """Detect latency spikes by comparing p99 to baseline.

    Args:
        metrics: List of canonical metrics for the service.
        baseline: Pre-computed rolling baseline data.

    Returns:
        List of anomaly alerts for detected spikes.

    Raises:
        DetectionError: If baseline data is insufficient.
    """
```

---

## 11. Code Review Guidelines

### 11.1 PR Checklist

Every Pull Request must satisfy:

- [ ] **Spec alignment:** Changes trace to an OpenSpec scenario or task
- [ ] **Tests included:** Unit tests for domain logic, integration tests for adapters
- [ ] **Type-safe:** `mypy --strict` passes with no errors
- [ ] **Formatted:** `black` and `isort` applied
- [ ] **No regressions:** All existing tests pass
- [ ] **Documentation updated:** Architecture docs, API contracts, or glossary updated if applicable
- [ ] **No secrets:** `bandit` scan clean
- [ ] **Conventional commit:** Commit message follows `type(scope): description` format

### 11.2 Review Focus Areas

Reviewers must evaluate:

1. **Architectural compliance:** Does the change respect layer boundaries (domain → ports → adapters)?
2. **Error handling:** Are exceptions caught at the right boundary? Are errors logged with context?
3. **Testability:** Can the new code be unit-tested in isolation?
4. **Performance:** Does the change introduce O(n²) operations or blocking I/O in the hot path?
5. **Safety:** For remediation code — is there a blast radius limit? Can it be rolled back?

---

## 12. Performance Standards

### 12.1 Latency SLOs

| Pipeline Stage | Target Latency |
|---|---|
| Telemetry ingestion | < 10 seconds from emission to agent receipt |
| Anomaly detection | < 60 seconds from threshold crossing to alert |
| Error rate surge | < 30 seconds from onset to alert |
| Proactive resource alert | < 120 seconds from condition becoming true |
| Full pipeline (detect → diagnose → remediate) | < 5 minutes (Phase 3 target) |

### 12.2 Resource Budgets

| Resource | Budget |
|---|---|
| Agent memory | 4–8 GB per instance |
| Agent CPU | 2 vCPU per instance |
| eBPF CPU overhead | ≤ 2% per host node |
| API response time | < 200ms for health/status endpoints |

### 12.3 Performance Anti-Patterns

- **No synchronous HTTP calls in the detection hot path** — use async or background workers
- **No unbounded in-memory collections** — all caches must have max-size limits and TTLs
- **No `SELECT *` equivalent queries** — always specify time ranges and metric filters
- **Profile before optimizing** — premature optimization violates YAGNI

---

## 13. Development Workflow

1.  Review the BDD scenarios in `openspec/`.
2.  Write isolated Unit tests targeting `domain/` models.
3.  Write Integration tests for any new `adapters/` requiring external dependencies.
4.  Submit a Pull Request. All tests must pass the [CI/CD Pipeline Gates](../../operations/ci_cd_pipeline.md) before merging.
5.  PR must be approved by at least one reviewer familiar with the affected layer.
6.  Squash-merge with a conventional commit message.

---

## 14. Conventional Commit Messages

```
type(scope): concise description

[optional body with context]

[optional footer: BREAKING CHANGE, Refs, Closes]
```

| Type | Usage |
|---|---|
| `feat` | New feature |
| `fix` | Bug fix |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `test` | Adding or correcting tests |
| `docs` | Documentation only changes |
| `chore` | Build process, CI, or dependency changes |
| `perf` | Performance improvement |
| `security` | Security-related change |

---

## 15. Document Versioning

All documents in `docs/` must include a header block:

```markdown
**Status:** DRAFT | APPROVED
**Version:** X.Y.Z
```

- **DRAFT**: Under active development, subject to change
- **APPROVED**: Reviewed and accepted by the team
- Version follows [Semantic Versioning](https://semver.org/): MAJOR.MINOR.PATCH
