# Runbook: Agent Incident Response

**Status:** DRAFT
**Version:** 1.0.0

**Target Audience:** On-Call Engineers
**Scope:** When the SRE Agent itself is failing, crashing, or causing infrastructure harm.

## Overview
This runbook dictates actions to take when the "Automated Doctor" is the patient. 

## Scenario A: Agent Process Crashing (CrashLoopBackOff)

**Symptoms:** SRE Agent pods are constantly restarting. Alerts fire for "Agent Unavailability".
**Impact:** Telemetry is not being baseline-scored. Incidents will not be auto-remediated.
**Actions:**
1.  Check the pod logs: `kubectl logs -l app=sre-agent -n sre-system --previous`
2.  *Common Cause - Redis Timeout:* If the agent cannot reach the Lock Manager, it purposely crashes to avoid split-brain scenarios. Check Redis health.
3.  *Common Cause - Vector DB Auth:* If Pinecone/Weaviate credentials rotate and the agent isn't updated, the RAG pipeline fails on boot.
4.  **Mitigation:** If unresolvable in 15 minutes, scale agent replicas to 0 to stop log spam, and inform the team that SRE is fully manual until patched.

## Scenario B: Agent Causing Infrastructure Degradation (The Rogue Agent)

**Symptoms:** The agent is executing actions that are degrading overall system health (e.g., shutting down critical services, creating massive HPA spikes).
**Actions:**
1.  **IMMEDIATELY Execute the Kill Switch.** (See `runbook_kill_switch.md`). Do not wait to debug.
2.  Manually revert the GitOps changes the agent pushed via the ArgoCD UI.
3.  Perform a blameless post-mortem specifically focused on *why the Tier 1 Guardrails failed to catch the destructive action*.

## Scenario C: Knowledge Base Poisoning

**Symptoms:** The agent's RAG diagnoses suddenly become nonsensical, hallucinated, or highly inaccurate.
**Actions:**
1.  Demote the agent to Phase 1 (Shadow Mode) via the Operator Dashboard.
2.  Investigate recent vector embeddings. 
    *   Did a badly written, sarcastic post-mortem get indexed?
    *   Did a runbook format change, breaking the document chunker?
3.  **Mitigation:** Rebuild the vector database from a known-good backup or re-run the `kb_indexer` job against the verified `docs/` repository only.
