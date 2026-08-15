<!-- markdownlint-disable-file -->
# Planning Log: Mockup Sandbox to Operator Dashboard

## Discrepancy Log

Gaps and differences identified between research findings and the implementation plan.

### Unaddressed Research Items

* None. All previously identified DR items are mapped to in-scope implementation steps in .copilot-tracking/details/2026-05-31/mockup-sandbox-to-operator-dashboard-details.md (Step 4.4, Step 4.5, Step 4.6).

### Resolved Research Items (Tracked)

* DR-01: Node API validation failures currently surface as generic 500 responses rather than structured 4xx client errors
  * Source: .copilot-tracking/research/subagents/2026-05-31/backend-api-contracts-analysis-research.md (Lines 112-133)
  * Resolution: Addressed by Step 4.4 in .copilot-tracking/details/2026-05-31/mockup-sandbox-to-operator-dashboard-details.md
  * Status: Planned in scope

* DR-02: Phase-2-7 artifacts reference FastAPI/Next.js wording while workspace implementation reality is Express/Vite
  * Source: .copilot-tracking/research/subagents/2026-05-31/openspec-phase-2-7-analysis-research.md (Lines 181-213)
  * Resolution: Addressed by Step 4.6 in .copilot-tracking/details/2026-05-31/mockup-sandbox-to-operator-dashboard-details.md
  * Status: Planned in scope

* DR-03: Websocket channel is implemented but not represented as a path in OpenAPI paths section
  * Source: .copilot-tracking/research/subagents/2026-05-31/backend-api-contracts-analysis-research.md (Lines 154-171)
  * Resolution: Addressed by Step 4.5 in .copilot-tracking/details/2026-05-31/mockup-sandbox-to-operator-dashboard-details.md
  * Status: Planned in scope

* DR-04: Phase label wording drift (AUTONOMOUS/AUTOMATE/PREDICTIVE) across artifacts
  * Source: .copilot-tracking/research/2026-05-31/mockup-sandbox-to-operator-dashboard-research.md (Lines 46-49)
  * Resolution: Addressed by Step 4.6 in .copilot-tracking/details/2026-05-31/mockup-sandbox-to-operator-dashboard-details.md
  * Status: Planned in scope

* DR-05: Performance acceptance thresholds lack explicit instrumentation guidance in phase task artifacts
  * Source: .copilot-tracking/research/subagents/2026-05-31/openspec-phase-2-7-analysis-research.md (Lines 231-236)
  * Resolution: Addressed by Step 4.2 in .copilot-tracking/details/2026-05-31/mockup-sandbox-to-operator-dashboard-details.md
  * Status: Planned in scope

### Plan Deviations from Research

* DD-02: Phase 1 validation command context required package-root execution
  * Research recommends: Package-scoped validation commands for new dashboard package
  * Plan implements: Validation commands were first executed from repository root, then rerun from fullstackapp/SRE-Command-Center to satisfy workspace filter resolution
  * Rationale: New package is nested under fullstackapp workspace and command context affected filter execution

* DD-03: Phase 2 incident detail rendering required selector-level mapping adjustment
  * Research recommends: Use DTO-to-view-model mapping to isolate UI rendering from transport schema drift
  * Plan implements: Incident detail UI was updated to consume mapped selector fields after transient type mismatches on direct transport access
  * Rationale: Preserves type safety and aligns with contract-mapping architecture in the implementation details

* DD-04: Phase 4 backend validation gate exposed missing api-server test command
  * Research recommends: Validate backend contract changes with executable verification commands
  * Plan implements: Added Step 5.4 to introduce api-server test script and minimal 4xx validation tests before final completion
  * Rationale: Ensures validation protocol completeness for backend contract changes introduced in Phase 4

* DD-05: Phase 5 api-server tests required environment bootstrap default for DATABASE_URL
  * Research recommends: Keep validation commands reproducible and deterministic in local and CI contexts
  * Plan implements: Added test-script environment defaults in artifacts/api-server/package.json and completed api-server test execution
  * Rationale: Route-level validation tests import DB-configured modules and need stable test bootstrap

* DD-06: Post-review remediation introduced explicit route rendering tests and evidence persistence updates
  * Research recommends: Ensure implementation artifacts include both route-level test assertions and auditable validation evidence
  * Plan implements: Added route-rendering test suite plus explicit Phase 5.1 command evidence section in the changes log
  * Rationale: Closes review major findings without altering core architecture or scope

## Implementation Paths Considered

### Selected: New Production Package with Sandbox Retained

* Approach: Create artifacts/operator-dashboard as production runtime package and retain artifacts/mockup-sandbox as design surface
* Rationale: Best weighted score, lowest migration risk, strongest architecture fit for current monorepo
* Evidence: .copilot-tracking/research/subagents/2026-05-31/migration-alternatives-analysis-research.md (Lines 251-272)

### IP-01: In-Place Refactor of mockup-sandbox

* Approach: Convert existing sandbox package directly into production dashboard runtime
* Trade-offs: Fast initial execution but high coupling with preview/generator shell and elevated maintenance risk
* Rejection rationale: Conflicts with long-term separation of concerns and increases regression risk in design workflows

### IP-02: Greenfield Replacement of sandbox

* Approach: Remove/replace mockup-sandbox entirely with a greenfield production app
* Trade-offs: Clean slate architecture, but highest blast radius and lost design sandbox utility
* Rejection rationale: Limited MVP gain over selected approach with materially higher disruption

## Suggested Follow-On Work

* WI-01: Standardize backend validation errors to structured 4xx payloads — Update API server validation/error mapping to align contract and runtime (High)
  * Source: Post-M4 stabilization and backward-compatibility hardening
  * Dependency: Milestone M4 completion

* WI-02: Formalize websocket endpoint contract publication — Add OpenAPI extension or companion async contract for /api/ws/incidents (Medium)
  * Source: Post-M4 contract governance refinement
  * Dependency: Milestone M4 completion

* WI-03: Harmonize OpenSpec phase-2-7 framework/testing wording with repository implementation reality (Medium)
  * Source: Ongoing OpenSpec governance and future phase artifacts
  * Dependency: Milestone M4 completion

* WI-04: Define reusable performance instrumentation template for future dashboard phases (Low)
  * Source: DR-05
  * Dependency: Baseline performance harness implemented in dashboard package

* WI-05: Extend backend CI gates for api-server when contract-affecting route changes are made (Medium)
  * Source: Phase 4 validation outcome
  * Dependency: Step 5.4 completion

* WI-06: Add positive-path incidents API contract tests with seeded test fixtures (Low)
  * Source: Phase 5 implementation recommendation
  * Dependency: Existing validation test harness in api-server
