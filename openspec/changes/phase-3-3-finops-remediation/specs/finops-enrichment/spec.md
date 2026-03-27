## ADDED Requirements — Phase 3.3 FinOps-Aware Remediation

> **Source:** [Competitively-Driven Roadmap](../../../../docs/project/roadmap_competitive_driven.md) — Item 11
> **Competitive Context:** Sedai's strongest differentiator is combining reliability + cost optimization. This adds cost visibility without compromising remediation speed.

### Requirement: Cost Impact Estimation for Scaling Actions
The system SHALL estimate the monthly cost impact for all scaling remediations and include the estimate in the remediation proposal.

#### Scenario: Scale-up cost estimation
- **GIVEN** a remediation proposes scaling a deployment from 3→5 replicas
- **WHEN** the cost provider is available
- **THEN** the remediation proposal SHALL include `cost_impact_monthly_usd` with current, projected, and delta values
- **AND** the cost estimate SHALL be based on per-replica cost data from the cost provider

#### Scenario: Scale-down cost savings estimation
- **GIVEN** a remediation proposes scaling down from 8→5 replicas
- **WHEN** the cost provider is available
- **THEN** `cost_impact_monthly_usd.delta` SHALL be negative (indicating savings)
- **AND** the HITL approval notification SHALL display the estimated monthly savings

#### Scenario: Cost provider unavailable
- **GIVEN** the cost provider (kubecost) is unreachable
- **WHEN** a scaling remediation is proposed
- **THEN** the remediation SHALL proceed without delay
- **AND** `cost_impact_monthly_usd` SHALL be `null`
- **AND** a warning SHALL be logged with `cost_provider_status=unavailable`

### Requirement: Cost Data Accuracy
The cost estimation SHALL meet a minimum accuracy target.

#### Scenario: Monthly projection accuracy
- **GIVEN** kubecost allocation data is available
- **WHEN** cost projection is calculated for a scaling action
- **THEN** the projected monthly cost SHALL be accurate within 10% of actual spend (measured at month-end reconciliation)

### Requirement: Cost Impact in Audit Trail
All remediation events SHALL include cost context for financial accountability.

#### Scenario: Audit trail cost field
- **WHEN** a scaling remediation is executed
- **THEN** the EventStore entry SHALL include `cost_impact` section with `current_monthly_usd`, `projected_monthly_usd`, `delta_monthly_usd`, and `provider_source`

#### Scenario: Post-incident summary includes cost
- **WHEN** a post-incident summary is generated
- **THEN** the summary SHALL include total cost impact of all remediation actions taken during the incident

### Requirement: Cost Context in HITL Notifications
Cost impact SHALL be visible in human approval requests for Sev 1-2 incidents.

#### Scenario: Slack approval with cost context
- **GIVEN** a Sev 2 scale-up remediation requires human approval
- **WHEN** the Slack approval notification is sent
- **THEN** the message SHALL include: "Estimated cost impact: +$X/month" alongside diagnosis and confidence
- **AND** cost impact SHALL be prominently displayed (not buried in detail)

---

## Implementation References

* **Port:** `src/sre_agent/ports/cost.py`
* **Adapter:** `src/sre_agent/adapters/cost/kubecost.py`
* **Remediation Engine:** `src/sre_agent/domain/remediation/`
