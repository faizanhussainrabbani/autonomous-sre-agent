<!-- markdownlint-disable-file -->
# Planning Log: SRE Command Center Progress Update So Far

## Discrepancy Log

Gaps and differences identified between research findings and the implementation plan.

### Unaddressed Research Items

* None. The plan explicitly covers contract publication, UI wording cleanup, and validation expansion. The only deferred item is the transport rewrite, which is tracked below as a plan deviation and follow-on work item.

### Plan Deviations from Research

* DD-01: The research recommends deciding between poll-based delivery and notification-backed push before further expansion.
  * Research recommends: Treat websocket transport publication and transport model choice as the next decision point
  * Plan implements: Stabilize and publish the current websocket contract now, keep the existing poll-and-resync behavior for the present plan, and defer a transport rewrite to follow-on work
  * Rationale: The current code already compensates for polling with reconnect and resync behavior, so the lower-risk move is to formalize the contract and clean up the remaining hardening gaps first
  * Impact: medium — the runtime still inherits polling latency and scalability limits until the deferred transport rewrite is addressed
  * Resolution: Track the transport rewrite as follow-on work in WI-01 and keep this plan scoped to contract publication and hardening

* DD-02: The research flags static operational copy as a source of user confusion.
  * Research recommends: Remove or replace the placeholder operator-facing status text before further rollout
  * Plan implements: Normalize the remaining static copy and phase wording in the dashboard package while preserving any intentional fallback language
  * Rationale: This keeps the UI honest about what is live data versus fallback copy without expanding product scope
  * Impact: medium — stale labels can still overstate live state until the wording cleanup lands
  * Resolution: Complete Step 1.2 and preserve explicit fallback labeling where live data is not yet available

* DD-03: The research recommends broadening validation confidence beyond the incidents route.
  * Research recommends: Expand backend route validation coverage beyond incidents so the rest of the exposed surface is exercised
  * Plan implements: Add targeted coverage around the already-exposed api-server and operator-dashboard surfaces, without introducing a new testing framework or a transport rewrite
  * Rationale: The plan stays focused on the currently shipped surfaces and avoids turning a hardening pass into a new architecture effort
  * Impact: medium — the exposed contract surface remains unevenly verified until the additional route and boundary checks land
  * Resolution: Execute Step 1.3 and the final validation pass in Phase 2, then carry any remaining gaps into future planning

## Implementation Paths Considered

### Selected: Stabilize and publish the current command center surface

* Approach: Keep the operator-dashboard package and poll-based websocket recovery model, publish the remaining websocket contract surface, normalize static copy, and expand validation around existing routes
* Rationale: Lowest-risk way to make the current implementation honest, documented, and testable while preserving the already-working dashboard flow
* Evidence: .copilot-tracking/research/2026-07-05/sre-command-center-progress-update-so-far-research.md (Lines 46-77 and 111-130)

### IP-01: Move the websocket runtime to notification-backed push now

* Approach: Replace the current poll-and-resync model with a push-driven transport layer before doing any further contract or UI cleanup
* Trade-offs: Better theoretical latency and transport elegance, but higher implementation risk and more surface area for regressions
* Rejection rationale: The current implementation already recovers from polling, so a transport rewrite is disproportionate to the remaining hardening gaps

### IP-02: Treat the dashboard as complete and only update docs

* Approach: Leave runtime behavior unchanged and publish only narrative documentation updates
* Trade-offs: Lowest effort, but it would preserve the mismatch between live behavior, static UI copy, and the published contract surface
* Rejection rationale: The research shows real follow-on work remains, especially around contract publication and validation

## Suggested Follow-On Work

* WI-01: Notification-backed websocket delivery and transport hardening - Replace the remaining poll-and-resync dependency with a push-based model if future rollout demands lower latency or better scale (High)
  * Source: .copilot-tracking/research/2026-07-05/sre-command-center-progress-update-so-far-research.md (Lines 74-77 and 111-130)
  * Dependency: Contract publication and dashboard wording cleanup should complete first

* WI-02: Broader api-server route validation coverage - Expand the test surface beyond incidents so the already-exposed endpoints have consistent contract checks (Medium)
  * Source: .copilot-tracking/research/2026-07-05/sre-command-center-progress-update-so-far-research.md (Lines 74-77 and 141-142)
  * Dependency: Existing route test harnesses remain available

* WI-03: Phase-label and operator-copy harmonization - Remove any remaining wording drift between dashboard UI, docs, and OpenSpec vocabulary (Medium)
  * Source: .copilot-tracking/research/2026-07-05/sre-command-center-progress-update-so-far-research.md (Lines 67-77 and 139-142)
  * Dependency: Live-state cleanup in the dashboard package

* WI-04: Contract publication follow-through for websocket consumers - Keep the websocket publication artifact aligned with the implementation as the command center evolves (Low)
  * Source: .copilot-tracking/research/2026-07-05/sre-command-center-progress-update-so-far-research.md (Lines 67-70 and 139-140)
  * Dependency: Step 1.1 in the details file