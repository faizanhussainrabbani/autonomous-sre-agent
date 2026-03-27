## Context

The SRE Agent's remediation engine executes scaling and restart actions without any cost awareness. The AGENTS.md multi-agent protocol defines FinOps Agent coordination at the lock protocol level, but the SRE Agent itself does not consume cost data. Sedai demonstrates that combining reliability + cost visibility is a strong market differentiator.

## Goals / Non-Goals

**Goals:**
- Define `CostProviderPort` ABC for querying per-workload cost data
- Implement kubecost/OpenCost adapter as first cost data source
- Enrich all scaling remediations with estimated monthly cost impact (before/after delta)
- Include cost impact in audit trail events and HITL approval notifications
- Cost enrichment is non-blocking — remediation never fails due to cost provider unavailability
- Monthly cost projection accuracy within 10%

**Non-Goals:**
- Automated cost optimization (that's the FinOps Agent's job, not the SRE Agent)
- Budget alerts or cost thresholds that block remediation
- Reserved instance / savings plan recommendations
- Cross-account cost attribution

## Decisions

### Decision: kubecost allocation API (not raw Prometheus cost metrics)
**Rationale:** kubecost provides pre-calculated per-workload cost allocation including CPU, memory, GPU, network, and PV costs. Building this from raw Prometheus metrics would require replicating kubecost's allocation logic.

### Decision: Cost enrichment is advisory-only (non-gating)
**Rationale:** The SRE Agent's primary mission is reliability. Cost visibility informs operators but must never delay or prevent a remediation action. If the cost provider is unavailable, the remediation proceeds with `cost_impact=null`.

### Decision: Cost delta as monthly projection (not hourly)
**Rationale:** Monthly projections are more meaningful to operators and finance teams. hourly costs are too granular for decision-making.

## Risks / Trade-offs

| Risk | Severity | Mitigation |
|---|---|---|
| kubecost allocation data lags real-time by 5–15 min | Low | Acceptable for cost estimation — not used for gating decisions |
| Cost projection inaccurate for spot/preemptible instances | Medium | Document limitation; use on-demand pricing as upper bound |
| kubecost not deployed in target cluster | Low | Graceful fallback: log warning, set `cost_impact=null`, proceed |
