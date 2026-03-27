## Why

The Autonomous SRE Agent currently has no production notification channel for communicating with human operators. Every competitor in the AIOps market — PagerDuty, Rootly, BigPanda, Datadog, Robusta — has deep Slack and/or Teams integration as table-stakes functionality. Without notification integrations, the Phase 2 HITL (Human-In-The-Loop) approval workflow for Sev 1-2 incidents cannot function in a production environment.

The competitive analysis identified two critical gaps:
1. **No Slack/Teams integration** — Required for real-time incident alerts, approval/reject buttons, and resolution summaries
2. **No PagerDuty/OpsGenie integration** — Required for enterprise on-call escalation with structured incident payloads

These are bundled into a single change because they implement the same port abstractions (`NotificationPort`, `EscalationPort`) and share HITL approval flow dependencies.

## What Changes

- **New `NotificationPort` ABC** (`ports/notification.py`): Abstract interface for notification delivery with channel configuration, message formatting, and delivery confirmation
- **New `EscalationPort` ABC** (`ports/escalation.py`): Abstract interface for on-call escalation with incident creation, update, and resolution lifecycle
- **New Slack adapter** (`adapters/notifications/slack.py`): Implements `NotificationPort` using Slack Bolt/Web API. Supports: incident alerts, interactive approve/reject buttons, resolution summaries, channel creation
- **New Teams adapter** (`adapters/notifications/teams.py`): Implements `NotificationPort` using Microsoft Teams webhook/Bot Framework. Supports: adaptive cards with action buttons
- **New PagerDuty adapter** (`adapters/oncall/pagerduty.py`): Implements `EscalationPort` using PagerDuty Events API v2. Auto-creates incidents with structured diagnosis payloads
- **New OpsGenie adapter** (`adapters/oncall/opsgenie.py`): Implements `EscalationPort` using Atlassian OpsGenie API
- **Updated Action Layer**: HITL approval flow now routes through `NotificationPort` for Sev 1-2 incidents
- **Updated configuration**: `NotificationSettings` in `config/settings.py` for channel routing, escalation policies, and fallback configuration

## Capabilities

### New Capabilities
- `slack-notifications`: Real-time incident alerts, interactive approval buttons, resolution summaries via Slack
- `teams-notifications`: Incident alerts and approval flow via Microsoft Teams adaptive cards
- `pagerduty-escalation`: On-call escalation with structured diagnosis payloads, confidence scores, and evidence links
- `opsgenie-escalation`: On-call escalation via Atlassian OpsGenie API

### Modified Capabilities
- `notifications`: Existing abstract spec now has concrete adapter implementations
- `safety-guardrails`: HITL approval flow now routed through live notification channels

## Impact

- **Dependencies**: `slack-bolt`, `slack-sdk`, `pdpyras` (PagerDuty Python SDK), `opsgenie-sdk`
- **Configuration**: New environment variables for API tokens (`SRE_AGENT_SLACK_TOKEN`, `SRE_AGENT_PAGERDUTY_ROUTING_KEY`, etc.)
- **Security**: API tokens must be stored in secrets manager (Vault/AWS SM/Azure KV), never in config files
