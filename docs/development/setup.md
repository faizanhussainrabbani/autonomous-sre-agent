---
title: Development Setup
description: Contributor setup path for local environment bootstrap, dependencies, and first validation checks.
ms.date: 2026-03-19
ms.topic: how-to
author: SRE Agent Engineering Team
status: APPROVED
---

## Setup workflow

1. Run bootstrap setup

```bash
bash scripts/dev/run.sh setup
```

2. Create environment file

```bash
cp .env.example .env
```

3. Start dependencies if running integration or demo flows

```bash
bash scripts/dev/setup_deps.sh start
```

4. Run first validation

```bash
bash scripts/dev/run.sh test:unit
```

## Canonical references

* [Getting started](../getting-started.md)
* [Onboarding guide](../project/onboarding.md)
* [External dependencies](../operations/external_dependencies.md)
