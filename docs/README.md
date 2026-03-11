# Autonomous SRE Agent — Documentation Index

> **Version:** Phase 2 (Intelligence Layer)  
> **Last Updated:** March 10, 2026  
> **Maintainer:** SRE Agent Engineering Team

This index is the canonical entry point for all project documentation. Every document in the `docs/` tree is listed here with its purpose and audience.

---

## Quick Start

| Goal | Go To |
|---|---|
| Understand the system | [Architecture Overview](architecture/architecture.md) |
| Set up a local dev environment | [Onboarding Guide](project/onboarding.md) |
| Run the test suite | [Testing Strategy](testing/testing_strategy.md) |
| Deploy to production | [Deployment Runbook](operations/runbooks/deployment.md) |
| Respond to an active incident | [Incident Response Runbook](operations/runbooks/incident_response.md) |
| Review API contracts | [API Contracts](api/api_contracts.md) |
| Understand coding standards | [Engineering Standards](project/standards/engineering_standards.md) |

---

## 1. API

Reference documentation for all internal and external interfaces.

| Document | Description |
|---|---|
| [api/api_contracts.md](api/api_contracts.md) | REST and event API contracts, request/response schemas, versioning policy |

---

## 2. Architecture

System design, domain models, and layer-by-layer technical breakdowns.

| **Core Architecture** | Description |
|---|---|
| [architecture.md](architecture/architecture.md) | High-level system architecture and hexagonal design overview |
| [Technology_Stack.md](architecture/Technology_Stack.md) | Full technology stack inventory with rationale |
| [dependency_graph.md](architecture/dependency_graph.md) | Service dependency graph structure and traversal |
| [sequence_incident_lifecycle.md](architecture/sequence_incident_lifecycle.md) | Sequence diagrams for detection → diagnosis → remediation |
| [extensibility.md](architecture/extensibility.md) | Extension points: adding new operators, detectors, and providers |

| **Domain Models** | Description |
|---|---|
| [models/data_model.md](architecture/models/data_model.md) | Domain model, canonical data structures, enums |
| [models/incident_taxonomy.md](architecture/models/incident_taxonomy.md) | Incident classification taxonomy and severity definitions |
| [models/state_incident_model.md](architecture/models/state_incident_model.md) | Finite state machine for incident lifecycle |

| **Evolution & Future** | Description |
|---|---|
| [evolution/target_architecture.md](architecture/evolution/target_architecture.md) | Target (post-Phase 2) architecture and evolution roadmap |
| [evolution/phase_1_5_migration.md](architecture/evolution/phase_1_5_migration.md) | Phase 1 → 1.5 migration guide (adding non-K8s cloud targets) |

### Architecture Layers

Detailed design for each layer of the hexagonal architecture:

| Document | Description |
|---|---|
| [architecture/layers/detection_layer.md](architecture/layers/detection_layer.md) | Anomaly detection algorithms, baseline computation, thresholds |
| [architecture/layers/intelligence_layer.md](architecture/layers/intelligence_layer.md) | LLM-backed root cause analysis and remediation planning |
| [architecture/layers/observability_layer.md](architecture/layers/observability_layer.md) | Metrics, logs, trace ingestion from OTel, Prometheus, Loki, Jaeger |
| [architecture/layers/action_layer.md](architecture/layers/action_layer.md) | Remediation action execution, dry-run mode, audit trail |
| [architecture/layers/operator_layer.md](architecture/layers/operator_layer.md) | Cloud operator adapters: Kubernetes, AWS, Azure |
| [architecture/layers/orchestration_layer.md](architecture/layers/orchestration_layer.md) | Multi-agent coordination, distributed locking, cooling-off protocol |

---

## 3. Operations

Day-to-day operational procedures, SLOs, and incident playbooks.

| **Runbooks** | Description |
|---|---|
| [runbooks/deployment.md](operations/runbooks/deployment.md) | Step-by-step deployment procedure for production |
| [runbooks/incident_response.md](operations/runbooks/incident_response.md) | Incident response playbook for the agent itself |
| [runbooks/kill_switch.md](operations/runbooks/kill_switch.md) | Emergency kill switch activation and recovery |
| [runbooks/phase_management.md](operations/runbooks/phase_management.md) | Procedures for graduating the agent across phases |
| [runbooks/agent_failure_runbook.md](operations/runbooks/agent_failure_runbook.md) | Runbook for responding to agent crash or stuck state |

| **Live Demos** | Description |
|---|---|
| [localstack_live_incident_demo.md](operations/localstack_live_incident_demo.md) | End-to-end LocalStack incident response demo: Lambda crash → CloudWatch → SNS → Agent diagnosis |

| **Operational Metrics** | Description |
|---|---|
| [slos_and_error_budgets.md](operations/slos_and_error_budgets.md) | Service Level Objectives, error budgets, burn rate alerts |
| [ci_cd_pipeline.md](operations/ci_cd_pipeline.md) | CI/CD pipeline design, stages, and quality gates |
| [operational_readiness.md](operations/operational_readiness.md) | Production readiness checklist |
| [external_dependencies.md](operations/external_dependencies.md) | External deps: Docker, LocalStack, LLM keys, ChromaDB |
| [graduation_criteria.md](operations/graduation_criteria.md) | Criteria for graduating from each phase to the next |

---

