# Autonomous SRE Agent — Documentation Index

> **Version:** Phase 2 (Intelligence Layer)  
> **Last Updated:** March 12, 2026  
> **Maintainer:** SRE Agent Engineering Team

This index is the canonical entry point for all project documentation. Every document in the `docs/` tree is listed here with its purpose and audience. 

**Status:** Documentation reorganized per [documentation_management_plan.md](reports/documentation_management_plan.md) — duplicates removed, DRAFT docs scheduled for promotion, point-in-time reports archived.

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
| [evolution/roadmap.md](architecture/evolution/roadmap.md) | Multi-cloud target architecture and phased evolution path |

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
| [live_demo_guide.md](operations/live_demo_guide.md) | Landing page for end-to-end live incident response demonstrations |
| [localstack_live_incident_demo.md](operations/localstack_live_incident_demo.md) | LocalStack Lambda incident → SNS → agent diagnosis (Demo 7) |

| **Operational Metrics** | Description |
|---|---|
| [slos_and_error_budgets.md](operations/slos_and_error_budgets.md) | Service Level Objectives, error budgets, burn rate alerts |
| [external_dependencies.md](operations/external_dependencies.md) | External deps: Docker, LocalStack, LLM keys, ChromaDB |
| [aws_data_collection_improvements.md](operations/aws_data_collection_improvements.md) | AWS incident data collection — improvement areas and implementation guide |

---

## 4. Project & Standards

Project management, core onboarding, and engineering standards.

| **Core Onboarding** | Description |
|---|---|
| [project/onboarding.md](project/onboarding.md) | New engineer onboarding guide — environment setup, key concepts |
| [project/roadmap.md](project/roadmap.md) | Feature roadmap and phase planning |
| [project/glossary.md](project/glossary.md) | Terminology and acronym definitions |

| **Project Standards** | Description |
|---|---|
| [standards/engineering_standards.md](project/standards/engineering_standards.md) | Coding standards, test pyramid, style guide, review process |
| [standards/FAANG_Documentation_Standards.md](project/standards/FAANG_Documentation_Standards.md) | Documentation quality standards applied to this project |

### Architectural Decision Records (ADRs)

| Document | Decision |
|---|---|
| [project/ADRs/001-hexagonal-architecture.md](project/ADRs/001-hexagonal-architecture.md) | ADR-001: Adopt Hexagonal Architecture |
| [project/ADRs/002-pydantic-over-dataclasses.md](project/ADRs/002-pydantic-over-dataclasses.md) | ADR-002: Use Pydantic over plain dataclasses |

*See [project/ADRs/_template.md](project/ADRs/_template.md) for the ADR template.*

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
| [testing/live_validation_test_cases.md](testing/live_validation_test_cases.md) | Live cluster validation test cases for Phase 1.5 acceptance |
| [testing/bugs.md](testing/bugs.md) | Bug tracking log — all 6 bugs from Phase 1.5 resolved |

---

## 7. Reports & Analysis

Documentation reviews, test findings, implementation verifications, and quality analyses.

| **Active Reports** | Description |
|---|---|
| [reports/documentation_management_plan.md](reports/documentation_management_plan.md) | Complete evaluation of all 145 markdown files with concrete management plan and 6-week sprint schedule |
| [reports/gap_closure_report.md](reports/gap_closure_report.md) | Phase 2 implementation gap closure report for Engineering Standards Compliance |
| [reports/live_demo_evaluation.md](reports/live_demo_evaluation.md) | Post-run analysis of Phase 2 Intelligence Layer live demonstration |
| [reports/phase_1_5_test_findings.md](reports/phase_1_5_test_findings.md) | Full test findings report: 283/284 tests (99.6%), all categories graded |
| [reports/observability_improvement_areas.md](reports/observability_improvement_areas.md) | Identified observability improvement areas for future phases |
| [reports/aws_data_collection_review.md](reports/aws_data_collection_review.md) | Current state review of AWS incident data collection (Phase 2.3 pre-work) |
| [reports/phase_2_3_verification_report.md](reports/phase_2_3_verification_report.md) | Phase 2.3 verification report: AWS adapters, enrichment layer, and polling agent |
| [reports/phase_2_2_token_optimization_report.md](reports/phase_2_2_token_optimization_report.md) | Phase 2.2 LLM token optimization strategy, execution, and implementation plan |
| [reports/ai_agent_architecture_research.md](reports/ai_agent_architecture_research.md) | Research report on AI agent architecture patterns and production best practices |
| [reports/alignment_report.md](reports/alignment_report.md) | Alignment report: research vs. project implementation |

| **Archived Reports** | Purpose |
|---|---|
| [reports/archive/](reports/archive/) | Historical planning artifacts, superseded analyses, and point-in-time snapshots from earlier phases |

---

## Document Conventions

All documents in this repository follow the standards defined in [project/standards/FAANG_Documentation_Standards.md](project/standards/FAANG_Documentation_Standards.md):

- **Headers:** `#` (H1) for document title, `##` (H2) for major sections
- **Status badges:** `✅ PASS`, `❌ FAIL`, `⚠️ PARTIAL`, `🔵 KNOWN LIMITATION`
- **Code blocks:** Always specify language for syntax highlighting
- **Links:** Use relative paths from the document's location
- **Dates:** ISO 8601 format (`YYYY-MM-DD`)
- **Tables:** Preferred over bullet lists for structured comparisons
- **Status field:** All documents must have `Status: APPROVED` after merging. Use `Status: DRAFT` only during active development.

---

## Related Resources

| Resource | Location |
|---|---|
| Project changelog | [../CHANGELOG.md](../CHANGELOG.md) |
| Project root README | [../README.md](../README.md) |
| Contribution guidelines | [../CONTRIBUTING.md](../CONTRIBUTING.md) |
| Multi-agent ecosystem | [../AGENTS.md](../AGENTS.md) |
| Agent configuration | [../config/agent.yaml](../config/agent.yaml) |
| Kubernetes infra manifests | [../infra/k8s/](../infra/k8s/) |
| Phase specs and proposals | [../openspec/](../openspec/) |

---

## Developer Scripts

| Script | Purpose |
|---|---|
| `scripts/run.sh` | Unified run script: server, test, lint, setup |
| `scripts/setup_deps.sh` | Start/stop Docker-based development dependencies |
| `docker-compose.deps.yml` | Docker Compose for LocalStack, Prometheus, Jaeger |
| `scripts/localstack_bridge.py` | SNS → AnomalyAlert incident bridge for LocalStack live demos |
| `scripts/mock_lambda.py` | Vulnerable Lambda handler for LocalStack live demo |
| `scripts/live_demo_localstack_incident.py` | Demo 7: 10-phase Lambda incident cascade (LocalStack) |
| `scripts/live_demo_ecs_multi_service.py` | Demo 8: 14-phase ECS multi-service cascade with LLM diagnosis |
| `.env.example` | Environment variable template (copy to `.env`) |
