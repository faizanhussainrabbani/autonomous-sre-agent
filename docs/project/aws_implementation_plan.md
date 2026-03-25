---
title: AWS Data Collection Implementation Plan
description: Detailed task list and acceptance criteria for all 10 AWS data collection improvements
author: GitHub Copilot
ms.date: 2025-07-15
ms.topic: reference
keywords:
  - aws
  - cloudwatch
  - implementation
  - acceptance criteria
estimated_reading_time: 15
---

## Scope

Implements all 10 improvement areas from
[aws_data_collection_improvements.md](../operations/aws_data_collection_improvements.md)
aligned to the gaps identified in
[aws_data_collection_review.md](../reports/aws_data_collection_review.md).

## Task List

### T1: Configuration and Settings Layer

**Files modified:**

* [src/sre_agent/config/settings.py](../../src/sre_agent/config/settings.py)
* [config/agent.yaml](../../config/agent.yaml)

**Changes:**

* Add `CloudWatchConfig` dataclass with `region`, `metric_poll_interval_seconds`,
  `log_fetch_window_minutes`, `log_filter_pattern`, `metric_streams_enabled`
* Add `EnrichmentConfig` dataclass with `fetch_metrics`, `fetch_logs`, `fetch_traces`,
  `fetch_resource_metadata` booleans
* Add `AWSHealthConfig` dataclass with `enabled`, `poll_interval_seconds`, `regions`
* Extend `AgentConfig` with `cloudwatch`, `enrichment`, `aws_health` fields
* Add feature flags: `cloudwatch_adapter`, `bridge_enrichment`, `background_polling`,
  `eventbridge_integration`, `aws_health_polling`, `xray_adapter`
* Update `agent.yaml` with new sections and defaults
* Update `_from_dict()` parser to handle new config sections
* Update `validate()` to check CloudWatch config when `cloud_provider = aws`

### T2: CloudWatch Metrics Adapter (Area 2)

**Files created:**

* `src/sre_agent/adapters/telemetry/cloudwatch/__init__.py`
* `src/sre_agent/adapters/telemetry/cloudwatch/metrics_adapter.py`

**Implements:** `MetricsQuery` port from `ports/telemetry.py`

**Key behaviors:**

* `METRIC_MAP` translating canonical metric names to CloudWatch (Namespace, MetricName) pairs
* `query()` calls `GetMetricData` with `MetricDataQueries`, returns `list[CanonicalMetric]`
* `query_instant()` calls `GetMetricData` with 5-min window, returns latest data point
* `list_metrics()` calls `ListMetrics` filtered by namespace/dimension
* `health_check()` calls `ListMetrics` with limit=1 to verify connectivity
* Dimensions derived from service name (FunctionName for Lambda, ServiceName for ECS)
* `close()` is a no-op (boto3 clients are not async)

### T3: CloudWatch Logs Adapter (Area 3)

**File created:**

* `src/sre_agent/adapters/telemetry/cloudwatch/logs_adapter.py`

**Implements:** `LogQuery` port from `ports/telemetry.py`

**Key behaviors:**

* `_resolve_log_group(service)` maps service name to CloudWatch Log Group
  (`/aws/lambda/{service}`, `/ecs/{cluster}/{service}`)
* `query_logs()` calls `FilterLogEvents` with severity/trace_id/search_text filters
* `query_by_trace_id()` calls `FilterLogEvents` with trace ID as `filterPattern`
* Parses CloudWatch log event JSON into `CanonicalLogEntry` objects
* `health_check()` calls `DescribeLogGroups` with limit=1

### T4: X-Ray Trace Adapter (Area 6)

**File created:**

* `src/sre_agent/adapters/telemetry/cloudwatch/xray_adapter.py`

**Implements:** `TraceQuery` port from `ports/telemetry.py`

**Key behaviors:**

