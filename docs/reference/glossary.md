---
title: Glossary Authority
description: Canonical terminology for coordination, safety, and incident lifecycle concepts used across the repository.
ms.date: 2026-03-19
ms.topic: reference
author: SRE Agent Engineering Team
status: APPROVED
---

## Canonical glossary terms

### Incident lifecycle terms

* Alert: Raw signal from observability systems
* Anomaly: Statistically significant deviation from baseline
* Incident: Confirmed actionable service disruption
* Remediation: Strategy and actions applied to restore health
* Resolution: Verified return to healthy state

### Coordination and safety terms

* Fencing token: Monotonic token preventing stale lock holders from writing actions
* Priority level: Deterministic lock conflict precedence value
* Lock acquisition: Grant of scoped exclusive operation rights on target resource
* Preemption: Higher-priority lock request replacing active lower-priority lock
* Cooldown: Time-bounded suppression key preventing oscillating repeat actions
* Kill switch: Human-controlled global stop for autonomous actions

### Architecture terms

* Hexagonal architecture: Domain isolated from external integrations via ports and adapters
* Port: Interface boundary consumed by domain logic
* Adapter: Concrete implementation of external provider behavior

## Authority and compatibility

This glossary is the canonical term authority for documentation routing. Historical glossary content remains available in [project glossary](../project/glossary.md).
