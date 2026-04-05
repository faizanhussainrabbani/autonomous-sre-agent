---
status: DRAFT
version: 1.0.0
date: 2026-04-03
scope: scripts/demo/
---

# Implementation Plan: Demo Hardening & Phase 3 Remediation Demo

## 1. Scope and Objectives

This plan covers three sequential work items identified in the live demo critical review:

| # | Work Item | Priority | Estimated Effort |
|---|-----------|----------|-----------------|
| WI-1 | Add SIGINT handlers to demos managing subprocesses | P0 | 0.5 day |
| WI-2 | Extract shared agent lifecycle to `_demo_utils.py` | P1 | 0.5 day |
| WI-3 | Build Phase 3 end-to-end remediation demo | P0 | 1 day |

**Objective:** Eliminate orphan-process risk, reduce ~400 lines of duplication, and fill the largest architectural demo gap (Phase 3 autonomous remediation).

---

## 2. Work Item 1: SIGINT Handlers

### 2.1 Problem

8 demos start subprocesses (uvicorn) but have no `signal.signal(signal.SIGINT, ...)` registration. Ctrl+C during demo execution leaves orphan uvicorn processes.

### 2.2 Affected Files

| Demo File | Subprocess Type | Current Cleanup |
|-----------|----------------|----------------|
| `live_demo_20_unknown_incident_safety_net.py` | uvicorn (agent) | try/finally only |
| `live_demo_21_human_governance_lifecycle.py` | uvicorn (agent) | try/finally only |
| `live_demo_22_change_event_causality.py` | uvicorn (agent) | try/finally only |
| `live_demo_24_cloudwatch_provider_bootstrap.py` | uvicorn (agent) | try/finally only |
| `live_demo_26_log_fetching_before_after.py` | uvicorn (agent) | try/finally only |
| `live_demo_http_optimizations.py` | uvicorn (agent) | try/finally only |
| `live_demo_cascade_failure.py` | none (in-process) | KeyboardInterrupt catch |
| `live_demo_deployment_regression.py` | none (in-process) | KeyboardInterrupt catch |

**Note:** Demos `cascade_failure` and `deployment_regression` do NOT manage subprocesses. They run pipelines in-process and already handle `KeyboardInterrupt`. These need no SIGINT changes.

**Actual targets: 6 demos** (20, 21, 22, 24, 26, http_optimizations).

### 2.3 Approach

Add a shared SIGINT/SIGTERM registration helper to `_demo_utils.py` that:

1. Accepts a cleanup callback
2. Registers both SIGINT and SIGTERM handlers
3. Prints a consistent interrupt message using existing color helpers
4. Calls the cleanup callback
5. Exits with code 130 (standard SIGINT exit code)

Each demo wires its existing cleanup/stop_agent logic into the shared handler.

### 2.4 Design

Add to `_demo_utils.py`:

```python
def register_cleanup_handler(cleanup_fn: Callable[[], None]) -> None:
    """Register SIGINT/SIGTERM handlers that run cleanup before exit."""
    def _handler(_sig: int, _frame: Any) -> None:
        print(f"\n{C.YELLOW}Interrupted — running cleanup...{C.RESET}")
        cleanup_fn()
        sys.exit(130)
    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)
```

Each demo adds one call after subprocess creation:

```python
register_cleanup_handler(lambda: stop_agent(proc, log_handle))
```

### 2.5 Files Changed

| File | Change |
|------|--------|
| `scripts/demo/_demo_utils.py` | Add `register_cleanup_handler()`, imports for `signal`, `sys`, `typing` |
| `scripts/demo/live_demo_20_unknown_incident_safety_net.py` | Add handler registration after `start_or_reuse_agent()` |
| `scripts/demo/live_demo_21_human_governance_lifecycle.py` | Add handler registration after `start_or_reuse_agent()` |
| `scripts/demo/live_demo_22_change_event_causality.py` | Add handler registration after `start_or_reuse_agent()` |
| `scripts/demo/live_demo_24_cloudwatch_provider_bootstrap.py` | Add handler registration after `start_or_reuse_agent()` |
| `scripts/demo/live_demo_26_log_fetching_before_after.py` | Add handler registration after `start_or_reuse_agent()` |
| `scripts/demo/live_demo_http_optimizations.py` | Add handler registration after subprocess start |

---

## 3. Work Item 2: Shared Agent Lifecycle

### 3.1 Problem

9 demos duplicate `start_or_reuse_agent()` and `stop_agent()` with two incompatible signatures:
- **Pattern A** (demos 20, 21, 22): 3-tuple return `(process, started_by_demo, log_handle)`
- **Pattern B** (demos 24, 26): 2-tuple return `(process, log_handle)`
- **Pattern C** (http_optimizations): inline subprocess with DEVNULL

### 3.2 Unified Design