* `get_trace(trace_id)` calls `BatchGetTraces` with single trace ID
* `query_traces()` calls `GetTraceSummaries` with `FilterExpression` for service name
* Parses X-Ray segments/subsegments into `TraceSpan` objects within `CanonicalTrace`
* Maps X-Ray fault/error/throttle flags to canonical status codes
* `health_check()` calls `GetTraceSummaries` with 1-minute window

### T5: CloudWatch Telemetry Provider (Composite)

**File created:**

* `src/sre_agent/adapters/telemetry/cloudwatch/provider.py`

**Implements:** `TelemetryProvider` from `ports/telemetry.py`

**Key behaviors:**

* Assembles `CloudWatchMetricsAdapter`, `CloudWatchLogsAdapter`, `XRayTraceAdapter`
* Exposes `metrics`, `traces`, `logs`, `dependency_graph` properties
* `dependency_graph` returns a placeholder (X-Ray Service Map in future)
* `health_check()` checks all three backends
* `close()` is a no-op (boto3 clients)
* Constructed from `CloudWatchConfig`

### T6: Resource Metadata Fetcher (Area 8)

**File created:**

* `src/sre_agent/adapters/cloud/aws/resource_metadata.py`

**Key behaviors:**

* `fetch_lambda_context(function_name)` calls `GetFunctionConfiguration`
  returning memory_mb, timeout_s, runtime, reserved_concurrency, last_modified
* `fetch_ecs_context(cluster, service)` calls `DescribeServices`
  returning desired_count, running_count, pending_count, task_definition, deployment_status
* `fetch_ec2_asg_context(asg_name)` calls `DescribeAutoScalingGroups`
  returning desired_capacity, min_size, max_size, instances, health_status
* Returns `dict[str, Any]` for injection into `AnomalyAlert.correlated_signals`
* Graceful error handling with structlog warnings

### T7: Bridge Enrichment (Area 1 + Area 10)

**File modified:**

* `../../scripts/demo/localstack_bridge.py`

**New file:**

* `src/sre_agent/adapters/cloud/aws/enrichment.py`

**Key behaviors:**

* `AlertEnricher` class accepts boto3 clients for CloudWatch and Logs
* `enrich(alarm_data)` fetches:
  * 30-minute metric trend via `GetMetricData`
  * Recent error logs via `FilterLogEvents`
  * Resource metadata via `ResourceMetadataFetcher`
* Computes real `deviation_sigma` from metric time series: `abs(current - mean) / std`
* Extracts actual `current_value` from metric data (not threshold)
* Computes `baseline_value` as mean of historical data points
* Builds fully populated `CorrelatedSignals` object
* Bridge calls enricher before forwarding to agent
* Falls back to hardcoded values if enrichment fails

### T8: Background Polling Agent (Area 5)

**File created:**

* `src/sre_agent/domain/detection/polling_agent.py`

**Key behaviors:**

* `MetricPollingAgent` runs as async background task
* Polls `CloudWatchMetricsAdapter.query_instant()` every N seconds (configurable)
* Feeds values into `BaselineService.ingest()` for baseline establishment
* Runs `AnomalyDetector.detect()` on each batch
* Publishes `AnomalyDetected` domain events for any alerts
* Configurable service + metric watchlist from `agent.yaml`
* Graceful shutdown via cancellation token

### T9: EventBridge Integration (Area 7)

**Files created:**

* `src/sre_agent/api/rest/events_router.py`

**Key behaviors:**

* `POST /api/v1/events/aws` endpoint receives EventBridge events
* Parses event source (aws.lambda, aws.ecs, aws.rds, aws.iam)
* Converts to `CanonicalEvent` with appropriate `event_type`
* Checks if affected resource has active incidents
* Stores event for correlation with future diagnoses

### T10: AWS Health Events (Area 9)

**File created:**

* `src/sre_agent/domain/detection/health_monitor.py`

**Key behaviors:**

