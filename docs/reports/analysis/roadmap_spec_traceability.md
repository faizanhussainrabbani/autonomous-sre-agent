# Roadmap-to-Spec Traceability Matrix

**Purpose:** Maps each Q1–Q4 2026 competitively-driven roadmap item to its corresponding OpenSpec change, capability spec, and implementation status.

**Source:** [Competitively-Driven Roadmap](../../project/roadmap_competitive_driven.md) | [Competitive Analysis Report](competitive_analysis_report.md)

---

## Full Traceability

| # | Roadmap Item | Quarter | Action | OpenSpec Change | Capability Spec Updated | BDD Spec Created |
|---|---|---|---|---|---|---|
| 1 | Intelligence Layer Hardening | Q1 | Update existing | — (hardening only) | [rag-diagnostics](../../../openspec/changes/autonomous-sre-agent/specs/rag-diagnostics/spec.md) | ✅ 4 hardening requirements |
| 2 | Slack/Teams Integration | Q2 | New change | [phase-2-6-notification-integrations](../../../openspec/changes/phase-2-6-notification-integrations/) | [notifications](../../../openspec/changes/autonomous-sre-agent/specs/notifications/spec.md) | ✅ [notification-delivery](../../../openspec/changes/phase-2-6-notification-integrations/specs/notification-delivery/spec.md) |
| 3 | PagerDuty/OpsGenie Integration | Q2 | Bundled with #2 | [phase-2-6-notification-integrations](../../../openspec/changes/phase-2-6-notification-integrations/) | [notifications](../../../openspec/changes/autonomous-sre-agent/specs/notifications/spec.md) | ✅ (included in #2) |
| 4 | Operator Dashboard MVP | Q2 | New change | [phase-2-7-operator-dashboard](../../../openspec/changes/phase-2-7-operator-dashboard/) | [operator-dashboard](../../../openspec/changes/autonomous-sre-agent/specs/operator-dashboard/spec.md) | ✅ [dashboard-mvp](../../../openspec/changes/phase-2-7-operator-dashboard/specs/dashboard-mvp/spec.md) |
| 5 | Multi-Agent Protocol Spec | Q2 | **No OpenSpec** | — | — | — (documentation deliverable) |
| 6 | SOC 2 Type II Prep | Q3 | **No OpenSpec** | — | — | — (compliance process) |
| 7 | Helm Chart + K8s Operator | Q3 | New change | [phase-3-1-helm-deployment](../../../openspec/changes/phase-3-1-helm-deployment/) | — (new capability) | ✅ [helm-deployment](../../../openspec/changes/phase-3-1-helm-deployment/specs/helm-deployment/spec.md) |
| 8 | Datadog Telemetry Adapter | Q3 | New change | [phase-2-8-datadog-adapter](../../../openspec/changes/phase-2-8-datadog-adapter/) | [provider-abstraction](../../../openspec/changes/autonomous-sre-agent/specs/provider-abstraction/spec.md) | ✅ [datadog-adapter](../../../openspec/changes/phase-2-8-datadog-adapter/specs/datadog-adapter/spec.md) |
| 9 | Community OSS Launch | Q3 | **No OpenSpec** | — | — | — (go-to-market activity) |
| 10 | GCP Support | Q4 | New change | [phase-3-2-gcp-support](../../../openspec/changes/phase-3-2-gcp-support/) | [cloud-portability](../../../openspec/changes/autonomous-sre-agent/specs/cloud-portability/spec.md) | ✅ [gcp-operator](../../../openspec/changes/phase-3-2-gcp-support/specs/gcp-operator/spec.md) |
| 11 | FinOps-Aware Remediation | Q4 | New change | [phase-3-3-finops-remediation](../../../openspec/changes/phase-3-3-finops-remediation/) | — (new capability) | ✅ [finops-enrichment](../../../openspec/changes/phase-3-3-finops-remediation/specs/finops-enrichment/spec.md) |
| 12 | Marketplace Listings | Q4 | **No OpenSpec** | — | — | — (infrastructure/packaging) |

---

## OpenSpec Change Index

| Phase | Change | Files | Status |
|---|---|---|---|
| 2.6 | [phase-2-6-notification-integrations](../../../openspec/changes/phase-2-6-notification-integrations/) | `.openspec.yaml`, `proposal.md`, `design.md`, `tasks.md`, `specs/notification-delivery/spec.md` | Draft |
| 2.7 | [phase-2-7-operator-dashboard](../../../openspec/changes/phase-2-7-operator-dashboard/) | `.openspec.yaml`, `proposal.md`, `design.md`, `tasks.md`, `specs/dashboard-mvp/spec.md` | Draft |
| 2.8 | [phase-2-8-datadog-adapter](../../../openspec/changes/phase-2-8-datadog-adapter/) | `.openspec.yaml`, `proposal.md`, `design.md`, `tasks.md`, `specs/datadog-adapter/spec.md` | Draft |
| 3.1 | [phase-3-1-helm-deployment](../../../openspec/changes/phase-3-1-helm-deployment/) | `.openspec.yaml`, `proposal.md`, `design.md`, `tasks.md`, `specs/helm-deployment/spec.md` | Draft |
| 3.2 | [phase-3-2-gcp-support](../../../openspec/changes/phase-3-2-gcp-support/) | `.openspec.yaml`, `proposal.md`, `design.md`, `tasks.md`, `specs/gcp-operator/spec.md` | Draft |
| 3.3 | [phase-3-3-finops-remediation](../../../openspec/changes/phase-3-3-finops-remediation/) | `.openspec.yaml`, `proposal.md`, `design.md`, `tasks.md`, `specs/finops-enrichment/spec.md` | Draft |

---

## Capability Spec Updates

| Spec | Updates Applied | Cross-Reference Added |
|---|---|---|
| `rag-diagnostics/spec.md` | +4 hardening requirements (latency SLO, accuracy SLO, concurrent stability, graceful degradation) | Source link to roadmap item 1 |
| `notifications/spec.md` | Cross-reference section added | → Phase 2.6, Phase 3.3 |
| `provider-abstraction/spec.md` | Cross-reference section added | → Phase 2.8 |
| `cloud-portability/spec.md` | Cross-reference section added | → Phase 3.2 |

---

## Exclusion Rationale

| Item | Reason for No OpenSpec | Tracking Method |
|---|---|---|
| 5. Multi-Agent Protocol Spec | Documentation/thought-leadership deliverable, not feature code | Project management task board |
| 6. SOC 2 Type II Prep | Compliance process, not software development | Compliance project tracker |
| 9. Community OSS Launch | Go-to-market activity (repo prep, docs, community) | Marketing/DevRel task board |
| 12. Marketplace Listings | Infrastructure packaging, not feature code | DevOps CI/CD pipeline tasks |
