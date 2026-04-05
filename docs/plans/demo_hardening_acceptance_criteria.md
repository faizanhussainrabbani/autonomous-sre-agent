---
status: DRAFT
version: 1.0.0
date: 2026-04-03
parent_plan: docs/plans/demo_hardening_phase3_plan.md
---

# Acceptance Criteria: Demo Hardening & Phase 3 Remediation Demo

Each criterion is traceable to a section of the implementation plan.

---

## WI-1: SIGINT Handlers (Plan §2)

| ID | Criterion | Pass/Fail Test |
|----|-----------|---------------|
| AC-1.1 | `_demo_utils.py` exports `register_cleanup_handler(cleanup_fn)` | Function exists, is importable, accepts a `Callable[[], None]` |
| AC-1.2 | `register_cleanup_handler` registers both SIGINT and SIGTERM | Source code contains `signal.signal(signal.SIGINT, ...)` and `signal.signal(signal.SIGTERM, ...)` |
| AC-1.3 | Handler prints interrupt message using `C.YELLOW` | Handler body contains color-formatted print statement |
| AC-1.4 | Handler exits with code 130 | `sys.exit(130)` called in handler |
| AC-1.5 | Demo 20 calls `register_cleanup_handler` after agent start | Grep finds `register_cleanup_handler` call in file |
| AC-1.6 | Demo 21 calls `register_cleanup_handler` after agent start | Same check |
| AC-1.7 | Demo 22 calls `register_cleanup_handler` after agent start | Same check |
| AC-1.8 | Demo 24 calls `register_cleanup_handler` after agent start | Same check |
| AC-1.9 | Demo 26 calls `register_cleanup_handler` after agent start | Same check |
| AC-1.10 | Demo http_optimizations calls `register_cleanup_handler` after subprocess start | Same check |
| AC-1.11 | All 6 demos still have their existing try/finally cleanup intact | try/finally blocks preserved (defense in depth) |

---

## WI-2: Shared Agent Lifecycle (Plan §3)

| ID | Criterion | Pass/Fail Test |
|----|-----------|---------------|
| AC-2.1 | `_demo_utils.py` exports `start_or_reuse_agent()` with documented signature | Function exists with type hints: `-> tuple[subprocess.Popen \| None, bool, IO[Any] \| None]` |
| AC-2.2 | `_demo_utils.py` exports `stop_agent()` with documented signature | Function exists with type hints for all 4 parameters |
| AC-2.3 | `start_or_reuse_agent` checks health endpoint before starting | Source contains HTTP GET to health path |
| AC-2.4 | `start_or_reuse_agent` returns `(None, False, None)` when agent already running | Reuse path returns 3-tuple with `False` |
| AC-2.5 | `start_or_reuse_agent` starts uvicorn subprocess when agent not running | `subprocess.Popen` call with uvicorn command |
| AC-2.6 | `start_or_reuse_agent` polls health with configurable timeout | Loop with timeout parameter, default 40s |
| AC-2.7 | `stop_agent` only terminates if `started_by_demo` is True | Conditional check on `started_by_demo` |
| AC-2.8 | `stop_agent` uses terminate → wait(timeout) → kill fallback | Three-step shutdown pattern present |
| AC-2.9 | `stop_agent` closes log handle safely | try/except around `log_handle.close()` |
| AC-2.10 | Demo 20 removes local `start_or_reuse_agent` and `stop_agent` | Grep finds no local function definitions for these names |
| AC-2.11 | Demo 21 removes local functions, imports from `_demo_utils` | Same check |
| AC-2.12 | Demo 22 removes local functions, imports from `_demo_utils` | Same check |
| AC-2.13 | Demo 24 removes local functions, adapts to 3-tuple return | Local functions removed; caller unpacks 3 values |
| AC-2.14 | Demo 26 removes local functions, adapts to 3-tuple return | Same check |
| AC-2.15 | Demo http_optimizations uses shared functions instead of inline subprocess | Inline Popen removed; imports shared functions |
| AC-2.16 | All 6 migrated demos still function (no import errors at load time) | `python -c "import live_demo_X"` succeeds for each |
| AC-2.17 | Google-style docstrings on both shared functions | Docstrings include Args, Returns sections |

---

## WI-3: Phase 3 End-to-End Remediation Demo (Plan §4)

### File and Structure

