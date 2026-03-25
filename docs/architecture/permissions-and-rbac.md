---
title: Permissions and RBAC
description: Least-privilege permission model for Autonomous SRE Agent across Kubernetes, AWS, and Azure operations.
ms.date: 2026-03-19
ms.topic: reference
author: SRE Agent Engineering Team
status: APPROVED
---

## Purpose

This document defines minimum permission baselines required for safe operation and controlled remediation.

## Permission design principles

* Least privilege by default
* Namespace and resource scoping over wildcard permissions
* Separation of read telemetry permissions from write remediation permissions
* Human override and auditability for high-risk actions
* Time-bounded credentials for automation where possible

## Kubernetes baseline

Minimum action scope for controlled remediation:

* `restart`, `scale`, `patch` limited to approved namespaces and resource classes
* No cluster-admin requirement for routine remediation
* Explicit deny list for unsafe resource types

Recommended controls:

* Dedicated service account for agent runtime
* Role and RoleBinding scoped per environment
* Admission controls to enforce policy and deny non-compliant actions

## AWS IAM baseline

Minimum action scope for current adapters:

* `ecs:StopTask`
* `ecs:UpdateService`
* `autoscaling:SetDesiredCapacity`
* `lambda:PutFunctionConcurrency`

Recommended controls:

* Restrict resources by ARN patterns
* Separate read-only telemetry role from remediation role
* Log all write operations to centralized audit stream

## Azure RBAC baseline

Minimum action scope for current adapters:

* `Microsoft.Web/sites/restart/Action`
* `Microsoft.Web/serverfarms/write`

Recommended controls:

* Scope role assignments to minimal resource groups
* Use managed identities where possible
* Apply policy constraints for forbidden scaling or restart patterns

## Coordination permissions

Lock manager access requirements:

* Read and write lock keys
* Read and write cooldown keys
* Publish and subscribe to revoke and preemption channels

Human override requirements:

* Elevated operational access must remain outside normal agent role
* Override actions must be auditable and traceable to operator identity

## Validation checklist

Use this checklist before enabling autonomous operation:

* Agent role cannot perform unrestricted wildcard write actions
* Namespace and resource filters are configured
* Kill-switch path is tested and documented
* Audit logs for write actions are enabled
* Dry-run mode can be toggled without redeploying credentials

## Related documents

* [Guardrails configuration](../security/guardrails_configuration.md)
* [Multi-agent coordination](multi-agent-coordination.md)
* [Kill switch runbook](../operations/runbooks/kill_switch.md)