Extract to `_demo_utils.py` a single pair of functions using Pattern A (superset):

```python
def start_or_reuse_agent(
    port: int = 8181,
    log_path: str = "/tmp/sre_agent_demo.log",
    startup_timeout: int = 40,
    health_path: str = "/health",
) -> tuple[subprocess.Popen | None, bool, IO[Any] | None]:
    """Start uvicorn SRE Agent or reuse existing.

    Returns:
        (process, started_by_demo, log_handle)
        If agent already running: (None, False, None)
    """

def stop_agent(
    process: subprocess.Popen | None,
    started_by_demo: bool,
    log_handle: IO[Any] | None,
    shutdown_timeout: int = 5,
) -> None:
    """Terminate agent process if started by this demo."""
```

### 3.3 Migration Plan

| Demo | Current Pattern | Migration |
|------|----------------|-----------|
| Demo 20 | Pattern A (local) | Replace with import from `_demo_utils` |
| Demo 21 | Pattern A (local, exact copy) | Replace with import |
| Demo 22 | Pattern A (local, exact copy) | Replace with import |
| Demo 24 | Pattern B (2-tuple) | Replace with import; adapt caller to 3-tuple |
| Demo 26 | Pattern B (2-tuple) | Replace with import; adapt caller to 3-tuple |
| HTTP opts | Pattern C (inline) | Replace with import; adapt caller to 3-tuple |
| Demo 15 (ECS) | Has own agent+bridge startup with SIGINT | Leave as-is (manages bridge too) |
| Demo 21 (localstack incident) | Has own agent+bridge startup with SIGINT | Leave as-is (manages bridge too) |
| Demo 23 (RAG eval) | Has own agent startup with SIGINT | Leave as-is (manages LocalStack resources too) |

**Demos 15, 21 (localstack), and 23 are excluded** because they manage additional resources (bridge subprocess, LocalStack resources) beyond just the agent process. Forcing them into the shared utility would over-abstract.

### 3.4 Files Changed

| File | Change |
|------|--------|
| `scripts/demo/_demo_utils.py` | Add `start_or_reuse_agent()`, `stop_agent()`, required imports |
| `scripts/demo/live_demo_20_unknown_incident_safety_net.py` | Remove local functions, import from `_demo_utils` |
| `scripts/demo/live_demo_21_human_governance_lifecycle.py` | Remove local functions, import from `_demo_utils` |
| `scripts/demo/live_demo_22_change_event_causality.py` | Remove local functions, import from `_demo_utils` |
| `scripts/demo/live_demo_24_cloudwatch_provider_bootstrap.py` | Remove local functions, adapt 2-tuple → 3-tuple caller |
| `scripts/demo/live_demo_26_log_fetching_before_after.py` | Remove local functions, adapt 2-tuple → 3-tuple caller |
| `scripts/demo/live_demo_http_optimizations.py` | Remove inline subprocess, use shared functions |

---

## 4. Work Item 3: Phase 3 End-to-End Remediation Demo

### 4.1 Purpose

Demonstrate the complete autonomous remediation workflow:

```
Detect → Diagnose → Confidence Gate → Blast Radius Check →
Lock Acquire → Execute (Canary → Full) → Validate → 
Cooldown Record → Release Lock
```

Plus failure paths:
- Guardrail rejection (blast radius exceeded)
- Kill-switch activation mid-flow
- Cooldown enforcement blocking re-execution

### 4.2 Design Principles

- **Self-contained:** No external dependencies (no LocalStack, no LLM, no K8s cluster)
- **In-process:** Uses domain objects directly (no HTTP API)
- **Demonstrates real code paths:** Uses actual `RemediationEngine`, `GuardrailOrchestrator`, `KillSwitch`, `CooldownEnforcer`, `InMemoryDistributedLockManager`
- **Event-sourced:** Captures and displays domain events at each stage
- **Narrative-driven:** 6 acts telling a coherent incident story

### 4.3 Narrative Structure

```
Act 1 — Safe Remediation (Happy Path)
  Setup: OOM incident on checkout-service, confidence 92%, blast_radius 0.05
  Execute: guardrails pass → lock acquired → canary restart → full restart → verify → cooldown
  Show: Full event chain (REMEDIATION_STARTED → REMEDIATION_COMPLETED)

Act 2 — Blast Radius Rejection
  Setup: Same service but blast_radius 0.95 (95% of pods affected)
  Execute: guardrails reject → BLAST_RADIUS_EXCEEDED event
  Show: Rejection reason and event

Act 3 — Cooldown Enforcement
  Setup: Re-attempt remediation on same resource (cooldown from Act 1 still active)
  Execute: guardrails reject → COOLDOWN_ENFORCED event
  Show: Remaining cooldown seconds

Act 4 — Kill Switch Activation
  Setup: Activate kill switch mid-scenario
  Execute: guardrails reject → engine refuses to act
  Show: Kill switch state and rejection reason

Act 5 — Priority Preemption
  Setup: SRE agent holds lock; SecOps agent requests same resource
  Execute: SecOps preempts SRE lock → SRE loses fencing token validity
  Show: Lock transfer, fencing token invalidation

Act 6 — Full Autonomous Loop (Integration)
  Setup: Fresh state, complete end-to-end with all safety checks
  Execute: detect anomaly → build remediation plan → engine.execute() → verify metrics → done
  Show: Complete audit trail with all domain events in sequence
```

