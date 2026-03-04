## ADDED Requirements

### Requirement: AsyncAPI Telemetry Event Definitions
The system SHALL document all asynchronous event streams (e.g., eBPF events, OTel metrics) consumed by the agent using the standard AsyncAPI specification format.

#### Scenario: Validating an event schema
- **WHEN** a new telemetry event type is introduced to the agent's ingestion pipeline
- **THEN** an `asyncapi.yaml` file must exist or be updated in `docs/architecture/api_contracts/` defining its schema and payload structure
