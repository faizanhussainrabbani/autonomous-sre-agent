## Why

Sedai's strongest competitive differentiator is combining reliability automation with cost optimization. Our competitive analysis identified that while the multi-agent protocol (AGENTS.md) defines FinOps Agent coordination, the SRE Agent itself has no cost awareness. When the agent scales up a deployment from 3→5 replicas, neither the operator nor the audit trail captures the cost impact of that decision.

This change adds cost-context enrichment to all scaling and resource-modifying remediations, without blocking remediation actions — cost visibility is additive, not gating.

## What Changes

- **New `CostProviderPort` ABC** (`ports/cost.py`): Abstract interface for querying per-workload cost data
- **New kubecost adapter** (`adapters/cost/kubecost.py`): Implements `CostProviderPort` using kubecost/OpenCost allocation API
- **Updated RemediationAction data model**: `cost_impact_monthly_usd` field added to remediation actions and audit trail
- **Updated remediation engine**: Cost enrichment step before execution — queries `CostProviderPort` for current cost, estimates new cost, and attaches delta to proposal
- **Updated audit trail**: `cost_impact` section in event payloads

## Capabilities

### New Capabilities
- `cost-context-enrichment`: Cost impact estimation for all scaling remediations
- `kubecost-integration`: Per-workload cost data from kubecost/OpenCost

### Modified Capabilities
- `remediation-engine`: Cost context attached to all resource-modifying actions
- `safety-guardrails`: Cost impact visible in HITL approval requests

## Impact

- **Dependencies**: `requests` (kubecost API is HTTP), optional `opencost-py` if available
- **Configuration**: `SRE_AGENT_COST_PROVIDER=kubecost`, `SRE_AGENT_KUBECOST_API_URL`
- **Non-blocking**: If cost provider is unavailable, remediation proceeds with `cost_impact=null`
