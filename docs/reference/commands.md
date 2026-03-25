---
title: Command Reference
description: Common commands for setup, testing, serving, dependencies, and demo execution.
ms.date: 2026-03-19
ms.topic: reference
author: SRE Agent Engineering Team
status: APPROVED
---

## Setup and server

```bash
bash scripts/dev/run.sh setup
bash scripts/dev/run.sh server --reload
```

## Testing

```bash
bash scripts/dev/run.sh test:unit
bash scripts/dev/run.sh test:e2e
bash scripts/dev/run.sh test
bash scripts/dev/run.sh coverage
```

## Dependencies

```bash
bash scripts/dev/setup_deps.sh start
bash scripts/dev/setup_deps.sh stop
```

## Validation and demos

```bash
python3 scripts/validation/e2e_validate.py --help
SKIP_PAUSES=1 .venv/bin/python scripts/demo/live_demo_06_http_optimizations.py
```

## Canonical references

* [Live demo guide](../operations/live_demo_guide.md)
* [Testing strategy](../testing/testing_strategy.md)
