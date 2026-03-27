# Tasks: Remediation Engine

**Input**: Design documents from `openspec/changes/autonomous-sre-agent/specs/remediation-engine/`  
**Prerequisites**: plan.md (✅), spec.md (✅), remediation_models.md (✅), safety-guardrails/spec.md (✅)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and package structure

- [ ] T001 Create `src/sre_agent/domain/remediation/__init__.py` with package docstring
- [ ] T002 [P] Create `src/sre_agent/domain/safety/__init__.py` with package docstring
- [ ] T003 [P] Create `src/sre_agent/adapters/kubernetes/__init__.py` with package docstring
- [ ] T004 [P] Create `tests/unit/domain/remediation/` directory structure with `conftest.py`
- [ ] T005 [P] Create `tests/unit/domain/safety/` directory structure with `conftest.py`

**Checkpoint**: Package directories established. Imports resolve. `pytest --collect-only` discovers test directories.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core domain models and port ABCs that ALL remediation components depend on

**⚠️ CRITICAL**: No engine/safety work can begin until this phase is complete

- [ ] T006 [MODELS] Implement `RemediationStrategy` enum in `src/sre_agent/domain/remediation/models.py`
  - All 7 values: `RESTART`, `SCALE_UP`, `SCALE_DOWN`, `GITOPS_REVERT`, `CONFIG_CHANGE`, `CERTIFICATE_ROTATION`, `LOG_TRUNCATION`

- [ ] T007 [P] [MODELS] Implement `ApprovalState`, `ActionStatus`, `VerificationStatus` enums in `src/sre_agent/domain/remediation/models.py`

- [ ] T008 [P] [MODELS] Implement `SafetyConstraints` frozen dataclass in `src/sre_agent/domain/remediation/models.py`
  - Fields: `max_blast_radius_percentage`, `canary_percentage`, `canary_validation_window_seconds`, `max_replicas`, `cooldown_ttl_seconds`, `requires_human_approval`

- [ ] T009 [MODELS] Implement `BlastRadiusEstimate` frozen dataclass in `src/sre_agent/domain/remediation/models.py`
  - Fields: `affected_pods_count`, `affected_pods_percentage`, `dependent_services`, `estimated_user_impact`

- [ ] T010 [MODELS] Implement `RemediationAction` dataclass in `src/sre_agent/domain/remediation/models.py`
  - All fields from `remediation_models.md` §3 including `executed_at`, `verified_at`, `rollback_executed_at`, `execution_duration_ms`, `lock_fencing_token`
  
- [ ] T011 [MODELS] Implement `RemediationPlan` dataclass in `src/sre_agent/domain/remediation/models.py`
  - Fields from `remediation_models.md` §2: `plan_id`, `diagnosis_id`, `incident_id`, `strategy`, `target_resource`, `compute_mechanism`, `provider`, `approval_state`, `safety_constraints`, `actions`, `created_at`, `approved_at`, `approved_by`

- [ ] T012 [MODELS] Implement `RemediationResult` frozen dataclass in `src/sre_agent/domain/remediation/models.py`
  - Fields: `success`, `metrics_before`, `metrics_after`, `verification_status`, `rollback_triggered`, `error_message`, `execution_duration_ms`

- [ ] T013 [PORT] Implement `RemediationPort` ABC in `src/sre_agent/ports/remediation.py`
  - Methods: `create_plan(diagnosis) -> RemediationPlan`, `execute_action(action) -> RemediationResult`, `verify_outcome(action) -> VerificationStatus`, `rollback_action(action) -> RemediationResult`
  - Follow `CloudOperatorPort` pattern: abstract methods, Google-style docstrings, type annotations

- [ ] T014 [TEST] Unit tests for all models in `tests/unit/domain/remediation/test_models.py`
  - Validate enum values, dataclass field defaults, frozen constraints, Pydantic-like validation
  - ≥12 test functions

**Checkpoint**: All domain models import correctly. `RemediationPort` ABC is defined. Model unit tests pass. `mypy --strict` passes on new files.

---

## Phase 3: User Story 1 — Remediation Planning (Priority: P1) 🎯 MVP

**Goal**: Given a `Diagnosis`, produce a safe `RemediationPlan` with the correct strategy.

**Independent Test**: Create a `Diagnosis` for an OOM kill → verify plan has `RESTART` strategy, correct target, and safety constraints.

### Tests for US1

- [ ] T015 [P] [US1] Unit tests for strategy selection in `tests/unit/domain/remediation/test_planner.py`
  - `test_oom_kill_selects_restart_strategy`
  - `test_traffic_spike_selects_scale_up_strategy`
  - `test_deployment_regression_selects_gitops_revert_strategy`
  - `test_cert_expiry_selects_certificate_rotation_strategy`
  - `test_disk_exhaustion_selects_log_truncation_strategy`
  - `test_unknown_anomaly_type_returns_none_and_escalates`
  - ≥8 test functions

