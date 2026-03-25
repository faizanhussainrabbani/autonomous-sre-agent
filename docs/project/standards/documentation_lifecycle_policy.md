---
title: Documentation Lifecycle Policy
description: Policy for active, deprecated, and archived documentation states, including ownership and review cadence.
ms.date: 2026-03-19
ms.topic: reference
author: SRE Agent Engineering Team
status: APPROVED
---

## Policy objective

Maintain documentation accuracy, discoverability, and safety by applying lifecycle state controls.

## Lifecycle states

| State | Definition | Required action |
|---|---|---|
| Active | Current and maintained documentation | Keep links valid, assign owner, review on release |
| Deprecated | Still reachable but replaced by newer source | Add deprecation notice and canonical pointer |
| Archived | Historical artifact not used for current operation | Move to archive path and mark as historical |

## Ownership model

Each top-level domain has an owner:

* Architecture
* Operations
* Security
* Testing
* Project and standards
* Reports

Owners review active docs on release cadence and approve lifecycle transitions.

## Required controls

* Canonical source declaration for overlapping topics
* Link integrity validation before merge
* Safety-critical document review by operations maintainers
* Deprecation window of at least one release cycle before archival, unless emergency correction is required

## Archive policy

Archive criteria:

* Point-in-time report with no open action items
* Superseded implementation plan after completion
* Obsolete draft with replaced canonical source

Archive location:

* `docs/reports/archive/` for report artifacts
* Domain-specific archive folders when required by ownership teams
