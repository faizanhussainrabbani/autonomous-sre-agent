# Phase Graduation Criteria

This document serves as the single source of truth for the SRE Agent's phase progression, detailing the specific entry criteria, exit criteria, and automatic regression triggers for each phase of operation.

## 1. Evaluation Methodology

*   **Evaluation Window:** 30 days rolling window or a minimum of 100 incidents, whichever comes first.
*   **Measurement:** Calculated continuously by the Orchestration & Governance Layer.
*   **Approval:** All phase transitions from Phase 1 -> Phase 2 -> Phase 3 require explicit human sign-off via the Operator Layer tracking UI, even if automated criteria are met. Automatic regressions happen immediately without human intervention.

## 2. Phase 1: OBSERVE (Shadow Mode)

*   **Entry Criteria:** Initial deployment of the agent in a new environment.
*   **Exit (Graduation) Criteria to Phase 2:**
    *   **Volume:** >100 incidents successfully logged and diagnosed.
    *   **Accuracy:** Agent diagnostic accuracy >=90% when compared to subsequent human actions.
    *   **Safety:** **Zero** critical false positive recommendations (e.g., recommending a destructive action that would have caused an outage).
    *   **Consecutive Success:** 100 consecutive incidents processed without a critical false positive.
*   **Regression Triggers:** N/A (Lowest phase)

## 3. Phase 2: ASSIST (Human-in-the-Loop)

*   **Entry Criteria:** Successful graduation from Phase 1.
*   **Exit (Graduation) Criteria to Phase 3:**
    *   **Resolution Rate:** Sev 3-4 automated resolution rate >=95%.
    *   **Safety:** Zero agent-worsened incidents (no actions that increased the severity or blast radius of an ongoing incident).
    *   **Accuracy:** Sev 1-2 diagnostic accuracy >=95%.
*   **Regression Triggers (Demote to Phase 1):**
    *   1+ instances of a destructive false positive action.
    *   Diagnostic accuracy drops below 85% over a 7-day rolling window.

## 4. Phase 3: AUTONOMOUS

*   **Entry Criteria:** Successful graduation from Phase 2.
*   **Exit (Graduation) Criteria to Phase 4:**
    *   **Performance:** 99% successful autonomous resolution of known incident typologies over a 90-day period.
    *   **Stability:** Zero SLA breaches caused by agent actions.
*   **Regression Triggers (Demote to Phase 2):**
    *   1+ instances of an agent-worsened incident.
    *   Resolution rate drops below 90% over a 7-day rolling window.