### Implementation for US1

- [ ] T016 [US1] Implement strategy selection matrix in `src/sre_agent/domain/remediation/strategies.py`
  - `ANOMALY_STRATEGY_MAP: dict[AnomalyType, RemediationStrategy]` — deterministic mapping per `remediation_models.md` §8
  - `select_strategy(diagnosis: Diagnosis) -> RemediationStrategy | None`

- [ ] T017 [US1] Implement `RemediationPlanner` in `src/sre_agent/domain/remediation/planner.py`
  - Constructor injection: `event_bus: EventBus`
  - `create_plan(diagnosis: Diagnosis, service_graph: ServiceGraph) -> RemediationPlan`
  - Computes `BlastRadiusEstimate` using `ServiceGraph.get_transitive_downstream()`
  - Sets `requires_human_approval` based on severity + confidence routing logic
  - Emits `REMEDIATION_PLANNED` event

- [ ] T018 [US1] Add structured logging for planner operations (structlog)
  - Log events: `remediation_plan_created`, `strategy_selected`, `blast_radius_computed`

**Checkpoint**: `RemediationPlanner.create_plan()` returns correct plans for all 5 incident types. All US1 tests pass.

---

## Phase 4: User Story 2 — Safety Guardrails (Priority: P1)

**Goal**: Validate a `RemediationPlan` against all safety constraints before execution.

**Independent Test**: Create a plan that exceeds blast radius → verify guardrails reject it.

### Tests for US2

- [ ] T019 [P] [US2] Unit tests for blast radius in `tests/unit/domain/safety/test_blast_radius.py`
  - `test_within_limit_allows_action`
  - `test_exceeding_limit_denies_action`
  - `test_scaling_within_2x_limit_allows`
  - `test_scaling_exceeding_2x_limit_denies`
  - ≥6 test functions

- [ ] T020 [P] [US2] Unit tests for kill switch in `tests/unit/domain/safety/test_kill_switch.py`
  - `test_activation_halts_all_actions`
  - `test_deactivation_resumes_actions`
  - `test_activation_emits_event`
  - `test_queued_actions_cancelled_on_activation`
  - ≥5 test functions

- [ ] T021 [P] [US2] Unit tests for cooldown in `tests/unit/domain/safety/test_cooldown.py`
  - `test_k8s_cooldown_key_format`
  - `test_non_k8s_cooldown_key_format`
  - `test_cooldown_denies_lock_within_ttl`
  - `test_higher_priority_bypasses_cooldown`
  - ≥5 test functions

- [ ] T022 [P] [US2] Unit tests for phase gate in `tests/unit/domain/safety/test_phase_gate.py`
  - `test_all_criteria_met_allows_graduation`
  - `test_accuracy_below_threshold_denies`
  - `test_destructive_fp_denies`
  - ≥4 test functions

### Implementation for US2

- [ ] T023 [US2] Implement `BlastRadiusCalculator` in `src/sre_agent/domain/safety/blast_radius.py`
  - `validate(plan: RemediationPlan) -> tuple[bool, str | None]`
  - Per-strategy limits from `incident_taxonomy.md`: restart ≤20%, scale ≤2x, single deployment only

- [ ] T024 [P] [US2] Implement `KillSwitch` in `src/sre_agent/domain/safety/kill_switch.py`
  - `activate(operator_id: str, reason: str) -> None` — emits `KILL_SWITCH_ACTIVATED`
  - `deactivate(operator_id: str) -> None` — emits `KILL_SWITCH_DEACTIVATED`
  - `is_active -> bool`
  - Thread-safe implementation using `asyncio.Event` or equivalent

- [ ] T025 [P] [US2] Implement `CooldownEnforcer` in `src/sre_agent/domain/safety/cooldown.py`
  - `record_action(resource_id: str, compute_mechanism: ComputeMechanism, provider: str, namespace: str) -> None`
  - `is_in_cooldown(resource_id: str, ...) -> tuple[bool, int]` — returns (in_cooldown, remaining_seconds)
  - Key format: K8s `cooldown:{ns}:{type}:{name}`, non-K8s `cooldown:{provider}:{mechanism}:{resource_id}`

- [ ] T026 [P] [US2] Implement `PhaseGate` in `src/sre_agent/domain/safety/phase_gate.py`
  - `evaluate_graduation(current_phase, target_phase, metrics: PhaseMetrics) -> tuple[bool, list[str]]`
  - Criteria from spec: accuracy ≥90%, zero destructive FPs, ≥95% Sev 3-4 automation, integration coverage ≥30%, 7-day soak clean