* `AWSHealthMonitor` polls `health:DescribeEvents` every 5 minutes
* Filters for open/upcoming issues and scheduled changes in configured regions
* Stores active health events in memory
* Provides `get_active_events(region, service)` for context injection
* Injects health context into `DiagnosisRequest` supplementary data

### T11: Wiring and Router Updates

**Files modified:**

* `src/sre_agent/api/rest/diagnose_router.py`
* `src/sre_agent/api/main.py`
* `src/sre_agent/adapters/intelligence_bootstrap.py`

**Key behaviors:**

* `diagnose_router` populates `correlated_signals` from `alert.correlated_signals`
  (passed through from bridge) into `DiagnosisRequest`
* Register EventBridge router in `main.py`
* Bootstrap optionally creates CloudWatch provider when `cloud_provider = aws`

### T12: Unit Tests

**Files created:**

* `tests/unit/adapters/test_cloudwatch_metrics_adapter.py`
* `tests/unit/adapters/test_cloudwatch_logs_adapter.py`
* `tests/unit/adapters/test_xray_adapter.py`
* `tests/unit/adapters/test_cloudwatch_provider.py`
* `tests/unit/adapters/test_resource_metadata.py`
* `tests/unit/adapters/test_enrichment.py`
* `tests/unit/domain/test_polling_agent.py`
* `tests/unit/domain/test_health_monitor.py`
* `tests/unit/adapters/test_events_router.py`

### T13: Integration and E2E Tests

**Files created:**

* `tests/integration/test_cloudwatch_integration.py`
* `tests/e2e/test_enriched_diagnosis_e2e.py`

## Acceptance Criteria

### AC-CW-1: CloudWatch Metrics Adapter

* AC-CW-1.1: `CloudWatchMetricsAdapter` implements all three `MetricsQuery` methods
* AC-CW-1.2: `query()` returns `list[CanonicalMetric]` with correct timestamps, values, and labels
* AC-CW-1.3: `METRIC_MAP` contains mappings for Lambda (Errors, Duration, Throttles, Invocations),
  ECS (CpuUtilized, MemoryUtilized, RunningTaskCount), ALB (TargetResponseTime, RequestCount),
  and ASG (GroupInServiceInstances)
* AC-CW-1.4: `health_check()` returns `True` when CloudWatch is reachable, `False` otherwise
* AC-CW-1.5: All returned metrics have `provider_source = "cloudwatch"`
* AC-CW-1.6: Service name is correctly mapped to CloudWatch dimensions

### AC-CW-2: CloudWatch Logs Adapter

* AC-CW-2.1: `CloudWatchLogsAdapter` implements both `LogQuery` methods
* AC-CW-2.2: `query_logs()` correctly filters by severity, trace_id, and search_text
* AC-CW-2.3: Log group resolution maps Lambda services to `/aws/lambda/{service}`
* AC-CW-2.4: Returned logs have `provider_source = "cloudwatch"` and correct severity
* AC-CW-2.5: `query_by_trace_id()` searches for trace ID in log messages
* AC-CW-2.6: `health_check()` returns `True/False` based on CloudWatch Logs connectivity

### AC-CW-3: X-Ray Trace Adapter

* AC-CW-3.1: `XRayTraceAdapter` implements both `TraceQuery` methods
* AC-CW-3.2: `query_traces()` uses `FilterExpression` with service name
* AC-CW-3.3: X-Ray segments/subsegments are correctly parsed into `TraceSpan` objects
* AC-CW-3.4: Fault/error/throttle flags map to appropriate HTTP status codes
* AC-CW-3.5: Returned traces have `provider_source = "cloudwatch"`
* AC-CW-3.6: `health_check()` returns `True/False` based on X-Ray connectivity

### AC-CW-4: CloudWatch Telemetry Provider

* AC-CW-4.1: `CloudWatchProvider` implements `TelemetryProvider` interface
* AC-CW-4.2: `metrics`, `traces`, `logs` properties return correct adapter instances
* AC-CW-4.3: `health_check()` checks all three backends
* AC-CW-4.4: `name` property returns `"cloudwatch"`

