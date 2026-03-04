# ADR-002: Pydantic BaseModel Over Python Dataclasses

**Status:** ACCEPTED  
**Date:** 2024-12-15  
**Authors:** SRE Agent Engineering Team  
**Deciders:** Tech Lead

---

## Context

The SRE Agent's canonical data model (`CanonicalMetric`, `CanonicalTrace`, `CanonicalLogEntry`, `AnomalyAlert`, `Incident`) must enforce strict input validation at the boundary between untrusted telemetry data and the trusted domain layer. Python's built-in `dataclasses` provide no runtime validation.

## Decision

Use **Pydantic `BaseModel`** classes for all canonical domain models instead of Python `dataclasses`.

## Consequences

### Positive
- Runtime type validation on all incoming telemetry data.
- Automatic serialization/deserialization (`.model_dump()`, `.model_validate()`).
- Built-in enum constraint enforcement (e.g., `AnomalyType`, `IncidentPhase`).
- JSON Schema generation for API contract documentation.

### Negative
- Slight performance overhead compared to plain dataclasses.
- Pydantic v2 migration required if starting from v1.

### Risks
- Over-reliance on Pydantic validators could hide logic that belongs in domain services.

## Alternatives Considered

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| Python `dataclasses` | Stdlib, lightweight | No runtime validation | Rejected |
| `attrs` library | Validators, slots | Less ecosystem support than Pydantic | Rejected |
| **Pydantic `BaseModel`** | Full validation, serialization, schema generation | Extra dependency | **Selected** |

## References

- [Data Model Documentation](../../architecture/data_model.md)
- [Canonical Models Source](../../../src/sre_agent/domain/models/canonical.py)
