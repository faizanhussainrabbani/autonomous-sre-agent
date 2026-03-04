# ADR-001: Hexagonal Architecture (Ports & Adapters)

**Status:** ACCEPTED  
**Date:** 2024-12-01  
**Authors:** SRE Agent Engineering Team  
**Deciders:** Tech Lead, SRE Lead

---

## Context

The SRE Agent must interface with multiple telemetry backends (Prometheus, Jaeger, Loki, New Relic), multiple cloud operators (Kubernetes, AWS ECS, AWS Lambda, Azure App Service), and potentially multiple LLM providers. Tight coupling to any single vendor would make the system fragile and limit extensibility.

## Decision

Adopt a **Hexagonal Architecture (Ports & Adapters)** pattern:

- **Domain Layer** (`src/sre_agent/domain/`): Pure business logic with zero external dependencies. Contains detection, correlation, and baseline services.
- **Ports** (`src/sre_agent/ports/`): Abstract interfaces (`TelemetryPort`, `CloudOperatorPort`, `LLMPort`) defining what the domain needs.
- **Adapters** (`src/sre_agent/adapters/`): Concrete implementations wired at startup via the composition root (`adapters/bootstrap.py`).

## Consequences

### Positive
- Domain logic is fully testable in isolation (unit tests with mocks).
- Adding a new cloud provider requires only a new adapter, not domain changes.
- Provider parity validation is possible via contract tests.

### Negative
- Higher initial boilerplate (port interfaces, adapter registries).
- Requires discipline — developers must not import adapters in domain code.

### Risks
- Leaky abstractions if adapters expose provider-specific behavior through port interfaces.

## Alternatives Considered

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| Monolithic service layer | Simpler initial setup | Tight coupling, hard to test | Rejected |
| Microservices per provider | Strong isolation | Operational overhead, distributed transactions | Rejected |
| **Hexagonal / Ports & Adapters** | Clean separation, testable, extensible | More boilerplate | **Selected** |

## References

- [Architecture Guide](../../architecture/architecture.md)
- [Extensibility Guide](../../architecture/extensibility.md)