- [ ] T027 [US2] Implement `GuardrailOrchestrator` in `src/sre_agent/domain/safety/guardrails.py`
  - `validate(plan: RemediationPlan) -> GuardrailResult`
  - Checks: kill switch → blast radius → canary sizing → cooldown → confidence gating
  - Emits appropriate events on denial (`BLAST_RADIUS_EXCEEDED`, `COOLDOWN_ENFORCED`)

**Checkpoint**: All safety components validate independently. Guardrail orchestrator correctly blocks unsafe plans and passes safe ones. All US2 tests pass.

---

## Phase 5: User Story 3 — Remediation Execution (Priority: P1)

**Goal**: Execute a validated `RemediationPlan` via the correct cloud operator, with canary pattern.

**Independent Test**: Mock `CloudOperatorPort` → execute restart plan → verify canary then full rollout.

### Tests for US3

- [ ] T028 [P] [US3] Unit tests for engine in `tests/unit/domain/remediation/test_engine.py`
  - `test_engine_routes_k8s_to_kubernetes_operator`
  - `test_engine_routes_ecs_to_ecs_operator`
  - `test_engine_executes_canary_then_rollout`
  - `test_engine_halts_on_canary_failure`
  - `test_engine_acquires_lock_before_execution`
  - `test_engine_emits_started_and_completed_events`
  - `test_engine_handles_circuit_breaker_open`
  - `test_engine_retries_on_timeout`
  - `test_engine_stops_on_kill_switch`
  - ≥12 test functions

### Implementation for US3

- [ ] T029 [US3] Implement `RemediationEngine` in `src/sre_agent/domain/remediation/engine.py`
  - Constructor injection: `cloud_operator_registry`, `event_bus`, `event_store`, `guardrails`, `kill_switch`
  - `execute(plan: RemediationPlan) -> RemediationResult`
  - Workflow: validate guardrails → acquire lock → execute canary → verify canary → execute remaining batches → verify all → release lock → write cooldown
  - Emits `REMEDIATION_STARTED`, `REMEDIATION_COMPLETED`, `REMEDIATION_FAILED`, `REMEDIATION_ROLLED_BACK` events

- [ ] T030 [US3] Implement canary batch calculation in `RemediationEngine`
  - `_calculate_batches(total: int, canary_pct: float) -> list[list[str]]`
  - Formula: `batch_0 = max(1, ceil(total * canary_pct / 100))`, remainder in subsequent batches

- [ ] T031 [US3] Add error handling with retry and circuit breaker integration
  - Timeout handling: 3 retries with exponential backoff (1s, 2s, 4s)
  - Circuit breaker check before execution
  - Partial failure handling: halt remaining batches, report succeeded/failed

**Checkpoint**: Engine executes full canary→rollout cycle with mocked operator. Lock lifecycle correct. Events emitted. Error paths tested. All US3 tests pass.

---

## Phase 6: User Story 4 — Post-Remediation Verification (Priority: P2)

**Goal**: After execution, monitor metrics to confirm recovery or trigger rollback.

**Independent Test**: Execute action → inject normalized metrics → verify resolution. Execute action → inject degraded metrics → verify rollback triggered.

### Tests for US4

- [ ] T032 [P] [US4] Unit tests for verification in `tests/unit/domain/remediation/test_verification.py`
  - `test_metrics_normalized_marks_resolved`
  - `test_metrics_degraded_triggers_rollback`
  - `test_verification_timeout_triggers_escalation`
  - `test_verification_emits_completed_event`
  - ≥6 test functions

### Implementation for US4

- [ ] T033 [US4] Implement `RemediationVerifier` in `src/sre_agent/domain/remediation/verification.py`
  - Constructor injection: `telemetry_port: TelemetryProvider`, `event_bus: EventBus`
  - `verify(action: RemediationAction, baseline: BaselineData, window_seconds: int = 300) -> VerificationStatus`
  - Checks: latency p99, error rate, throughput — all within 1σ of baseline
  - Emits `REMEDIATION_COMPLETED` or `REMEDIATION_ROLLED_BACK` event

**Checkpoint**: Verifier correctly classifies metric recovery. Rollback path triggers when metrics degrade.

---

## Phase 7: User Story 5 — Kubernetes Adapter (Priority: P2)

**Goal**: Implement `CloudOperatorPort` for Kubernetes, the primary remediation target.

### Tests for US5

- [ ] T034 [P] [US5] Unit tests for K8s operator in `tests/unit/adapters/test_kubernetes_operator.py`
  - `test_restart_compute_unit_calls_rollout_restart`
  - `test_scale_capacity_calls_kubectl_scale`
  - `test_unsupported_action_raises`
  - ≥5 test functions

### Implementation for US5

