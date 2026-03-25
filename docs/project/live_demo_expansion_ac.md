# Acceptance Criteria: Live Demos Expansion

## AC-1: Script Executability
**Given** an environment with Docker and LocalStack running (or able to run)
**When** the user executes `python ../../scripts/demo/live_demo_cloudwatch_enrichment.py` and `python ../../scripts/demo/live_demo_eventbridge_reaction.py`
**Then** the scripts must start, wait for user input (Enter to proceed), and progress through defined demo stages without crashing.

## AC-2: CloudWatch Enrichment Demo Validation
**Given** the execution of `live_demo_cloudwatch_enrichment.py`
**When** Phase metrics are pushed and the AlertEnricher is triggered
**Then** the console output must explicitly show that live metrics and logs were dynamically fetched before sending the payload for diagnosis.

## AC-3: EventBridge Reaction Demo Validation
**Given** the execution of `live_demo_eventbridge_reaction.py`
**When** an EventBridge mock payload is POSTed to the agent's `/api/v1/events/aws`
**Then** the script must assert or display that the internal EventStore captured the canonical domain event, making it available for Timeline construction.

## AC-4: Documentation Completeness
**Given** the repository's docs folder
**When** `docs/operations/live_demo_guide.md` is inspected
**Then** the document must include entries for both new demos, explaining their "Services", "Incident Pattern", "Learning Focus", and executable instructions.
