---
title: Documentation Index
description: Canonical documentation entry point for contributors, operators, maintainers, and automation agents.
ms.date: 2026-03-19
ms.topic: overview
author: SRE Agent Engineering Team
status: APPROVED
---

## Audience routing

### New contributor

* [Getting started](getting-started.md)
* [Development setup](development/setup.md)
* [Testing workflow](development/testing.md)
* [Contributing workflow](development/contributing.md)

### Operator and user

* [Deployment runbook](operations/runbooks/deployment.md)
* [Incident response runbook](operations/runbooks/incident_response.md)
* [Rollback and recovery controls](operations/runbooks/agent_failure_runbook.md)
* [Kill switch procedure](operations/runbooks/kill_switch.md)

### Maintainer

* [Architecture overview](architecture/overview.md)
* [System architecture deep dive](architecture/architecture.md)
* [Engineering standards](project/standards/engineering_standards.md)
* [ADR index](project/ADRs/)

### Future agents and automation

* [Multi-agent coordination](architecture/multi-agent-coordination.md)
* [Permissions and RBAC](architecture/permissions-and-rbac.md)
* [Guardrails configuration](security/guardrails_configuration.md)
* [Glossary authority](reference/glossary.md)

## Core documentation domains

| Domain | Entry point | Purpose |
|---|---|---|
| Architecture | [architecture/](architecture/) | Concepts, models, and system internals |
| Operations | [operations/](operations/) | Deployment, runbooks, and runtime procedures |
| Development | [development/README.md](development/README.md) | Contributor setup, testing, style, and contribution workflow |
| Reference | [reference/README.md](reference/README.md) | Stable lookup docs for API, commands, runbooks, glossary, and taxonomy |
| Security | [security/](security/) | Threat model, guardrails, and safety controls |
| Testing | [testing/](testing/) | Strategy, environment, and validation coverage |
| Project and standards | [project/](project/) | Roadmap, standards, ADRs, and governance artifacts |
| Reports | [reports/](reports/) | Analysis, verification, and historical records |

## Quick navigation by task

| Task | Document |
|---|---|
| Run first-time setup | [getting-started.md](getting-started.md) |
| Understand detection-to-remediation flow | [architecture/overview.md](architecture/overview.md) |
| Configure permissions safely | [architecture/permissions-and-rbac.md](architecture/permissions-and-rbac.md) |
| Execute an incident runbook | [reference/runbooks.md](reference/runbooks.md) |
| Follow contribution standards | [development/code-style.md](development/code-style.md) |
| Find stable commands | [reference/commands.md](reference/commands.md) |

## Canonical governance references

* [Documentation lifecycle policy](project/standards/documentation_lifecycle_policy.md)
* [Documentation quality SLOs](project/standards/documentation_quality_slos.md)
* [Document taxonomy](reference/document-taxonomy.md)

