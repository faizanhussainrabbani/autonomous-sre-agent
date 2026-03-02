# Runbook: Agent Deployment & Upgrade

**Target Audience:** SREs, Platform Engineers
**Frequency:** Per release cycle

## Overview
This runbook details the procedure for deploying a new version of the SRE Agent or upgrading an existing deployment. Because the agent directly mutates infrastructure state, updates must be handled with the same caution as a tier-0 control plane service.

## Prerequisites
*   `kubectl` access to the management cluster with `cluster-admin` privileges.
*   Access to the GitOps configuration repository.
*   Approval from the Change Advisory Board (CAB) for production agents.

## Deployment Procedure

1.  **Preparation (Pre-Flight Checks):**
    *   Ensure the target cluster is not currently experiencing a Sev 1 or Sev 2 incident. *Never upgrade the agent during an active fire.*
    *   Verify the Redis/etcd datastore is healthy and accessible.
2.  **Configuration Update:**
    *   Update the `image.tag` in the `sre-agent` Helm chart within the GitOps repository.
    *   Create a Pull Request.
3.  **Deployment Execution:**
    *   Merge the PR. ArgoCD will automatically begin the deployment sync.
    *   **CRITICAL:** The agent deployment uses a `Recreate` strategy (or strict lock management if rolling) to ensure two different versions of the agent do not process the same telemetry concurrently.
4.  **Verification (Post-Flight):**
    *   Check agent pod logs for `Agent initialization complete` and successful connection to the Redis coordinator.
    *   Trigger a synthetic `Sev 4` anomaly (e.g., test log injected) and verify the agent detects and records it correctly.

## Rollback Procedure
If the new version crashes repeatedly or exhibits anomalous behavior (e.g., false positive spikes):
1.  Revert the Git commit that bumped the image tag.
2.  ArgoCD will downgrade the deployment to the previous stable version.
3.  Execute `runbook_incident_response.md` to investigate the failure.
