# Plan: AWS Metric Generation Integration Testing

## 1. Objective
Close the testing gap identified in Phase 2.3 by implementing a real AWS metric generation integration test. This test will leverage LocalStack to emulate AWS CloudWatch, allowing us to actively generate/publish metrics via `boto3` and verify that the `CloudWatchMetricsAdapter` successfully queries and transforms them into our `CanonicalMetric` models.

## 2. Scope
- Add a new integration test file: `tests/integration/test_cloudwatch_live_integration.py` (or extend `test_aws_operators_integration.py` context).
- Utilize LocalStack (Community or Pro, via Docker) to provide a real HTTP endpoint for CloudWatch.
- Create an ephemeral `boto3.client("cloudwatch", endpoint_url=...)` connected to LocalStack.

## 3. Implementation Steps
1. **LocalStack Fixture:** Ensure a `pytest` fixture exists (or create one) to spin up/verify LocalStack is accessible (similar to `test_aws_operators_integration.py`).
2. **Metric Publishing:** Use `PutMetricData` to publish a known, discrete test metric (e.g., `lambda_errors`) to a specific namespace (`AWS/Lambda`) mapped in `METRIC_MAP`.
3. **Synchronization Strategy:** Introduce a minor polling or sleep mechanism, as CloudWatch aggregation (even in LocalStack) requires a moment to become queryable via `GetMetricData`.
4. **Adapter Execution:** Initialize the `CloudWatchMetricsAdapter` with the LocalStack-bound boto3 client. Call `adapter.query()` or `adapter.query_instant()`.
5. **Assertion:** Verify the results:
   - Returns a list of `CanonicalMetric`.
   - `provider_source` is `cloudwatch`.
   - `value` matches the published data.
   - `metric_name` logic successfully resolves the expected Canonical identity.

## 4. Alignment with Standards
- Needs to be async-compatible / thread-safe for tests.
- Documentation and file structure must align with FAANG standards (clear docstrings, specific ARNs/URIs emulation).
- Must adhere strictly to the ports/adapters hexagon pattern (test uses the adapter directly, overriding its boto3 client via DI).

## 5. Deliverables
- `tests/integration/test_cloudwatch_live_integration.py`
- Setup logic integrated with existing `pytest` infrastructure.