| ID | Criterion | Pass/Fail Test |
|----|-----------|---------------|
| AC-3.1 | File exists at `scripts/demo/live_demo_phase3_remediation_e2e.py` | File present on disk |
| AC-3.2 | Module docstring describes purpose and all 6 acts | Docstring contains act descriptions |
| AC-3.3 | No external dependencies (no LocalStack, no LLM, no Docker, no K8s) | No boto3, httpx, or kubectl usage; no env var requirements for external services |
| AC-3.4 | Uses `_demo_utils.py` for output formatting | Imports `banner`, `phase`, `step`, `ok`, `info`, `fail` from `_demo_utils` |
| AC-3.5 | Supports `SKIP_PAUSES=1` for non-interactive mode | `pause_if_interactive` calls present |

### Act 1 — Safe Remediation (Happy Path)

| ID | Criterion | Pass/Fail Test |
|----|-----------|---------------|
| AC-3.6 | Constructs `RemediationEngine` with all safety components | Engine initialized with guardrails, kill_switch, cooldown, lock_manager |
| AC-3.7 | Creates a `RemediationPlan` with safe parameters (blast_radius < threshold) | Plan construction with low blast_radius_ratio |
| AC-3.8 | Engine executes successfully | Result indicates success |
| AC-3.9 | Fencing token is displayed | Output shows fencing token value |
| AC-3.10 | Cooldown is recorded after execution | Cooldown state is verified after action |
| AC-3.11 | Domain events are captured and displayed | Event bus/store contains REMEDIATION events |

### Act 2 — Blast Radius Rejection

| ID | Criterion | Pass/Fail Test |
|----|-----------|---------------|
| AC-3.12 | Creates plan with blast_radius_ratio > threshold (e.g., 0.95) | Plan has high blast ratio |
| AC-3.13 | Guardrails reject the plan | Result indicates rejection |
| AC-3.14 | Rejection reason mentions blast radius | Reason string contains "blast" or "radius" |

### Act 3 — Cooldown Enforcement

| ID | Criterion | Pass/Fail Test |
|----|-----------|---------------|
| AC-3.15 | Re-attempts action on same resource as Act 1 | Same resource identifiers used |
| AC-3.16 | Cooldown blocks execution | Result indicates rejection due to cooldown |
| AC-3.17 | Remaining cooldown time is displayed | Output shows seconds remaining |

### Act 4 — Kill Switch

| ID | Criterion | Pass/Fail Test |
|----|-----------|---------------|
| AC-3.18 | Kill switch is activated with operator ID and reason | `kill_switch.activate()` called |
| AC-3.19 | Subsequent remediation attempt is rejected | Result indicates kill-switch rejection |
| AC-3.20 | Kill switch is deactivated at end of act | `kill_switch.deactivate()` called |

### Act 5 — Priority Preemption

| ID | Criterion | Pass/Fail Test |
|----|-----------|---------------|
| AC-3.21 | SRE agent (priority 2) acquires lock | Lock acquired successfully |
| AC-3.22 | SecOps agent (priority 1) requests same resource | Second lock request made |
| AC-3.23 | SecOps preempts SRE lock | SRE lock invalidated, SecOps lock granted |
| AC-3.24 | Fencing token invalidation is demonstrated | Stale token check returns invalid |

### Act 6 — Full Autonomous Loop

| ID | Criterion | Pass/Fail Test |
|----|-----------|---------------|
| AC-3.25 | Fresh state (new engine, cleared cooldowns) | New instances created |
| AC-3.26 | Complete flow: plan → guardrails → lock → execute → verify → cooldown → release | All steps execute in sequence |
| AC-3.27 | Complete audit trail displayed at end | All domain events printed in chronological order |
| AC-3.28 | Demo exits cleanly with success message | Exit code 0, success banner printed |

### Edge Cases and Quality

| ID | Criterion | Pass/Fail Test |
|----|-----------|---------------|
| AC-3.29 | `SKIP_PAUSES=1` runs demo without blocking | Full execution with env var set completes without input prompts |
| AC-3.30 | Script runs without errors: `python scripts/demo/live_demo_phase3_remediation_e2e.py` | Exit code 0, no tracebacks |
| AC-3.31 | No hardcoded secrets or API keys | Grep for "key", "secret", "token" finds no literals |
| AC-3.32 | Follows naming convention: `live_demo_*.py` | Filename matches pattern |
