---
title: Executive Live Demo Showcase Plan
description: Evidence-based plan to present Autonomous SRE Agent capabilities to non-technical upper management using the current live demo suite.
author: SRE Agent Engineering Team
ms.date: 2026-03-31
ms.topic: how-to
keywords:
  - live demos
  - executive presentation
  - incident response
  - autonomous sre agent
estimated_reading_time: 15
---

## Purpose

This plan defines how to showcase product value to non-technical upper management with high signal and low technical noise.

Primary outcome:

* Convince leadership that the system reduces incident impact, shortens time to diagnosis, and keeps humans in control at critical decision points

Secondary outcomes:

* Establish a repeatable executive demo format
* Separate engineering validation demos from executive storytelling demos
* Reduce demo-time failure risk through preflight and rehearsal standards

## Accuracy Review of the Retrospective

The retrospective is mostly correct and directionally strong. The key claims below were validated against current scripts and guide content.

1. Claim: There are 19 live demos
Status: Accurate
Evidence: [docs/operations/live_demo_guide.md](../../../operations/live_demo_guide.md#L29), [docs/operations/live_demo_guide.md](../../../operations/live_demo_guide.md#L47)

2. Claim: Demos 14, 15, and 16 are not real live demos
Status: Accurate
Evidence: [scripts/demo/live_demo_14_disk_exhaustion.py](../../../scripts/demo/live_demo_14_disk_exhaustion.py#L10), [scripts/demo/live_demo_15_traffic_anomaly.py](../../../scripts/demo/live_demo_15_traffic_anomaly.py#L10), [scripts/demo/live_demo_16_xray_tracing_placeholder.py](../../../scripts/demo/live_demo_16_xray_tracing_placeholder.py#L11)

3. Claim: Demo 7 is a strong end-to-end showpiece
Status: Accurate
Evidence: [scripts/demo/live_demo_localstack_incident.py](../../../scripts/demo/live_demo_localstack_incident.py#L10), [scripts/demo/live_demo_localstack_incident.py](../../../scripts/demo/live_demo_localstack_incident.py#L682), [scripts/demo/live_demo_localstack_incident.py](../../../scripts/demo/live_demo_localstack_incident.py#L724)

4. Claim: Demo 8 is the best showpiece and demonstrates human override
Status: Mostly accurate
Evidence: [scripts/demo/live_demo_ecs_multi_service.py](../../../scripts/demo/live_demo_ecs_multi_service.py#L10), [scripts/demo/live_demo_ecs_multi_service.py](../../../scripts/demo/live_demo_ecs_multi_service.py#L989), [scripts/demo/live_demo_ecs_multi_service.py](../../../scripts/demo/live_demo_ecs_multi_service.py#L1068)

Important precision note:
The script demonstrates diagnosis, correlation, and severity override workflow. It does not explicitly call a remediation execution endpoint inside the demo flow.
Evidence: [scripts/demo/live_demo_ecs_multi_service.py](../../../scripts/demo/live_demo_ecs_multi_service.py#L869), [scripts/demo/live_demo_ecs_multi_service.py](../../../scripts/demo/live_demo_ecs_multi_service.py#L960), [scripts/demo/live_demo_ecs_multi_service.py](../../../scripts/demo/live_demo_ecs_multi_service.py#L999)

5. Claim: Demo 2 is a strong conceptual cascade demo
Status: Accurate
Evidence: [scripts/demo/live_demo_cascade_failure.py](../../../scripts/demo/live_demo_cascade_failure.py#L3), [scripts/demo/live_demo_cascade_failure.py](../../../scripts/demo/live_demo_cascade_failure.py#L274)

6. Claim: Demos 1, 6, and 13 are technical and weak for executive audiences
Status: Accurate
Evidence: [scripts/demo/live_demo_1_telemetry_baseline.py](../../../scripts/demo/live_demo_1_telemetry_baseline.py#L3), [scripts/demo/live_demo_http_optimizations.py](../../../scripts/demo/live_demo_http_optimizations.py#L3), [scripts/demo/live_demo_multi_agent_lock_protocol.py](../../../scripts/demo/live_demo_multi_agent_lock_protocol.py#L3)

7. Missing context in the retrospective: current suite has newer demos 17, 18, and 19
Status: True
Evidence: [docs/operations/live_demo_guide.md](../../../operations/live_demo_guide.md#L44), [docs/operations/live_demo_guide.md](../../../operations/live_demo_guide.md#L45), [docs/operations/live_demo_guide.md](../../../operations/live_demo_guide.md#L46)

## Executive Demo Portfolio Decision

Use this portfolio split for leadership presentations.

1. Primary executive showpieces
* Demo 7: [scripts/demo/live_demo_localstack_incident.py](../../../scripts/demo/live_demo_localstack_incident.py)
* Demo 8: [scripts/demo/live_demo_ecs_multi_service.py](../../../scripts/demo/live_demo_ecs_multi_service.py)
* Why: clear incident story, visible chain of events, diagnosis output, and human governance control

2. Optional executive add-on when asked about breadth
* Demo 19 excerpt only: [scripts/demo/live_demo_rag_error_evaluation.py](../../../scripts/demo/live_demo_rag_error_evaluation.py#L757)
* Why: scorecard view can support ROI and consistency messaging, but full marathon is too long for main stage

3. Engineering and internal audiences only
* Demo 1, 4, 6, 11, 12, 13, 17, 18
* Why: architecture, adapter, lock-manager, and protocol mechanics are valuable but too implementation-heavy for non-technical stakeholders

4. Remove from executive pathway immediately
* Demo 14, 15, 16
* Why: payload printouts and placeholder scope do not demonstrate autonomous behavior

## End-to-End Delivery Plan

### Phase 1: Message Architecture (2 to 3 days)

1. Define executive narrative in business language
* Incident risk threatens revenue and customer trust
* Agent detects and diagnoses faster than manual triage
* Humans remain in control for high-risk decisions

2. Define three business proof points to repeat in every session
* Mean time to detect reduction
* Mean time to diagnose reduction
* Controlled intervention with explicit operator authority

3. Build one-slide value framing for each selected demo
* Demo 7: Single critical service failure contained quickly
* Demo 8: Multi-service cascade triaged with human override governance

### Phase 2: Demo Hardening (4 to 5 days)

1. Build an executive launcher script that runs only Demo 7 and Demo 8 in controlled sequence

2. Add executive output mode flags to reduce noise
* Keep only phase banners, key state transitions, and diagnosis summary
* Hide package checks and non-critical setup logs

3. Pre-seed deterministic resources for faster startup
* Avoid visible infrastructure warm-up where possible
* Keep startup under 3 minutes before audience joins

4. Freeze script versions for presentation branch
* Lock demo scripts and dependencies for a specific release tag

5. Remove weak demos from executive index
* Relocate 14, 15, and 16 to fixtures or mock directory
* Keep historical references only in engineering docs

### Phase 3: Executive Story Packaging (2 to 3 days)

1. Build presenter talk track for each phase transition

2. Prepare visual side panel for each live phase
* Current incident status
* What the agent is doing now
* Business impact if not handled

3. Add one-page appendix for governance and safety controls
* Severity override
* Human authority boundary
* Action halt behavior

### Phase 4: Rehearsal and Go/No-Go (2 days)

1. Conduct at least three full dry runs
* One ideal run
* One degraded run with delayed component startup
* One fallback run using recorded output package

2. Apply go/no-go gates
* 100% successful dry runs in target environment
* No uncaught traceback or setup interruption visible to audience
* Total runtime within target window

3. Validate fallback assets
* Timestamped backup logs
* Pre-recorded screen capture of successful run
* Printed scorecard and diagnosis artifacts

### Phase 5: Live Session Execution (presentation day)

1. Start environment 30 minutes early

2. Run preflight checklist 15 minutes early

3. Deliver scripted flow and avoid ad-hoc deep technical detours

4. Close with quantified outcomes and next-step decision request

## Standard Executive Session Flow (30 minutes)

1. Minute 0 to 4: Business framing
* Explain what outage risk means in revenue, operations, and trust terms

2. Minute 4 to 14: Demo 7 live narrative
* Trigger incident chain
* Show diagnosis output and recommended path
* State business effect of rapid triage

3. Minute 14 to 25: Demo 8 live narrative
* Trigger cascade across two services
* Show correlated diagnosis
* Execute severity override as human governance control

4. Minute 25 to 28: Optional scorecard snippet from Demo 19
* Use only aggregate evaluation summary if leadership asks about consistency at scale

5. Minute 28 to 30: Close
* Summarize measurable value
* Confirm proposed rollout or pilot decision

## Demo Operations Runbook

### Pre-session checklist

1. Validate dependencies and credentials
2. Confirm LocalStack health
3. Confirm required ports are free
4. Confirm SKIP_PAUSES behavior for rehearsal and interactive mode for live narration
5. Confirm bridge host configuration for runtime topology

### In-session operator protocol

1. Keep one presenter and one operator role
2. If a step exceeds 45 seconds, narrate expected state and move to fallback artifact
3. Never debug package installation live

### Fallback protocol

1. If Demo 7 fails before diagnosis output, switch to validated recording and continue narrative
2. If Demo 8 override endpoint is unavailable, show latest successful override artifact from rehearsal package
3. Continue Q and A with business outcomes, not terminal debugging

## Success Metrics

Track these metrics after every executive session.

1. Delivery reliability
* Full live sequence completion rate
* Time to first meaningful output

2. Clarity and stakeholder confidence
* Post-session leadership confidence score
* Number of requests for follow-up pilot discussions

3. Product value perception
* Perceived reduction in incident handling risk
* Perceived adequacy of human governance controls

## Immediate Actions for the Next 10 Business Days

1. Day 1 to 2
* Approve executive demo scope and lock Demo 7 plus Demo 8 as mandatory

2. Day 3 to 5
* Implement executive launcher and output-noise controls
* Relocate Demo 14 to 16 out of executive pathways

3. Day 6 to 7
* Build and review presenter talk track and visuals

4. Day 8 to 9
* Run three rehearsals and collect timing plus failure points

5. Day 10
* Final go/no-go review and leadership session scheduling

## Final Recommendation

Start executive showcases with Demo 7 and Demo 8 only.

Treat Demo 14, 15, and 16 as internal mock artifacts, not live demonstrations.

Use Demo 19 only as a short evidence add-on for scale questions.

This approach maximizes perceived product maturity while minimizing avoidable demo risk.