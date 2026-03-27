## FIN-001 — Cost Provider Port (Critical Path)

- [ ] 1.1 Create `src/sre_agent/ports/cost.py` — `CostProviderPort` ABC with `get_workload_cost()`, `estimate_scaling_cost()`, `health_check()`
- [ ] 1.2 Define `CostEstimate` data model (current_monthly_usd, projected_monthly_usd, delta_monthly_usd, resource_breakdown)

## FIN-002 — kubecost Adapter (High)

- [ ] 2.1 Create `src/sre_agent/adapters/cost/kubecost.py` implementing `CostProviderPort`
- [ ] 2.2 Implement `get_workload_cost()` using kubecost Allocation API (`/model/allocation`)
- [ ] 2.3 Implement `estimate_scaling_cost()` — linear extrapolation from current per-replica cost
- [ ] 2.4 Handle kubecost API unavailability gracefully (return `None`, log warning)
- [ ] 2.5 Implement `health_check()` — validate kubecost API connectivity

## FIN-003 — Remediation Engine Integration (High)

- [ ] 3.1 Add cost enrichment step in remediation pipeline (before execution, after validation)
- [ ] 3.2 Query `CostProviderPort.estimate_scaling_cost()` for all scaling actions
- [ ] 3.3 Attach `CostEstimate` to `RemediationAction` data model
- [ ] 3.4 Include cost impact in HITL approval notifications (Slack/PagerDuty)

## FIN-004 — Audit Trail Integration (Medium)

- [ ] 4.1 Add `cost_impact_monthly_usd` field to remediation event payloads
- [ ] 4.2 Include cost breakdown in post-incident summary
- [ ] 4.3 Add cost impact to dashboard incident detail view

## FIN-005 — Configuration (Medium)

- [ ] 5.1 Add `CostSettings` to `config/settings.py` (provider, kubecost URL, enabled flag)
- [ ] 5.2 Register cost adapter in `adapters/bootstrap.py`
- [ ] 5.3 Update Helm chart values.yaml with cost provider configuration

## FIN-006 — Testing (High)

- [ ] 6.1 Unit tests for `CostProviderPort` and kubecost adapter with mocked responses
- [ ] 6.2 Integration test: scale-up remediation → cost estimate attached → audit trail includes cost
- [ ] 6.3 Fallback test: kubecost unavailable → remediation proceeds → cost_impact=null
