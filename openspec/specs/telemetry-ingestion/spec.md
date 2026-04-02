# telemetry-ingestion Specification

## Purpose
TBD - created by archiving change phase-1-5-non-k8s-platforms. Update Purpose after archive.
## Requirements
### Requirement: Graceful eBPF Degradation
The telemetry ingestion pipeline SHALL gracefully handle environments where kernel-level eBPF collection is unsupported (e.g., Serverless), continuing to process application-level metrics and traces without failing health checks.

#### Scenario: Agent runs on AWS Lambda
- **WHEN** the `eBPFQuery` port is initialized on a `SERVERLESS` compute mechanism
- **THEN** it SHALL report `is_supported() == False`
- **AND** the signal correlator SHALL tag the `CorrelatedSignals` with `has_degraded_observability = True`
- **AND** anomaly detection MUST proceed using only OTel signals

