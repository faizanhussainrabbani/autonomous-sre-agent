# Implementation Plan: Demo 1 and Demo 11

## Scope and Objectives
1. **Demo 1 (Missing Demo 1 - Basic Telemetry Fetch & Baseline)**: Establish the first demo in the sequence `scripts/live_demo_1_telemetry_baseline.py` to demonstrate the lowest level of Phase 1 — basic metric fetching and conversion to Canonical representation using existing LocalStack services.
2. **Demo 11 (Provider Coverage - Azure Operations)**: Create `scripts/live_demo_11_azure_operations.py` to exercise the Azure App Service and Azure Functions adapters from Phase 1.5, proving that the Cloud Operator abstraction seamlessly delegates to Azure models using mock Azure clients (since Azure LocalStack equivalents aren't natively available).

## All Areas Addressed
- **Scripts**: 
  - `scripts/live_demo_1_telemetry_baseline.py`
  - `scripts/live_demo_11_azure_operations.py`
- **Documentation**: 
  - Update `docs/operations/live_demo_guide.md` with Demo 1 and Demo 11.
  - Update `CHANGELOG.md` with accomplishments.

## Dependencies, Risks, and Assumptions
- **Assumption**: Mocking the Azure `web_client` is acceptable for Demo 11 implementation because maintaining active Azure cloud credentials is not viable for out-of-the-box local developer demos.
- **Risk**: The Azure client interfaces (`azure-mgmt-web`) require specific mock structures. The demo will need to stub `restart` and `begin_create_or_update` to simulate responses.
- **Dependency**: Demo 1 will rely on `boto3` and the LocalStack endpoint to fetch simulated metrics.

## File/Module Breakdown of Changes
1. **Create** `scripts/live_demo_1_telemetry_baseline.py`: Use `setup_cloudwatch` and `CloudWatchMetricsAdapter` to fetch `PutMetricData` points and display `CanonicalMetric` objects.
2. **Create** `scripts/live_demo_11_azure_operations.py`: Instantiate `AppServiceOperator` and `FunctionsOperator` with mock `web_client` objects and invoke their `restart` and `scale` methods.
3. **Edit** `docs/operations/live_demo_guide.md`: Append the execution logic and expected output for Demos 1 and 11.
4. **Edit** `CHANGELOG.md`: Log the final completion structure.
