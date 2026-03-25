---
title: Development Testing
description: Contributor-oriented testing entry point with command matrix and links to canonical testing strategy.
ms.date: 2026-03-19
ms.topic: how-to
author: SRE Agent Engineering Team
status: APPROVED
---

## Test command matrix

```bash
bash scripts/dev/run.sh test:unit
bash scripts/dev/run.sh test:e2e
bash scripts/dev/run.sh test
bash scripts/dev/run.sh coverage
```

## Integration and provider tests

For provider-backed tests, start dependencies first:

```bash
bash scripts/dev/setup_deps.sh start
```

## Canonical references

* [Testing strategy](../testing/testing_strategy.md)
* [LocalStack Pro guide](../testing/localstack_pro_guide.md)
* [Live validation test cases](../testing/live_validation_test_cases.md)