- [ ] T035 [US5] Implement `KubernetesOperator` in `src/sre_agent/adapters/kubernetes/operator.py`
  - Implements `CloudOperatorPort` ABC
  - `restart_compute_unit()`: `kubectl rollout restart deployment/{name} -n {namespace}`
  - `scale_capacity()`: `kubectl scale deployment/{name} --replicas={count} -n {namespace}`
  - `health_check()`: `kubectl cluster-info` connectivity test
  - Uses `kubernetes` Python client library

**Checkpoint**: Kubernetes adapter implements `CloudOperatorPort`. Restart and scale operations work with mocked K8s client.

---

## Phase 8: User Story 6 — Severity Routing & HITL Integration (Priority: P2)

**Goal**: Route Sev 1-2 to human approval, Sev 3-4 to autonomous execution.

### Tests for US6

- [ ] T036 [P] [US6] Unit tests for severity routing in `tests/unit/domain/remediation/test_engine.py` (extend)
  - `test_sev3_autonomous_executes_immediately`
  - `test_sev4_autonomous_executes_immediately`
  - `test_sev1_requires_human_approval`
  - `test_sev2_requires_human_approval`
  - ≥4 test functions

### Implementation for US6

- [ ] T037 [US6] Add severity routing logic to `RemediationEngine.execute()`
  - If `plan.safety_constraints.requires_human_approval`: emit `REMEDIATION_PLANNED` + notification, wait for approval
  - Else: proceed to autonomous execution

- [ ] T038 [US6] Add approval timeout handling
  - Default HITL timeout: 30 minutes
  - On timeout: `ApprovalState.EXPIRED`, escalate with full context

**Checkpoint**: Severity routing correctly gates Sev 1-2.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Integration, documentation, and quality improvements

- [ ] T039 [P] Update `src/sre_agent/adapters/intelligence_bootstrap.py` to wire remediation components
- [ ] T040 [P] Create `src/sre_agent/api/rest/remediation_router.py` — FastAPI endpoints:
  - `POST /api/v1/remediation/execute` — trigger remediation for an incident
  - `POST /api/v1/kill-switch` — activate/deactivate kill switch
  - `GET /api/v1/remediation/{plan_id}/status` — check plan status
- [ ] T041 [P] Update `src/sre_agent/ports/__init__.py` to export `RemediationPort`
- [ ] T042 Integration test in `tests/integration/test_remediation_e2e.py`
  - Full pipeline: Diagnosis → Planner → Guardrails → Engine → Verification
  - Uses mocked `CloudOperatorPort` and `InMemoryEventStore`
- [ ] T043 Update `docs/architecture/architecture.md` — mark Action Layer as `[✅ IMPLEMENTED]`
- [ ] T044 [P] Update `docs/architecture/models/data_model.md` — add `RemediationPlan`, `RemediationResult` models
- [ ] T045 [P] Run `mypy --strict` on all new files
- [ ] T046 Run `black` and `isort` on all new files
- [ ] T047 Code cleanup and docstring review
- [ ] T048 Update `CHANGELOG.md` with remediation engine entry

**Checkpoint**: All new code passes `mypy --strict`, `black`, `isort`. Integration test validates full pipeline. API endpoints functional.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — BLOCKS all user stories
- **Phase 3 (Planning)**: Depends on Phase 2
- **Phase 4 (Safety)**: Depends on Phase 2, can run in PARALLEL with Phase 3
- **Phase 5 (Execution)**: Depends on Phase 3 + Phase 4
- **Phase 6 (Verification)**: Depends on Phase 5
- **Phase 7 (K8s Adapter)**: Depends on Phase 2, can run in PARALLEL with Phase 3–6
- **Phase 8 (HITL Routing)**: Depends on Phase 5
- **Phase 9 (Polish)**: Depends on all previous phases

### Parallel Opportunities

```
Phase 1 (Setup)
    │
Phase 2 (Models + Port)
    │
    ├── Phase 3 (Planner)     ← Can run in parallel
    ├── Phase 4 (Safety)      ← Can run in parallel  
    └── Phase 7 (K8s Adapter) ← Can run in parallel
         │
    Phase 5 (Engine) ← Needs Phase 3 + 4
         │
    ├── Phase 6 (Verification)
    └── Phase 8 (HITL Routing)
         │
    Phase 9 (Polish)
```

### Within Each Phase

- Tests MUST be written and FAIL before implementation (TDD)
- Models before services
- Services before endpoints
- Complete checkpoint before moving to next phase
- Commit after each task or logical group

---

## Summary

| Metric | Value |
|---|---|
| Total tasks | 48 |
| New source files | 14 |
| New test files | 11 |
| Estimated new LOC (source) | ~2,500 |
| Estimated new LOC (tests) | ~1,800 |
| Estimated test functions | ~85 |