### 4.4 Key Components Used

| Component | Source | Usage |
|-----------|--------|-------|
| `RemediationEngine` | `domain/remediation/engine.py` | Core orchestrator |
| `GuardrailOrchestrator` | `domain/safety/guardrails.py` | Pre-execution validation |
| `KillSwitch` | `domain/safety/kill_switch.py` | Global halt mechanism |
| `CooldownEnforcer` | `domain/safety/cooldown.py` | Anti-oscillation |
| `BlastRadiusCalculator` | `domain/safety/blast_radius.py` | Impact validation |
| `InMemoryDistributedLockManager` | `adapters/coordination/in_memory_lock_manager.py` | Lock protocol |
| `InMemoryEventBus` | `adapters/events/` | Domain event capture |
| `InMemoryEventStore` | `adapters/events/` | Event persistence |
| `CloudOperatorRegistry` | `domain/remediation/` or adapters | Operator dispatch |

### 4.5 Mock Components

A `DemoOperator` implementing `CloudOperatorPort` that:
- Tracks all calls (restart, scale) with timestamps
- Simulates success/failure based on configuration
- Returns realistic response objects

A `DemoVerifier` implementing verification that:
- Checks simulated metrics post-action
- Returns pass/fail based on configuration

### 4.6 File

`scripts/demo/live_demo_phase3_remediation_e2e.py`

### 4.7 Dependencies

- Zero external dependencies (no LocalStack, no LLM, no Docker, no K8s)
- Only imports from `sre_agent.domain.*` and `sre_agent.adapters.coordination.*`
- Uses `_demo_utils.py` for output formatting and pause behavior

---

## 5. Dependencies, Risks, and Assumptions

### Dependencies

| Dependency | Risk | Mitigation |
|-----------|------|-----------|
| `RemediationEngine` API stability | Low | Engine is mature; tests exist |
| `InMemoryDistributedLockManager` completeness | Low | Used by existing demos (#3, #17) |
| `GuardrailOrchestrator` async interface | Medium | May need async event loop in demo |
| `_demo_utils.py` import path | Low | Already works in all existing demos |

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Changing shared `start_or_reuse_agent` breaks existing demos | Medium | High | Test each migrated demo after change |
| `RemediationEngine.execute()` signature differs from demo expectations | Low | Medium | Read actual implementation before coding |
| Demo 24/26 callers break on 3-tuple return | Medium | Medium | Update all call sites simultaneously |

### Assumptions

1. `RemediationEngine` can be constructed with in-memory adapters for all dependencies
2. The `GuardrailOrchestrator.validate()` method is async and follows the documented interface
3. Existing demos' `finally` blocks will still execute alongside signal handlers (Python guarantee)
4. The `sys.path` manipulation in existing demos works for new imports from `_demo_utils.py`

---

## 6. Execution Order

1. **WI-1 (SIGINT):** Modify `_demo_utils.py` first, then add handlers to each demo
2. **WI-2 (Lifecycle):** Add shared functions to `_demo_utils.py`, then migrate demos one by one
3. **WI-3 (Phase 3):** Create new demo file after WI-1 and WI-2 are complete (uses shared utilities)

WI-1 and WI-2 modifications to `_demo_utils.py` are additive (new functions only), so they don't conflict.

---

## 7. Standards Compliance Notes

Reviewed against:
- `docs/project/standards/engineering_standards.md` v2.0.0
- `docs/project/standards/FAANG_Documentation_Standards.md` v1.1.0
- `docs/testing/testing_strategy.md` v1.0.0

| Standard | Compliance | Notes |
|----------|-----------|-------|
| Hexagonal architecture | Compliant | Phase 3 demo imports only from domain + adapters, never crosses inward |
| SOLID (SRP) | Compliant | `register_cleanup_handler` has single responsibility; `start_or_reuse_agent` owns lifecycle |
| Type annotations | Compliant | All new public functions fully typed |
| structlog | N/A | Demo scripts use color output helpers, not production logging |
| Google-style docstrings | Compliant | All new functions will have Args/Returns/Raises docstrings |
| FAANG doc structure | Compliant | Plan has frontmatter (status, version, date) |
| Test pyramid | N/A | Demo scripts are operational, not test-pyramid artifacts |
| mypy --strict / bandit | Exempt | Demo scripts are operational tooling, not library code |
