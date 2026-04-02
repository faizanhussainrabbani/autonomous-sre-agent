## ADDED Requirements

### Requirement: Serverless Cold Start Suppression
The anomaly detection engine SHALL suppress latency and error rate alerts that occur during the initialization phase of a serverless compute instance.

#### Scenario: Lambda Cold Start
- **WHEN** a new metric arrives with `compute_mechanism` set to `SERVERLESS`
- **AND** the metric timestamp is within the first 15 seconds of the instance's initialization
- **THEN** the anomaly detector SHALL ignore any latency spikes crossing the standard sigma threshold
- **AND** log the suppression event with reason `cold_start`

### Requirement: Serverless OOM Exemption
The anomaly detection engine SHALL NOT fire Memory Pressure alerts for serverless compute components, relying instead on the platform's native invocation error reporting.

#### Scenario: Memory exhaustion on Azure Functions
- **WHEN** a metric indicating memory usage > 85% arrives
- **AND** the `compute_mechanism` is `SERVERLESS`
- **THEN** the memory pressure anomaly rule SHALL NOT trigger
- **AND** the system SHALL instead monitor for `InvocationError` surges correlated to memory limit configurations
