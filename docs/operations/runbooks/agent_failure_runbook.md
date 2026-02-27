# Runbook: Agent Failure & Rogue Action

**Service:** Autonomous SRE Agent
**Runbook Owner:** Core Infrastructure Team

This document outlines the standard operating procedures when the Autonomous SRE Agent is experiencing a failure (crashing, disconnected) or is exhibiting rogue behavior (e.g., oscillating remediations, dangerous false positives).

---

## Scenario A: The Agent is Exhibiting Destructive Behavior

If the agent is systematically restarting healthy pods, scaling down critical services, or rolling back good deployments during a false positive anomaly.

### Immediate Action: Engage the Global Kill Switch
Do not attempt to debug the Anomaly Detection heuristics while the agent is active. You must immediately halt the control plane.

1.  **Via Slack (Preferred):**
    *   In the `#incidents-platform` channel, run the slash command:
        `/sre-agent halt "Rogue behavior on user-auth service"`
2.  **Via API (Fallback):**
    *   If Slack is down, use `curl` from the Bastion host using your internal admin token:
        ```bash
        curl -X POST https://sre-agent.internal/api/v1/system/halt -H "Authorization: Bearer $B_TOKEN" -d '{"reason":"rogue action"}'
        ```
### Verification
*   Check the Agent Dashboard. The status banner MUST be red and read `PHASE: KILLED`.
*   Ensure the `sre_agent_active_remediations` metric drops to 0.

---

## Scenario B: Agent is "Stuck" (Deadlock in Redis)

If the agent has acquired a distributed lock on a service (to prevent other agents from acting) but crashed mid-remediation without releasing the lock.

### Symptoms
*   The agent is online, but ignoring a Sev 2/3 incident.
*   The logs show: `WARN: Cannot acquire lock for service user-auth; owned by session 1234a.`

### Immediate Action: Clear the Redis Lock Manually
1.  Connect to the primary Redis Management cluster for the agent namespace.
2.  Scan for the stale lock:
    ```redis
    SCAN 0 MATCH "sre_lock:*"
    ```
3.  Delete the frozen key. **WARNING: Ensure the pod holding that lock is actually dead before doing this.**
    ```redis
    DEL "sre_lock:user-auth"
    ```

---

## Scenario C: Total LLM Provider Outage

If the external API providing LLM inference or Vector DB similarity search is down, the agent cannot diagnose novel issues.

### Symptoms
*   Error logs showing `TimeoutException` or `503 Service Unavailable` from `ports/llm.py` or the VectorDB adapter.
*   Agent transitions automatically to `PHASE: ASSIST` mode due to continuous validation failures.

### Immediate Action: Acknowledge and Route to Humans
1.  The agent acts safely in this state by failing closed (routing to PagerDuty). No infrastructure is at risk from the agent itself.
2.  Update the PagerDuty schedules to expect a 20% higher volume of alerts, as the Tier-1 auto-remediation deflection shield is currently offline.
