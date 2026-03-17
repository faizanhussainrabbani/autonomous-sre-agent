# Acceptance Criteria: AWS Metric Generation Integration Testing

## AC-1: LocalStack Integration
**Given** an active LocalStack instance running in the test environment
**When** the integration test provisions a `cloudwatch` boto3 client pointing to it
**Then** the client successfully connects without authentication or routing errors.

## AC-2: Actual Metric Publication
**Given** the LocalStack `cloudwatch` client
**When** the test uses `PutMetricData` to publish a known metric (e.g., `lambda_errors`) to the `AWS/Lambda` namespace
**Then** LocalStack HTTP response confirms a 200 OK acceptance of the metric data.

## AC-3: End-to-End Query Verification
**Given** previously published metric data in LocalStack
**When** the integration test executes `CloudWatchMetricsAdapter.query(...)` over that time window
**Then** the returned response must contain the newly published data point(s) mapped accurately to the `CanonicalMetric` schema.

## AC-4: Resiliency/Timing Robustness
**Given** the eventual consistency nature of CloudWatch metrics
**When** querying immediately after publication
**Then** the test avoids flakiness by implementing a minor, bounded polling or jitter/wait strategy to ensure the metric has settled in LocalStack before asserting failure.

## AC-5: Independent Execution
**Given** a clean test execution environment
**When** running `pytest tests/integration/test_cloudwatch_live_integration.py`
**Then** the test completes successfully 100% of the time, properly tearing down or ignoring stale state across runs.