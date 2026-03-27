## NOTIF-001 — Port Interfaces (Critical Path)

- [ ] 1.1 Create `src/sre_agent/ports/notification.py` — `NotificationPort` ABC with `send_alert()`, `send_approval_request()`, `send_resolution_summary()`, `health_check()`
- [ ] 1.2 Create `src/sre_agent/ports/escalation.py` — `EscalationPort` ABC with `create_incident()`, `update_incident()`, `resolve_incident()`, `health_check()`
- [ ] 1.3 Define `NotificationMessage` data model in `domain/models/notifications.py` — structured payload for all notification types
- [ ] 1.4 Define `EscalationPayload` data model — structured incident payload with diagnosis, confidence, evidence links

## NOTIF-002 — Slack Adapter (High)

- [ ] 2.1 Create `src/sre_agent/adapters/notifications/slack.py` implementing `NotificationPort`
- [ ] 2.2 Implement `send_alert()` using Block Kit for structured incident messages
- [ ] 2.3 Implement `send_approval_request()` with interactive Approve/Reject buttons
- [ ] 2.4 Implement button interaction handler — acknowledge within 3s, dispatch `ApprovalReceived` event to EventBus
- [ ] 2.5 Implement `send_resolution_summary()` with incident timeline, actions taken, and metrics
- [ ] 2.6 Implement `health_check()` — validate bot token via `auth.test` API call
- [ ] 2.7 Add circuit breaker wrapping for Slack API calls (reuse `resilience.py` pattern)

## NOTIF-003 — Teams Adapter (Medium)

- [ ] 3.1 Create `src/sre_agent/adapters/notifications/teams.py` implementing `NotificationPort`
- [ ] 3.2 Implement Adaptive Card templates for incident alerts and approval requests
- [ ] 3.3 Implement webhook-based message delivery
- [ ] 3.4 Implement action handler for approval/reject responses

## NOTIF-004 — PagerDuty Adapter (High)

- [ ] 4.1 Create `src/sre_agent/adapters/oncall/pagerduty.py` implementing `EscalationPort`
- [ ] 4.2 Implement `create_incident()` using Events API v2 `trigger` action
- [ ] 4.3 Structured payload: severity mapping (Sev 1→critical, Sev 2→error), diagnosis summary, confidence score, evidence links, audit trail URL
- [ ] 4.4 Implement `update_incident()` using Events API v2 with `dedup_key`
- [ ] 4.5 Implement `resolve_incident()` using Events API v2 `resolve` action
- [ ] 4.6 Implement `health_check()` — validate routing key format and API connectivity

## NOTIF-005 — OpsGenie Adapter (Medium)

- [ ] 5.1 Create `src/sre_agent/adapters/oncall/opsgenie.py` implementing `EscalationPort`
- [ ] 5.2 Implement `create_incident()`, `update_incident()`, `resolve_incident()` using OpsGenie Alert API
- [ ] 5.3 Map severity levels and include diagnosis context

## NOTIF-006 — Configuration and Routing (Medium)

- [ ] 6.1 Add `NotificationSettings` to `config/settings.py` — channel configuration, routing rules, fallback order
- [ ] 6.2 Implement severity-based routing logic (Sev 1-2 → PagerDuty + Slack, Sev 3-4 → Slack only)
- [ ] 6.3 Implement fallback chain — if primary channel fails, attempt next in priority order
- [ ] 6.4 Register notification adapters in `adapters/bootstrap.py`

## NOTIF-007 — Testing (High)

- [ ] 7.1 Unit tests for all port interface methods (mock adapters)
- [ ] 7.2 Integration tests for Slack adapter using `slack-sdk` mock server
- [ ] 7.3 Integration tests for PagerDuty adapter using mock Events API
- [ ] 7.4 E2E test: full HITL approval flow — diagnosis → Slack notification → button click → remediation authorized
