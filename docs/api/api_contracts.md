# API & Integration Contracts

**Service:** Autonomous SRE Agent
**Status:** DRAFT
**Version:** 1.0.0

This document defines the strict API contracts and JSON schemas for all external boundaries of the Autonomous SRE Agent. Internal inter-component messaging uses standard Python dataclasses (`src/sre_agent/domain/models/canonical.py`).

---

## 1. External Telemetry Ingestion (OpenTelemetry)
The agent consumes data primarily from OpenTelemetry Collectors. The following describes semantic conventions the agent *requires* to function.

### 1.1 Required Entity Attributes (`ServiceLabels`)
Regardless of the signal type (Metric, Trace, Log), the `resource.attributes` MUST contain:
*   `service.name` (string): Logical name of the service.
*   `k8s.namespace.name` (string): Namespace (for K8s environments).
*   *Phase 1.5 Exception:* If `k8s.namespace.name` is absent, the payload must include `cloud.resource_id` and `cloud.platform` (e.g., `aws_lambda`).

---

## 2. Escalation Payloads (PagerDuty / Slack)
When the agent encounters a Sev 1/2 incident, or lacks confidence to auto-remediate a Sev 3/4, it POSTs an escalation payload.

### 2.1 Webhook Schema
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "AgentEscalationPayload",
  "type": "object",
  "properties": {
    "alert_id": { "type": "string", "format": "uuid" },
    "anomaly_type": { "type": "string", "enum": ["latency_spike", "error_rate_surge", "memory_pressure", "disk_exhaustion", "certificate_expiry", "multi_dimensional", "deployment_induced", "invocation_error_surge", "traffic_anomaly"] },
    "service_target": { 
      "type": "object",
      "properties": {
        "service": { "type": "string" },
        "namespace": { "type": "string" },
        "compute_mechanism": { "type": "string" }
      }
    },
    "severity": { "type": "integer", "enum": [1, 2, 3, 4] },
    "diagnostic_summary": { "type": "string" },
    "confidence_score": { "type": "number", "minimum": 0.0, "maximum": 1.0 },
    "proposed_remediation": { "type": "string", "nullable": true },
    "action_required": { "type": "boolean" },
    "interactive_links": {
      "type": "object",
      "properties": {
        "approve_action": { "type": "string", "format": "uri" },
        "reject_action": { "type": "string", "format": "uri" },
        "view_dashboard": { "type": "string", "format": "uri" }
      }
    }
  },
  "required": ["alert_id", "anomaly_type", "service_target", "severity", "diagnostic_summary", "confidence_score", "action_required"]
}
```

---

## 3. Global Kill Switch API
Used to instantly halt all autonomous remediations across the fleet.

### 3.1 [PLANNED] Endpoint `/api/v1/system/halt`
*   **Method:** `POST`
*   **Auth:** Requires `GlobalAdmin` or `IncidentCommander` RBAC role.
*   **Request Body:**
    ```json
    {
      "reason": "String",
      "requested_by": "String (Email/ID)",
      "mode": { "type": "string", "enum": ["soft", "hard"] }
    }
    ```
*   **Response (200 OK):**
    ```json
    {
      "status": "halted",
      "timestamp": "ISO8601",
      "active_remediations_aborted": 2
    }
    ```

### 3.2 [PLANNED] Endpoint `/api/v1/system/resume`
*   **Method:** `POST`
*   **Auth:** Requires dual-authorization token.
*   **Request Body:**
    ```json
    {
      "primary_approver": "String",
      "secondary_approver": "String",
      "review_notes": "String"
    }
    ```

---

## 4. Multi-Agent Coordination Protocol

To function within the multi-agent ecosystem described in `AGENTS.md`, agents communicate their intents and state changes via a shared message bus (e.g., Redis Pub/Sub or Kafka).

### 4.1 Action Intent (Lock Request) Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "ActionIntent",
  "type": "object",
  "properties": {
    "intent_id": { "type": "string", "format": "uuid" },
    "agent_id": { "type": "string" },
    "priority_level": { "type": "integer", "enum": [1, 2, 3] },
    "target_resource": {
      "type": "object",
      "properties": {
        "resource_type": { "type": "string" },
        "resource_name": { "type": "string" },
        "namespace": { "type": "string" }
      },
      "required": ["resource_type", "resource_name"]
    },
    "proposed_action": { "type": "string" },
    "estimated_duration_seconds": { "type": "integer" }
  },
  "required": ["intent_id", "agent_id", "priority_level", "target_resource", "proposed_action"]
}
```

### 4.2 Resource Acted Upon (State Observation) Schema

Published immediately after an agent successfully modifies a resource.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "ResourceActedUpon",
  "type": "object",
  "properties": {
    "event_id": { "type": "string", "format": "uuid" },
    "agent_id": { "type": "string" },
    "timestamp": { "type": "string", "format": "date-time" },
    "target_resource": {
      "type": "object",
      "properties": {
        "resource_type": { "type": "string" },
        "resource_name": { "type": "string" },
        "namespace": { "type": "string" }
      },
      "required": ["resource_type", "resource_name"]
    },
    "action_executed": { "type": "string" },
    "new_state": { "type": "string" },
    "cooling_off_ttl_seconds": { "type": "integer" }
  },
  "required": ["event_id", "agent_id", "timestamp", "target_resource", "action_executed"]
}
```
