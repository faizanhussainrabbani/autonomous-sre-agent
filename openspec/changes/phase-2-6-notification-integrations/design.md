## Context

Phase 2 (ASSIST) requires human-in-the-loop approval for Sev 1-2 incidents. The existing `notifications` capability spec defines abstract requirements for escalation, approval, summaries, and routing. This change provides concrete adapter implementations for Slack, Teams, PagerDuty, and OpsGenie.

## Goals / Non-Goals

**Goals:**
- Implement `NotificationPort` and `EscalationPort` ABCs following Hexagonal Architecture
- Deliver Slack adapter with interactive approval buttons (Block Kit)
- Deliver Teams adapter with Adaptive Cards for approval flow
- Deliver PagerDuty adapter with Events API v2 integration
- Deliver OpsGenie adapter as secondary on-call provider
- Achieve <5s notification delivery latency for Slack, <3s for PagerDuty
- Support severity-based routing (Sev 1-2 → PagerDuty + Slack, Sev 3-4 → Slack only)
- Support fallback channels when primary channel fails

**Non-Goals:**
- Custom Slack app distribution (uses bot token, not OAuth app)
- Email notification adapter (deferred to Phase 3)
- Jira ticket creation on incident resolution (deferred — exists in abstract spec)
- SMS/voice notifications

## Decisions

### Decision: Slack Bolt SDK (not raw Web API)
Use `slack-bolt` for event handling and `slack-sdk` for message posting.

**Rationale:** Bolt provides built-in handling for interactive components (button clicks, modal submissions), socket mode for development, and HTTP mode for production. Raw Web API would require manual interaction payload parsing.

### Decision: PagerDuty Events API v2 (not REST API v2)
Use the Events API for incident creation rather than the REST API.

**Rationale:** Events API is designed for automated integrations — it accepts structured payloads with `routing_key` and returns `dedup_key` for idempotent incident management. The REST API requires OAuth and is designed for human-facing CRUD operations.

### Decision: Approval state stored in EventStore (not in Slack)
When an operator clicks Approve/Reject in Slack, the action is recorded as a `DomainEvent` in the EventStore. The Slack adapter does not own approval state.

**Rationale:** Preserves event sourcing as the single source of truth. Slack message state (button disabled, updated text) is a UI concern, not a domain concern.

## Risks / Trade-offs

| Risk | Severity | Mitigation |
|---|---|---|
| Slack API rate limits (1 msg/sec per channel) | Medium | Batch notifications for multi-incident scenarios; use channel-per-incident pattern |
| PagerDuty routing key exposure | High | Store in secrets manager; validate on startup; never log |
| Interactive button timeout (Slack 3s response limit) | Medium | Acknowledge immediately with `ack()`, process approval async |
| Teams webhook deprecation (Microsoft shifting to Bot Framework) | Low | Abstract behind `NotificationPort`; adapter swap is non-breaking |
