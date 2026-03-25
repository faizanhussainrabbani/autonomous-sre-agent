---
title: Architecture Overview
description: Conceptual architecture for Autonomous SRE Agent including components, incident flow, integration boundaries, and trust assumptions.
ms.date: 2026-03-19
ms.topic: concept
author: SRE Agent Engineering Team
status: APPROVED
---

## Purpose

This is the conceptual architecture entry point. It explains how the system detects, diagnoses, and remediates incidents while preserving safety and auditability.

## System components

Primary components:

* Detection layer for baseline comparison, anomaly identification, and correlation
* Intelligence layer for retrieval-grounded diagnosis and severity assignment
* Action layer for controlled remediation execution
* Operator adapters for Kubernetes, AWS, and Azure actions
* Orchestration layer for lock management and multi-agent coordination
* Eventing and telemetry adapters for observability ingestion and audit trails

## Detection to remediation flow

1. Telemetry is ingested and normalized into canonical models
2. Detection logic identifies anomalies and builds incident context
3. Intelligence logic proposes diagnosis and remediation intent
4. Safety checks evaluate blast-radius and policy constraints
5. Operator adapters execute approved remediation actions
6. Post-action validation confirms service recovery or triggers rollback controls

See [Incident lifecycle sequence](sequence_incident_lifecycle.md) for sequence-level detail.

## Python and shell boundaries

* Python hosts domain logic, adapter logic, API, and testable orchestration
* Shell scripts orchestrate local setup, runtime convenience, and environment bootstrap
* Shell scripts must not replace domain control logic

## Integration boundaries

Boundary principles:

* Domain code depends on ports, not concrete provider SDKs
* Adapter code encapsulates provider-specific behavior
* External systems are replaceable through adapter boundaries
* Safety and policy checks execute before action adapters are invoked

## Trust and safety assumptions

Assumptions for safe operation:

* Input telemetry is untrusted and must be validated at boundaries
* LLM output is advisory and must be constrained by policy
* Human override and kill-switch controls are always available
* Coordination locks and fencing protect against stale or conflicting actions

Safety references:

* [Multi-agent coordination](multi-agent-coordination.md)
* [Permissions and RBAC](permissions-and-rbac.md)
* [Guardrails configuration](../security/guardrails_configuration.md)
