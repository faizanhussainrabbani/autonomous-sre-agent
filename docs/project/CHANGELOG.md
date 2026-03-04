# Changelog

All notable changes to the Autonomous SRE Agent will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added (2026-03-04 — Integration Testing & Docs Restructure)
- **LocalStack Pro integration:** Activated Pro license (`LOCALSTACK_AUTH_TOKEN`) enabling full AWS service emulation (EC2 ASG, ECS, Lambda) in integration tests.
- **`docs/testing/localstack_pro_guide.md`:** Comprehensive setup and authentication guide for local AWS mocking via Testcontainers.
- **`docs/README.md`:** New top-level documentation navigation index linking all 47 documents across 6 sections
- **`docs/reports/phase_1_5_test_findings.md`:** Comprehensive Phase 1.5 test findings report (99.6% pass rate, all categories graded)
- **`docs/testing/live_validation_test_cases.md`:** Live cluster validation test cases for Phase 1.5 acceptance
- **`docs/testing/e2e_testing_plan.md`:** E2E test plan with scenarios and success criteria

### Changed (2026-03-04)
- **Integration test suite:** 6/6 PASS (was 4/6) — EC2 ASG, ECS, Lambda now pass with LocalStack Pro
- **`tests/integration/test_aws_operators_integration.py`:** Switched to `localstack/localstack-pro:latest` image; added `_get_localstack_auth_token()` helper reading from `~/.localstack/auth.json`
- **`docs/testing/bugs.md`:** Updated header from 184/184 tests → 283/284; BUG-001 coverage updated to 88.4%
- **Docs restructured:**
  - `docs/operations/testing_strategy.md` → `docs/testing/testing_strategy.md`
  - `docs/operations/test_infrastructure.md` → `docs/testing/test_infrastructure.md`
  - `docs/architecture/standards/FAANG_Documentation_Standards.md` → `docs/project/standards/FAANG_Documentation_Standards.md`
  - `docs/project/ImprovementAreasAfterPhase1_5.md` → `docs/project/../reports/improvement_areas_phase_1_5.md` (snake_case)
- **Cross-references updated** in `documentation_improvement_review.md`, `FAANG_Documentation_Standards.md`, `engineering_standards.md`

### Fixed (2026-03-04)
- **DEF-002 (AWS integration tests):** EC2 ASG and ECS tests were failing due to LocalStack Community tier — resolved by activating LocalStack Pro

### Infrastructure (2026-03-04)
- k3d cluster `sre-local` stopped (all K8s tests completed and passed: 8/8)
- LocalStack Pro Docker image pre-pulled: `localstack/localstack-pro:latest`

---

### Added (Prior — Documentation Sprint)
- Documentation improvement plan execution (Sprint 1-4)
- ADR (Architectural Decision Record) template and initial records
- Standardized version/status headers across all documentation
- Implementation references in OpenSpec spec files

### Changed
- Consolidated 12 architecture layer documents into 6 canonical docs
- Updated README.md with better navigation and quickstart guide
- Expanded CONTRIBUTING.md with hexagonal architecture and coverage rules
- Standardized Phase terminology across glossary and all docs
- Updated `data_model.md` to reflect Pydantic BaseModel usage
- Updated `extensibility.md` with correct port file paths
- Updated `architecture.md` with implementation status per layer
- Updated `features_and_safety.md` with `[PLANNED]` markers on unimplemented guardrails
- Updated `threat_model.md` with `[PLANNED]` markers on unimplemented mitigations
- Updated `dependency_graph.md` to replace networkx references with canonical Pydantic models
- Fixed runbook paths in `operational_readiness.md`
- Aligned EventType references in `slos_and_error_budgets.md`
- Marked CI/CD pipeline sections as `[PLANNED]`
- Marked unimplemented API endpoints as `[PLANNED]` in `api_contracts.md`

### Removed
- Empty `docs/mermaid/`, `docs/specs/`, and `docs/archive/` directories
- Redundant `_layer_details.md` files (merged into parent layer docs)

---

## [1.5.0] — 2025-01-10

### Added
- Phase 1.5: Compute Agnosticism
  - AWS ECS operator adapter (`adapters/cloud/aws/ecs_operator.py`)
  - AWS EC2/ASG operator adapter (`adapters/cloud/aws/ec2_asg_operator.py`)
  - AWS Lambda operator adapter (`adapters/cloud/aws/lambda_operator.py`)
  - Azure App Service operator adapter (`adapters/cloud/azure/app_service_operator.py`)
  - Azure Functions operator adapter (`adapters/cloud/azure/functions_operator.py`)
  - New Relic NerdGraph telemetry adapter
  - Cloud operator registry for multi-provider resolution
  - Retry and circuit breaker patterns for cloud adapters
  - Serverless detection rules (cold-start suppression)

---

## [1.0.0] — 2024-12-01

### Added
- Phase 1: Data Foundation
  - Canonical data model (Pydantic BaseModel): `CanonicalMetric`, `CanonicalTrace`, `CanonicalLogEntry`
  - Telemetry port abstraction (`TelemetryPort`)
  - Prometheus, Jaeger, Loki adapters via OTel
  - `BaselineService` for rolling statistical baselines
  - `AnomalyDetector` supporting 6 anomaly types
  - `AlertCorrelationEngine` with dependency-graph-aware grouping
  - `PipelineMonitor` for collector failure detection
  - Domain event bus (`InMemoryEventBus`, `InMemoryEventStore`)
  - eBPF adapter for kernel-level signal ingestion
  - Hexagonal architecture (Ports & Adapters pattern)
  - 177 unit tests with 85% coverage threshold
