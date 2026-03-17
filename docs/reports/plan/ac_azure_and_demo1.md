# Acceptance Criteria: Demo 1 and Demo 11

## 1. Demo 1: Telemetry Baseline (live_demo_1_telemetry_baseline.py)
- **AC 1.1**: The script must successfully push mock `CPUUtilization` metrics to LocalStack CloudWatch.
- **AC 1.2**: The script must successfully retrieve the pushed metrics using the `CloudWatchMetricsAdapter`.
- **AC 1.3**: The script must output `CanonicalMetric` models with valid metadata (timestamp, value, unit, name).
- **AC 1.4**: The script must execute without unhandled exceptions or connection errors.

## 2. Demo 11: Azure Operations (live_demo_11_azure_operations.py)
- **AC 2.1**: The script must correctly inject mock `azure-mgmt-web` clients into `AppServiceOperator` and `FunctionsOperator`.
- **AC 2.2**: The script must successfully execute the `restart` operation for App Service using the abstract `CloudOperatorPort`.
- **AC 2.3**: The script must successfully call `scale` (e.g., updating site configs) for Azure Functions using the abstract `CloudOperatorPort`.
- **AC 2.4**: The script must execute and output the mocked behaviors gracefully.

## 3. Documentation
- **AC 3.1**: `docs/operations/live_demo_guide.md` must contain sections for "Demo 1" and "Demo 11" with execution details.
- **AC 3.2**: `CHANGELOG.md` must document the updates accurately mapping back to the analysis report.