## 4. Project & Standards

Project management, core onboarding, and engineering standards.

| **Core Onboarding** | Description |
|---|---|
| [project/onboarding.md](project/onboarding.md) | New engineer onboarding guide — environment setup, key concepts |
| [project/roadmap.md](project/roadmap.md) | Feature roadmap and phase planning |
| [project/CHANGELOG.md](project/CHANGELOG.md) | Chronological change log for major milestones |
| [project/glossary.md](project/glossary.md) | Terminology and acronym definitions |

| **Project Standards** | Description |
|---|---|
| [standards/engineering_standards.md](project/standards/engineering_standards.md) | Coding standards, test pyramid, style guide, review process |
| [standards/FAANG_Documentation_Standards.md](project/standards/FAANG_Documentation_Standards.md) | Documentation quality standards applied to this project |

### Architectural Decision Records (ADRs)

| Document | Decision |
|---|---|
| [project/ADRs/000-template.md](project/ADRs/000-template.md) | ADR template |
| [project/ADRs/001-hexagonal-architecture.md](project/ADRs/001-hexagonal-architecture.md) | ADR-001: Adopt Hexagonal Architecture |
| [project/ADRs/002-pydantic-over-dataclasses.md](project/ADRs/002-pydantic-over-dataclasses.md) | ADR-002: Use Pydantic over plain dataclasses |

---

## 5. Security

Threat model, guardrails, and safety controls.

| Document | Description |
|---|---|
| [security/threat_model.md](security/threat_model.md) | STRIDE threat model: attack surfaces, mitigations |
| [security/features_and_safety.md](security/features_and_safety.md) | Safety features: dry-run mode, guardrails, human override |
| [security/guardrails_configuration.md](security/guardrails_configuration.md) | Configuration reference for all safety guardrails |

---

## 6. Testing

Test strategy, infrastructure instructions, and live validation.

| Document | Description |
|---|---|
| [testing/testing_strategy.md](testing/testing_strategy.md) | End-to-end testing strategy, pyramid rationale, environment matrix |
| [testing/localstack_pro_guide.md](testing/localstack_pro_guide.md) | Guide for using LocalStack Pro with Testcontainers to mock AWS services |
| [testing/e2e_testing_plan.md](testing/e2e_testing_plan.md) | E2E test plan with scenarios, expected outcomes, success criteria |
| [testing/live_validation_test_cases.md](testing/live_validation_test_cases.md) | Live cluster validation test cases for Phase 1.5 acceptance |
| [testing/bugs.md](testing/bugs.md) | Bug tracking log — all 6 bugs from Phase 1.5 resolved |

---

## 7. Reports & Archives

Point-in-time progress reports, test findings, and document reviews.

| Document | Description |
|---|---|
| [reports/phase_1_5_test_findings.md](reports/phase_1_5_test_findings.md) | Full test findings report: 283/284 tests (99.6%), all categories graded |
| [reports/phase_1_status.md](reports/phase_1_status.md) | Phase 1 completion status report |
| [reports/improvement_areas_phase_1_5.md](reports/improvement_areas_phase_1_5.md) | Identified improvement areas after Phase 1.5 delivery |
| [reports/implementation_progress.md](reports/implementation_progress.md) | Detailed implementation progress against acceptance criteria |
| [reports/documentation_review.md](reports/documentation_review.md) | Review of documentation gaps and improvement plan |

---

## Document Conventions

All documents in this repository follow the standards defined in [FAANG_Documentation_Standards.md](project/standards/FAANG_Documentation_Standards.md):

- **Headers:** `#` (H1) for document title, `##` (H2) for major sections
- **Status badges:** `✅ PASS`, `❌ FAIL`, `⚠️ PARTIAL`, `🔵 KNOWN LIMITATION`
- **Code blocks:** Always specify language for syntax highlighting
- **Links:** Use relative paths from the document's location
- **Dates:** ISO 8601 format (`YYYY-MM-DD`)
- **Tables:** Preferred over bullet lists for structured comparisons

---

## Related Resources

| Resource | Location |
|---|---|
| Project root README | [README.md](../README.md) |
| Contribution guidelines | [CONTRIBUTING.md](../CONTRIBUTING.md) |
| Multi-agent ecosystem | [AGENTS.md](../AGENTS.md) |
| Agent configuration | [config/agent.yaml](../config/agent.yaml) |
| Kubernetes infra manifests | [infra/k8s/](../infra/k8s/) |
| Phase specs and proposals | [openspec/](../openspec/) |
| Phase 1 data foundation | [phases/phase-1-data-foundation/](../phases/phase-1-data-foundation/) |

---

## Developer Scripts

| Script | Purpose |
|---|---|
| `scripts/run.sh` | Unified run script: server, test, lint, setup |
| `scripts/setup_deps.sh` | Start/stop Docker-based development dependencies |
| `docker-compose.deps.yml` | Docker Compose for LocalStack, Prometheus, Jaeger |
| `scripts/localstack_bridge.py` | SNS → AnomalyAlert incident bridge for LocalStack live demo |
| `scripts/mock_lambda.py` | Vulnerable Lambda handler for LocalStack live demo |
| `scripts/live_demo_localstack_incident.py` | Single-script orchestrator: runs all 10 demo phases end-to-end |
| `.env.example` | Environment variable template (copy to `.env`) |
