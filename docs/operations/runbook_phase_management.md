# Runbook: Phase Management

**Target Audience:** SRE Leadership, Platform Managers
**Reference:** [Graduation Criteria](graduation_criteria.md)

## Overview
This runbook covers the manual procedure for graduating the SRE Agent from one Phase to the next (e.g., Shadow Mode -> Assist Mode), as well as handling automatic regression alerts.

## 1. Phase Graduation (Manual Promotion)

While the Orchestration layer calculates metrics automatically, promotion requires human validation.

1.  **Review Metrics:**
    *   Navigate to the Operator Layer Dashboard -> "Phase Tracker".
    *   Verify the required metric thresholds (e.g., >90% accuracy, >100 incidents) are colored Green.
2.  **Audit Sample set:**
    *   Randomly select 5 incidents handled during the evaluation window.
    *   Verify the agent's proposed diagnostic citations match human expectations.
3.  **Execute Promotion:**
    *   Click "Promote to Phase X" in the Operator Dashboard.
    *   This triggers a configuration update in the PostgreSQL metadata store, changing the global authorized state.
    *   Announce the promotion in the `#engineering-announcements` Slack channel, detailing the new capabilities the agent now possesses.

## 2. Handling Automatic Regression

If the agent violates safety criteria (e.g., resolution rate drops below 90% in Phase 3), the Orchestration Layer will automatically demote it to the previous phase and page the on-call engineer.

1.  **Acknowledge Page:** Acknowledge the PagerDuty alert "Agent Auto-Regression Triggered".
2.  **Investigate the Trigger:**
    *   Open the Operator Dashboard. The banner will indicate the regression reason (e.g., "Demoted to Phase 2: Agent Worsened Incident ID-10492").
3.  **Root Cause the Agent Failure:**
    *   Why did the agent fail? Was the RAG vector DB poisoned? Was the baselining ML model drifting?
    *   Create a Jira ticket to patch the agent's logic.
4.  **Re-Evaluation:**
    *   The agent must serve a new 30-day evaluation window in the lower phase before it can be manually promoted again.
