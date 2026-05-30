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

## Slow-response detection model (Phase 2.5)

Phase 2.5 introduced a hybrid latency detection model alongside the existing sigma-based spike detector.

Detection rules are evaluated as candidates for every latency metric. A single alert is emitted per evaluation cycle using the following precedence:

```
TIMEOUT_PROXIMITY > SLOW_RESPONSE > LATENCY_SPIKE
```

Rules:

* **LATENCY_SPIKE** (pre-existing): sigma-based, requires an established baseline, fires when deviation exceeds the configured multiplier.
* **SLOW_RESPONSE** (Phase 2.5): absolute-threshold, no baseline required. Fires when a latency metric exceeds `slow_response_absolute_threshold_ms` for `slow_response_duration_seconds` consecutively. Applies to Kubernetes, ECS, and Lambda.
* **TIMEOUT_PROXIMITY** (Phase 2.5): serverless-only. Fires when Lambda duration is at or above `timeout_proximity_percent` of the function's configured timeout. Cold-start suppression is applied during the first `cold_start_suppression_window_seconds` of a function's lifecycle.

Platform metric support added in Phase 2.5A:

* `http_request_duration_p99` — Kubernetes p99 response time
* `ecs_response_time_ms` — ECS Container Insights `ResponseTime`
* `lambda_duration_ms` — Lambda duration enriched with `timeout_ms` metadata via `AWSResourceMetadataFetcher`

Azure App Service support (`appservice_response_time_ms`) is deferred to Phase 2.5B, pending availability of the Azure Monitor adapter.
