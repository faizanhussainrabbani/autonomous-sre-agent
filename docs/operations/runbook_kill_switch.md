# Runbook: Agent Kill Switch Activation

**Target Audience:** Incident Commanders, On-Call Engineers
**Emergency Contact:** SRE Platform Team

## Overview
The "Kill Switch" is the ultimate safety mechanism enforcing Human Supremacy. Activating the kill switch immediately halts all autonomous actions, PR generation, and diagnostic processing across the entire fleet.

## When to use
*   The agent is caught in an oscillation loop (e.g., repeatedly scaling a service up and down).
*   The agent issues a destructive, unapproved action outside of its guardrails.
*   A major, unprecedented infrastructure event is occurring, and human operators require absolute manual control without agent noise.

## Activation Procedure

### Option 1: Via Slack (Preferred)
1.  In the `#sre-alerts` channel, type `/sre-agent halt`
2.  The bot will respond with a modal.
3.  Enter the reason (e.g., "Agent causing false restarts on API gateway").
4.  Select Halt Mode:
    *   **Soft-Stop:** Prevents any *new* actions from starting, but allows currently executing remediations (e.g., a rollout restart) to definitively complete or rollback cleanly. (Safer for state consistency).
    *   **Hard-Stop:** Instantly severs the agent pipeline. In-flight operations are abandoned mid-execution. Use only if the current action is actively destroying infrastructure.
5.  Click **Confirm Halt**.

### Option 2: Via API (Fallback)
If Slack is down, use `curl` to hit the management endpoint:
```bash
curl -X POST https://sre-agent.internal/api/v1/system/halt \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"reason": "Emergency manual override", "requested_by": "jdoe", "mode": "hard"}'
```

### Verification
*   The Operator Layer dashboard will flash a global **`HALTED`** banner.
*   Agent pods will log: `FATAL: Global kill switch activated. Yielding all locks.`

## Recovery & Resume Procedure
1.  Once the underlying issue is resolved and the agent's behavior is diagnosed, the agent can be resumed.
2.  Resumption requires dual-authorization.
3.  Hit the resume endpoint:
```bash
curl -X POST https://sre-agent.internal/api/v1/system/resume \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"primary_approver": "jdoe", "secondary_approver": "asmith", "review_notes": "Bug patched in v1.2"}'
```
