# API & Extension Guide

**Status:** DRAFT
**Version:** 1.0.0

The SRE Agent is designed to be deeply extensible. Because of our strict Hexagonal Architecture, internal components (`domain/`) are decoupled from external tools (`adapters/`) using abstract `ports/`.

If you are looking to integrate the SRE Agent into a new cloud provider, new observability backend, or new action executor, you should add new **Adapters**.

## Extending Telemetry Integration (Adding an Observability Backend)
Currently, the SRE Agent supports OpenTelemetry Collector backends (Prometheus, Jaeger, Loki). 

To add support for a new backend (e.g., Datadog, Splunk), follow these steps:

1. **Review the Port:** Look at `src/sre_agent/ports/telemetry.py`. This defines the canonical schema the Domain uses (e.g., `MetricsQuery`, `TraceQuery`).
2. **Create the Adapter:** In `src/sre_agent/adapters/telemetry/datadog_adapter.py`, create a class implementing the Telemetry Port.
3. **Map the Queries:** Write the specific vendor queries (e.g., Datadog API calls) inside the adapter, mapping the raw JSON response out to the Canonical Data Model objects expected by the Port.
4. **Register:** Register your adapter in the application bootstrapper (or dependency injection container).

## Adding a Remediation Action
To teach the agent a new trick (e.g., interacting with a cloud-specific service like AWS RDS snapshotting), you create an Action Adapter.

1. **Review the Port:** Check `src/sre_agent/ports/cloud_operator.py`.
2. **Implement:** Create `src/sre_agent/adapters/actions/aws_rds_snapshot.py` (or an appropriate implementation of `CloudOperatorPort`). You must implement methods ensuring the action is uniquely traceable.
3. **Define Blast Radius:** Make sure your new Action includes a robust implementation of the Guardrails limits—for instance, throwing an exception if the action attempts to snapshot more than 2 clusters at once.

## Generating Documentation Locally
You can render these markdown guides into a static site using typical markdown tools (like MkDocs) if configured for this repository. Ensure any Mermaid diagrams render properly using your documentation engine.
