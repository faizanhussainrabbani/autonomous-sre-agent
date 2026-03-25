---
title: Getting Started
description: Deterministic setup and first-run guide for contributors and operators using the Autonomous SRE Agent.
ms.date: 2026-03-19
ms.topic: tutorial
author: SRE Agent Engineering Team
status: APPROVED
---

## Purpose

Use this guide as the default first-run path. It covers prerequisites, setup, environment variables, first execution, expected outputs, and common failure modes.

## Prerequisites

* Python 3.11 or newer
* Git
* Docker Desktop or Docker Engine
* Optional for cloud demos: AWS and Azure test credentials with least privilege

## Local setup

1. Clone the repository and open it in your terminal
2. Bootstrap dependencies

```bash
bash scripts/dev/run.sh setup
```

3. Create environment file

```bash
cp .env.example .env
```

4. Start local dependencies for integration and demo flows

```bash
bash scripts/dev/setup_deps.sh start
```

## Environment variables

Minimum baseline variables:

* `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`
* `AWS_DEFAULT_REGION` for AWS-backed demos
* Additional values from `.env.example`

For dependency and provider details, see [External dependencies](operations/external_dependencies.md).

## First run

Run core checks in this order:

```bash
bash scripts/dev/run.sh test:unit
bash scripts/dev/run.sh server --reload
```

Open API docs at <http://localhost:8080/docs>.

## Example incident flow

Use one live demo script with pause-skipping enabled:

```bash
SKIP_PAUSES=1 .venv/bin/python scripts/demo/live_demo_06_http_optimizations.py
```

For the complete demo matrix, see [Live demo guide](operations/live_demo_guide.md).

## Expected outputs

Expected signals during successful first run:

* Unit test run exits with code `0`
* API server starts and exposes OpenAPI docs
* Demo script logs timeline phases without uncaught exceptions
* Local dependencies report healthy status

## Common failure modes

### `python: command not found`

Use `python3` or project venv binary `.venv/bin/python`.

### Missing cloud credentials

Set required credentials in `.env` and validate region values before running cloud demos.

### Docker dependency startup failure

Verify Docker is running, then rerun:

```bash
bash scripts/dev/setup_deps.sh start
```

### Integration tests fail due to unavailable providers

Run unit tests first and then enable only providers available in your environment.

## Next steps by role

* New contributor: [Development setup](development/setup.md)
* Operator: [Incident response runbook](operations/runbooks/incident_response.md)
* Maintainer: [Architecture overview](architecture/overview.md)
* Automation author: [Multi-agent coordination](architecture/multi-agent-coordination.md)
