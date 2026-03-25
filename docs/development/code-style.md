---
title: Development Code Style
description: Contributor-facing code style and architecture discipline entry point for this repository.
ms.date: 2026-03-19
ms.topic: reference
author: SRE Agent Engineering Team
status: APPROVED
---

## Required standards

Use these standards as the source of truth:

* [Engineering standards](../project/standards/engineering_standards.md)
* [Documentation standards](../project/standards/FAANG_Documentation_Standards.md)

## Core implementation expectations

* Respect hexagonal boundaries and dependency inversion rules
* Keep domain logic testable and adapter-specific concerns isolated
* Treat safety and auditability as first-order constraints
* Maintain deterministic tests with clear pass or fail behavior