### AC-CW-5: Resource Metadata Fetcher

* AC-CW-5.1: `fetch_lambda_context()` returns memory_mb, timeout_s, runtime, last_modified
* AC-CW-5.2: `fetch_ecs_context()` returns desired_count, running_count, task_definition
* AC-CW-5.3: `fetch_ec2_asg_context()` returns desired_capacity, min_size, max_size
* AC-CW-5.4: All methods handle `ClientError` gracefully with structlog warnings
* AC-CW-5.5: Returns empty dict on failure (never raises to caller)

### AC-CW-6: Bridge Enrichment

* AC-CW-6.1: Bridge calls `AlertEnricher.enrich()` before forwarding to agent
* AC-CW-6.2: `correlated_signals` is populated with metric trend data (not `None`)
* AC-CW-6.3: `current_value` reflects actual metric value (not alarm threshold)
* AC-CW-6.4: `baseline_value` reflects computed mean from metric time series
* AC-CW-6.5: `deviation_sigma` is computed as `abs(current - mean) / std_dev`
* AC-CW-6.6: Enrichment gracefully falls back to defaults on CloudWatch API failure
* AC-CW-6.7: Log entries from CloudWatch Logs are included in `correlated_signals.logs`
* AC-CW-6.8: Resource metadata is included in alert platform_metadata

### AC-CW-7: Background Polling Agent

* AC-CW-7.1: `MetricPollingAgent` polls at configurable interval
* AC-CW-7.2: Each poll feeds values into `BaselineService.ingest()`
* AC-CW-7.3: Each poll runs `AnomalyDetector.detect()` and emits events for alerts
* AC-CW-7.4: Graceful shutdown via cancellation
* AC-CW-7.5: Service + metric watchlist is configurable via `agent.yaml`

### AC-CW-8: EventBridge Integration

* AC-CW-8.1: `POST /api/v1/events/aws` accepts EventBridge event payloads
* AC-CW-8.2: Events from aws.lambda, aws.ecs, aws.rds, aws.iam are parsed
* AC-CW-8.3: Events are converted to `CanonicalEvent` with correct `event_type`
* AC-CW-8.4: Invalid payloads return 422 with descriptive error

### AC-CW-9: AWS Health Events

* AC-CW-9.1: `AWSHealthMonitor` polls at configurable interval
* AC-CW-9.2: Active health events are stored and queryable
* AC-CW-9.3: `get_active_events()` filters by region and service
* AC-CW-9.4: Handles `SubscriptionRequiredException` gracefully (Business/Enterprise only)

### AC-CW-10: Configuration

* AC-CW-10.1: `CloudWatchConfig` dataclass exists with all required fields
* AC-CW-10.2: `agent.yaml` contains CloudWatch, enrichment, and health sections
* AC-CW-10.3: Feature flags control each new capability independently
* AC-CW-10.4: `validate()` checks CloudWatch region when `cloud_provider = aws`

### AC-CW-11: Wiring

* AC-CW-11.1: `diagnose_router` passes `correlated_signals` from alert to `DiagnosisRequest`
* AC-CW-11.2: EventBridge router is registered in `main.py`
* AC-CW-11.3: Bootstrap creates CloudWatch provider when configured

### AC-CW-12: Test Coverage

* AC-CW-12.1: Every new adapter has unit tests with mocked boto3 calls
* AC-CW-12.2: Bridge enrichment has unit tests for success and fallback paths
* AC-CW-12.3: Polling agent has unit tests for poll cycle and shutdown
* AC-CW-12.4: EventBridge router has unit tests for valid and invalid payloads
* AC-CW-12.5: Integration test verifies enriched diagnosis flow end-to-end
* AC-CW-12.6: All tests pass with `pytest tests/unit/ -x`
