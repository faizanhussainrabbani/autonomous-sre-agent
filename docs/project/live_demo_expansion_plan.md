# Implementation Plan: Expansion of Live Demos

## 1. Scope and Objectives
The objective of this initiative is to expand the current suite of LocalStack-based live demonstrations (`live_demo_localstack_aws.py`, `live_demo_localstack_incident.py`) to cover newly introduced features from **Phase 2.3** (AWS Data Collection Improvements). 

### Demos to Implement:
1. **`scripts/live_demo_cloudwatch_enrichment.py`**
   - **Focus:** Showcases the `AlertEnricher` and `CloudWatchMetricsAdapter`.
   - **Scenario:** Simulates an anomaly, publishes real mock metrics to LocalStack CloudWatch, and triggers the Enrichment pipeline to demonstrate live data fetching + log fetching before diagnosis.
2. **`scripts/live_demo_eventbridge_reaction.py`**
   - **Focus:** Showcases the new `/api/v1/events/aws` EventBridge webhook and `TimelineConstructor`.
   - **Scenario:** Simulates state change events (e.g., ECS Task OOM or Lambda deployment) pushed to the EventBridge webhook, verifying that the diagnostic pipeline correctly correlates and layers these events onto the incident timeline.

### Documentation Requirements:
- Update `docs/operations/live_demo_guide.md` with operational instructions for the new scripts.
- Create standalone Markdown guides if required, adhering to FAANG standards.

## 2. File/Module Breakdown of Changes
1. `scripts/live_demo_cloudwatch_enrichment.py` (New Script)
2. `scripts/live_demo_eventbridge_reaction.py` (New Script)
3. `docs/operations/live_demo_guide.md` (Update)

## 3. Dependencies, Risks, and Assumptions
- **Dependency:** Requires Docker and `localstack/localstack:latest`.
- **Dependency:** Requires `boto3` and `pytest-asyncio` components (available in `.venv`).
- **Risk:** LocalStack latency for metric aggregation may cause race conditions. Addressed via bounded sleeps.
- **Assumption:** The `sre_agent` backend is properly mocked or runs embedded in the script similar to existing demos.
- **Assumption:** Both scripts should be executable directly via `python scripts/<script_name>.py`.

## 4. Execution Steps
1. Review Plan against standards.
2. Create Acceptance Criteria.
3. Scaffold and build `live_demo_cloudwatch_enrichment.py`.
4. Scaffold and build `live_demo_eventbridge_reaction.py`.
5. Update `docs/operations/live_demo_guide.md`.
6. Run both scripts locally to validate terminal output.
7. Update `CHANGELOG.md`.
