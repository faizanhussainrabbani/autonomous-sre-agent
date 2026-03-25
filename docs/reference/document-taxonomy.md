---
title: Document Taxonomy
description: Approved documentation classes and placement rules for consistency, discoverability, and automation reliability.
ms.date: 2026-03-19
ms.topic: reference
author: SRE Agent Engineering Team
status: APPROVED
---

## Approved document classes

Use these classes for authoring and classification:

* overview
* how-to
* reference
* runbook
* policy
* adr
* report

## Placement rules

| Class | Default location |
|---|---|
| overview | `docs/` and domain landing pages |
| how-to | `docs/getting-started.md`, `docs/development/`, `docs/operations/` |
| reference | `docs/reference/`, `docs/api/` |
| runbook | `docs/operations/runbooks/` |
| policy | `docs/project/standards/`, root policy files |
| adr | `docs/project/ADRs/` |
| report | `docs/reports/` |

## Canonical source declaration

When multiple pages describe the same topic:

* One page must declare itself canonical
* Non-canonical pages must route readers to canonical source
* Deprecated pages must include migration pointer and review date
