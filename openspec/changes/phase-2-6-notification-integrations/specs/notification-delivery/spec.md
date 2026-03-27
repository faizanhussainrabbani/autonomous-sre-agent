## ADDED Requirements — Phase 2.6 Notification Delivery

> **Source:** [Competitively-Driven Roadmap](../../../../docs/project/roadmap_competitive_driven.md) — Items 2+3
> **Competitive Context:** Every competitor (PagerDuty, Rootly, BigPanda, Robusta) has deep Slack integration. PagerDuty on-call is the enterprise standard.
> **Extends:** [notifications capability spec](../../autonomous-sre-agent/specs/notifications/spec.md)

### Requirement: Slack Notification Delivery Latency
The system SHALL deliver Slack notifications within a latency target that ensures timely human response during incidents.

#### Scenario: Incident alert delivery to Slack
- **GIVEN** a Sev 1 incident is diagnosed
- **WHEN** the notification adapter sends the alert
- **THEN** the message SHALL appear in the configured Slack channel within 5 seconds of diagnosis completion
- **AND** the message SHALL include: severity badge, service name, diagnosis summary, confidence score, and evidence citations

#### Scenario: Approval request delivery with interactive buttons
- **GIVEN** a Sev 1-2 incident requires human approval for remediation
- **WHEN** the approval request is sent to Slack
- **THEN** the message SHALL include interactive Approve and Reject buttons
- **AND** clicking Approve SHALL dispatch an `ApprovalReceived` domain event within 3 seconds
- **AND** the Slack message SHALL update to show the approval status and approver identity

#### Scenario: Resolution summary delivery
- **GIVEN** an incident has been resolved (autonomously or with approval)
- **WHEN** the resolution summary is generated
- **THEN** a structured summary SHALL be posted to the incident Slack channel within 5 minutes of resolution
- **AND** the summary SHALL include: incident timeline, root cause, remediation actions, post-action metrics, and total resolution time

### Requirement: PagerDuty Escalation Delivery Latency
The system SHALL create PagerDuty incidents within a latency target to ensure on-call responders are paged promptly.

#### Scenario: PagerDuty incident creation
- **GIVEN** a Sev 1-2 incident is diagnosed and requires escalation
- **WHEN** the PagerDuty adapter creates the incident
- **THEN** incident creation SHALL complete within 3 seconds
- **AND** the incident payload SHALL include: severity (mapped to PagerDuty severity), diagnosis summary, confidence score, evidence links, and audit trail URL

#### Scenario: PagerDuty incident resolution on remediation completion
- **GIVEN** an escalated incident has been successfully remediated
- **WHEN** post-action verification confirms recovery
- **THEN** the PagerDuty incident SHALL be automatically resolved via Events API v2
- **AND** the resolution note SHALL include remediation summary and metrics confirmation

### Requirement: Notification Fallback and Resilience
The system SHALL attempt fallback channels when the primary notification channel is unreachable.

#### Scenario: Slack unavailable, fallback to PagerDuty
- **GIVEN** Slack API returns 5xx errors or times out
- **WHEN** a notification needs to be delivered
- **THEN** the system SHALL attempt delivery via the next channel in the fallback chain within 10 seconds
- **AND** log the primary channel failure with error details

#### Scenario: All channels exhausted
- **GIVEN** all configured notification channels have failed
- **WHEN** fallback chain is exhausted
- **THEN** the system SHALL log a `CRITICAL` event
- **AND** halt autonomous remediation actions until a human acknowledges
- **AND** the failure SHALL be visible on the `/api/v1/status` endpoint as `notification_degraded=true`

### Requirement: Notification Message Delivery Confirmation
The system SHALL track notification delivery status for auditability.

#### Scenario: Delivery confirmation logged
- **WHEN** any notification is sent via any channel
- **THEN** the system SHALL log a structured event with `channel`, `message_type`, `delivery_status` (success/failure), `latency_ms`, and `alert_id`
- **AND** delivery events SHALL be recorded in the EventStore

---

## Implementation References

* **Ports:** `src/sre_agent/ports/notification.py`, `src/sre_agent/ports/escalation.py`
* **Adapters:** `src/sre_agent/adapters/notifications/slack.py`, `src/sre_agent/adapters/oncall/pagerduty.py`
* **Extends:** `openspec/changes/autonomous-sre-agent/specs/notifications/spec.md`
