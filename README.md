---
title: Autonomous SRE Agent
description: AI-powered SRE system that detects, diagnoses, and safely remediates infrastructure incidents with strict guardrails.
ms.date: 2026-03-19
ms.topic: overview
author: SRE Agent Engineering Team
---

## Project summary

Autonomous SRE Agent is an AI-powered reliability system that executes the incident loop from detection to remediation with safety-first controls.

Core value:

* Reduces incident response time by automating diagnosis and action planning
* Grounds diagnostics in telemetry and retrieval context
* Enforces blast-radius, approval, and coordination guardrails

## High-level architecture

The system uses hexagonal architecture with domain logic isolated from cloud, telemetry, and LLM adapters.

Key references:

* [Architecture overview](docs/architecture/overview.md)
* [Incident lifecycle sequence](docs/architecture/sequence_incident_lifecycle.md)
* [Multi-agent coordination](docs/architecture/multi-agent-coordination.md)

## Quick start

```bash
bash scripts/dev/run.sh setup
cp .env.example .env
bash scripts/dev/run.sh test:unit
bash scripts/dev/run.sh server --reload
```

For full first-run setup and troubleshooting, use [Getting started](docs/getting-started.md).

## Documentation entry points

* [Documentation index](docs/README.md)
* [Operations and runbooks](docs/operations/runbooks/)
* [Architecture docs](docs/architecture/)
* [Development docs](docs/development/README.md)
* [Reference docs](docs/reference/README.md)

## Safety and permissions warning

> [!WARNING]
> This project can operate infrastructure actions. Use least-privilege credentials, keep kill-switch procedures ready, and validate guardrail policy before enabling autonomous behavior.

Safety and permission references:

* [Permissions and RBAC](docs/architecture/permissions-and-rbac.md)
* [Guardrails configuration](docs/security/guardrails_configuration.md)
* [Kill switch runbook](docs/operations/runbooks/kill_switch.md)

## Contributing and release discipline

Before contributing, read:

* [Contributing guide](CONTRIBUTING.md)
* [Engineering standards](docs/project/standards/engineering_standards.md)
* [Testing strategy](docs/testing/testing_strategy.md)

## License

MIT License. See `LICENSE`.
