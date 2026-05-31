<!-- markdownlint-disable-file -->
# Planning Log: SRE Command Center Backend Operator Dashboard Endpoints

## Discrepancy Log

### Implementation Deviations

* DD-01: Phase 1 validation commands required pnpm dependency verification override.
  * Plan specifies: Run `pnpm --filter @workspace/api-spec run codegen` and `pnpm run typecheck:libs`.
  * Implementation differs: Executed both commands with `--config.verify-deps-before-run=false`.
  * Rationale: Workspace preinstall guard blocked default pnpm verification in this environment; command outputs still validated contract generation and lib typecheck.
* DD-02: Workspace-level typecheck failure was remediated during review-findings implementation.
  * Plan specifies: Run workspace typecheck as part of validation.
  * Implementation differs: Initial run failed in `artifacts/mockup-sandbox` due missing `indicatorClassName` prop typing support; later remediated in Phase 5.
  * Rationale: Converted from blocker to resolved discrepancy after extending shared Progress component props.
* DD-03: Workspace-level build failure was remediated during review-findings implementation.
  * Plan specifies: Run workspace build as part of final validation.
  * Implementation differs: Initial run failed due mockup-sandbox env requirements (`PORT`, then `BASE_PATH`); later remediated in Phase 5.
  * Rationale: Converted from blocker to resolved discrepancy after adding safe Vite config fallbacks.
* DD-11: Phase 5 revalidation exposed mockup-sandbox hard requirement for `PORT`.
  * Plan specifies: Workspace build should run without ad hoc environment setup.
  * Implementation differs: Build initially required explicit `PORT`; Step 5.5 introduced fallback port handling.
  * Rationale: Resolved via configuration fallback while preserving explicit override behavior.
* DD-12: Post-Step-5.5 validation exposed mockup-sandbox hard requirement for `BASE_PATH`.
  * Plan specifies: Workspace build should run without ad hoc environment setup.
  * Implementation differs: Build initially required explicit `BASE_PATH`; Step 5.6 introduced fallback base path (`/`).
  * Rationale: Resolved via configuration fallback while preserving explicit override behavior.

## Implementation Paths Considered

### Selected: Express dashboard BFF over shared Postgres

* Approach: Extend the Express backend with typed Drizzle reads, OpenAPI-backed responses, and polling websocket delivery.
* Rationale: It matches the repository boundary and lets the command-center backend become a meaningful product surface without changing the Python API.
* Evidence: .copilot-tracking/research/2026-05-31/sre-command-center-backend-endpoints-research.md (Lines 220-360)

### IP-01: Consume the Python SRE Agent APIs directly

* Approach: Keep the Express app as a shell and point the dashboard frontend at the Python FastAPI endpoints.
* Trade-offs: Lower backend implementation effort, but the command-center backend remains a scaffold and the dashboard still depends on another service for its core data.
* Rejection rationale: It does not satisfy the user's backend-focused planning request for the SRE Command Center itself.

### IP-02: Add PostgreSQL LISTEN/NOTIFY before the websocket

* Approach: Modify the Python event persistence path or add triggers to emit db notifications, then attach a websocket broadcaster to them.
* Trade-offs: Lower update latency, but it expands the scope into the Python service and database trigger work.
* Rejection rationale: The research showed no existing notification path and no current requirement to solve that before the dashboard backend can land.

## Suggested Follow-On Work

* WI-01: Add a dashboard coordination/audit endpoint — Expose coordination_audit for operator history and lock timeline views if the dashboard scope expands. (medium)
  * Source: research on coordination_audit table usefulness.
  * Dependency: Core dashboard endpoints and schema work must land first.
* WI-02: Replace websocket polling with notification-backed push — Add pg_notify or trigger-based event delivery for lower-latency incident updates. (high)
  * Source: deep schema and websocket research.
  * Dependency: Python persistence or database trigger changes.
* WI-03: Materialize KPI aggregates — Move phase and accuracy metrics into a dedicated aggregate or materialized view if SQL aggregation becomes a bottleneck. (medium)
  * Source: dashboard KPI requirements and metric_baselines research.
  * Dependency: Dashboard endpoint stability and production metrics validation.
* WI-04: Completed in Phase 5 - mockup-sandbox TypeScript prop mismatch resolved and workspace-level validation restored. (closed)
  * Source: Phase 5 remediation and Phase 6 validation runs.
  * Dependency: None.
