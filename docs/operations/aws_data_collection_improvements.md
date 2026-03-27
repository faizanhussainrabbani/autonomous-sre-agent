# AWS Incident Data Collection — Improvement Areas

**Date:** 2025-07-14\
**Based on:** [aws_data_collection_review.md](../reports/analysis/aws_data_collection_review.md)\
**Industry research:** Datadog, New Relic, and Sentry AWS integration patterns

---

## Overview

This document identifies concrete, prioritised improvements to how the Autonomous SRE Agent
discovers, collects, and enriches incident information from AWS services. Each improvement is
grounded in both a gap identified in the current codebase review and in how leading industry tools
approach the same problem.

---

## Industry Research: How Leading Tools Collect AWS Data

### Datadog

Datadog uses a **dual-track strategy** for AWS metric collection:

| Track | Mechanism | Latency | Cost |
|---|---|---|---|
| **API Polling** | IAM role → `cloudwatch:GetMetricStatistics` every 10 min | ~10 min | CloudWatch API charges |
| **Metric Streams** | CloudWatch Metric Streams → Amazon Data Firehose → Datadog | ~2–3 min | Firehose costs |

For logs, Datadog deploys a **Forwarder Lambda** that subscribes to CloudWatch Log Groups via
subscription filters. When a new log event is delivered to CloudWatch, the Forwarder Lambda fires
and pushes the payload to Datadog's log ingestion endpoint within seconds.

For alarms, Datadog can use either of:
- **Alarm polling**: Periodic `DescribeAlarmHistory` API calls
- **SNS subscription**: CloudWatch alarms → SNS → HTTP POST to Datadog (same pattern as the SRE agent)

Key Datadog IAM permissions for data collection (read-only):
`cloudwatch:Get*`, `cloudwatch:List*`, `cloudwatch:Describe*`, `logs:FilterLogEvents`,
`logs:GetLogEvents`, `ecs:Describe*`, `ecs:List*`, `xray:BatchGetTraces`,
`xray:GetTraceSummaries`, `lambda:List*`

### New Relic

New Relic explicitly recommends **CloudWatch Metric Streams over API polling** for all supported
services, citing:

- **Push vs poll**: Metric Streams delivers data within 2–3 minutes vs 10-minute polling intervals
- **Coverage**: Streams all namespaces automatically; polling requires per-service configuration
- **Scalability**: No CloudWatch API rate-limit issues at scale

For services not supported by Metric Streams (CloudTrail, Health, Trusted Advisor, X-Ray),
New Relic falls back to API polling.

For logs, New Relic uses Kinesis Data Firehose: CloudWatch Logs subscription filters →
Firehose → New Relic Log API.

Architecture:
```
CloudWatch Metric Streams
        │
        ▼
Amazon Kinesis Data Firehose
        │
        ▼
New Relic Metrics API  (OTLP endpoint)
```

### Sentry

Sentry takes a fundamentally different, **SDK-injection approach** for Lambda:

- Deploys a CloudFormation stack that modifies Lambda function configurations
- Injects the Sentry SDK as a **Lambda Layer** + environment variables
- The SDK wraps the Lambda handler and captures: unhandled exceptions, performance traces
  (invocation duration, cold starts), and custom events
- Data flows from the Lambda runtime directly to Sentry's ingest endpoint

Sentry does **not** poll CloudWatch. Instead, it instruments the application layer, capturing
errors and traces at the source. This gives it higher-fidelity data (full stack traces, request
context) but requires SDK access to the runtime.

### Key Takeaways for the SRE Agent

| Approach | Datadog | New Relic | Sentry | SRE Agent (current) |
|---|---|---|---|---|
| Metric collection | Poll + Stream | Stream (preferred) | N/A | ❌ None |
| Log collection | Forwarder Lambda | Firehose | SDK | ❌ None |
| Trace collection | X-Ray API polling | X-Ray API polling | SDK tracing | ❌ None |
| Alarm ingestion | SNS or poll | SNS or stream | N/A | ✅ SNS push |
| Resource metadata | IAM read APIs | IAM read APIs | CloudFormation | ❌ None |
| Latency | 2–10 min | 2–3 min | Sub-second | Variable (push-only) |

---

## Improvement Areas

### Area 1 — Bridge Enrichment: Populate `correlated_signals` Before Forwarding

**Priority:** Critical\
**Effort:** Medium (2–3 days)\
**Impact:** Transforms LLM diagnosis quality immediately, no architecture change needed

#### Problem

The `localstack_bridge.py` always sets `correlated_signals = None`. The LLM receives an alarm name
and description but no live metric data, no log excerpts, and no trace context.

#### Solution

After receiving the SNS alarm notification, the bridge should call the CloudWatch APIs to fetch
supporting evidence **before** posting to `/api/v1/diagnose`:

```python
import boto3

def enrich_alert_with_cloudwatch(alarm_name: str, metric_name: str,
                                  namespace: str, dimensions: list) -> dict:
    cw = boto3.client("cloudwatch")
    logs = boto3.client("logs")
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(minutes=30)

    # 1. Fetch metric trend (30-min window)
    metric_data = cw.get_metric_data(
        MetricDataQueries=[{
            "Id": "m1",
            "MetricStat": {
                "Metric": {
                    "Namespace": namespace,
                    "MetricName": metric_name,
                    "Dimensions": dimensions,
                },
                "Period": 60,
                "Stat": "Sum",
            },
        }],
        StartTime=start_time,
        EndTime=end_time,
    )

    # 2. Fetch recent log events (if log group exists)
    log_group = f"/aws/lambda/{service_name}"  # or ECS equivalent
    log_events = logs.filter_log_events(
        logGroupName=log_group,
        startTime=int(start_time.timestamp() * 1000),
        endTime=int(end_time.timestamp() * 1000),
        filterPattern="ERROR",
        limit=50,
    )

    # 3. Compute real deviation_sigma from baseline
    values = metric_data["MetricDataResults"][0]["Values"]
    if len(values) > 1:
        mean = sum(values[:-1]) / len(values[:-1])
        std = statistics.stdev(values[:-1]) if len(values) > 2 else 0.1
        deviation_sigma = abs(values[-1] - mean) / std if std > 0 else 0.0
    else:
        deviation_sigma = 10.0  # fallback

    return {
        "metrics": [{"name": metric_name, "value": v, ...} for v in values],
        "logs": [{"message": e["message"], "timestamp": e["timestamp"]} for e in log_events.get("events", [])],
        "deviation_sigma": deviation_sigma,
        "current_value": values[-1] if values else threshold,
        "baseline_value": mean if values else 0.0,
    }
```

**Benefit:** The LLM immediately gains access to:
- Actual metric values (not just the threshold)
- Real `deviation_sigma` (not hardcoded `10.0`)
- Recent CloudWatch log error messages
- A 30-minute trend showing whether the issue is worsening or recovering

---

### Area 2 — CloudWatch Metrics Adapter: Implement `CloudWatchMetricsAdapter`

**Priority:** High\
**Effort:** Medium (3–4 days)\
**Impact:** Activates the `AnomalyDetector` and `SignalCorrelator` for AWS-native metrics

#### Problem

The `MetricsQuery` port exists but has no CloudWatch implementation. `PrometheusMetricsAdapter`
uses PromQL against Prometheus — unsuitable for AWS-native metric namespaces.

#### Solution

Implement a `CloudWatchMetricsAdapter` that satisfies `MetricsQuery`:

```python
class CloudWatchMetricsAdapter(MetricsQuery):
    """MetricsQuery port backed by CloudWatch GetMetricData API."""

    # Maps canonical SRE metric names to CloudWatch namespaces + metric names
    METRIC_MAP = {
        "http_request_duration_seconds": ("AWS/ApplicationELB", "TargetResponseTime"),
        "http_requests_total": ("AWS/ApplicationELB", "RequestCount"),
        "error_rate": ("AWS/Lambda", "Errors"),
        "invocation_count": ("AWS/Lambda", "Invocations"),
        "lambda_duration_ms": ("AWS/Lambda", "Duration"),
        "lambda_throttles": ("AWS/Lambda", "Throttles"),
        "ecs_cpu_utilization": ("ECS/ContainerInsights", "CpuUtilized"),
        "ecs_memory_utilization": ("ECS/ContainerInsights", "MemoryUtilized"),
        "ecs_running_tasks": ("ECS/ContainerInsights", "RunningTaskCount"),
        "asg_in_service_instances": ("AWS/AutoScaling", "GroupInServiceInstances"),
    }

    async def query(self, service, metric, start_time, end_time, ...) -> list[CanonicalMetric]:
        namespace, cw_metric = self.METRIC_MAP.get(metric, (None, metric))
        # Call GetMetricData API ...
        # Return list[CanonicalMetric]
```

**Benefit:** Enables `SignalCorrelator` to gather real AWS metric trends for any alarm, and wires
the `AnomalyDetector` to a real data source.

**Implementation note:** Register `CloudWatchMetricsAdapter` in
`adapters/intelligence_bootstrap.py` alongside the OTel provider, controlled by a
`TELEMETRY_PROVIDER=cloudwatch` config flag.

---

### Area 3 — CloudWatch Logs Adapter: Implement `CloudWatchLogsAdapter`

**Priority:** High\
**Effort:** Medium (2–3 days)\
**Impact:** Provides actual error messages to the LLM — the single most useful diagnostic signal

#### Problem

There is no `LogQuery` implementation for CloudWatch Logs. The `LokiLogAdapter` targets Grafana
Loki (LogQL) and cannot query CloudWatch Log Groups.

#### Solution

Implement `CloudWatchLogsAdapter` satisfying `LogQuery`:

```python
class CloudWatchLogsAdapter(LogQuery):
    """LogQuery port backed by CloudWatch Logs Insights API."""

    async def query_logs(self, service, start_time, end_time,
                          severity=None, trace_id=None, search_text=None,
                          limit=1000) -> list[CanonicalLogEntry]:
        # Determine log group: /aws/lambda/{service} or ECS task log group
        log_group = self._resolve_log_group(service)

        # Use FilterLogEvents for simple queries
        filter_pattern = self._build_filter(severity, trace_id, search_text)
        response = self._client.filter_log_events(
            logGroupName=log_group,
            startTime=...,
            endTime=...,
            filterPattern=filter_pattern,
            limit=min(limit, 10000),
        )
        return [self._to_canonical(e) for e in response["events"]]

    async def query_insights(self, log_group: str, query: str,
                              start_time: datetime, end_time: datetime):
        """Run a CloudWatch Logs Insights query for structured log analysis."""
        # Start query
        start_resp = self._client.start_query(
            logGroupName=log_group,
            startTime=int(start_time.timestamp()),
            endTime=int(end_time.timestamp()),
            queryString=query,
        )
        query_id = start_resp["queryId"]
        # Poll for results (max 30s)
        ...
```

**Benefit:** Actual Lambda error stack traces, ECS task crash logs, and application error messages
are passed to the LLM — the difference between "Lambda had errors" and "database connection pool
exhausted at 128/128 connections".

---

### Area 4 — Metric Streams Integration: Low-Latency AWS Metric Push

**Priority:** High\
**Effort:** Large (1–2 weeks, requires AWS infrastructure changes)\
**Impact:** Reduces metric collection latency from 10 min (poll) to 2–3 min (stream)

#### Problem

API polling is reactive and slow. A critical outage that recovers in 4 minutes may never be caught
by a 10-minute polling interval.

#### Solution (following New Relic's recommended pattern)

```
CloudWatch Metric Streams  →  Amazon Kinesis Data Firehose  →  /api/v1/ingest/metrics
```

1. Create a CloudWatch Metric Stream for the namespaces of interest (`AWS/Lambda`, `AWS/ECS`,
   `AWS/ApplicationELB`, `ECS/ContainerInsights`).
2. Configure the stream to deliver to a Kinesis Data Firehose delivery stream.
3. Configure Firehose to call the agent's new `POST /api/v1/ingest/metrics` HTTP endpoint.
4. Implement a metric receiver that feeds incoming metric values into `BaselineService.ingest()`
   and triggers `AnomalyDetector.detect()` on each update.

**Benefits:**
- 2–3 minute end-to-end latency for metric ingestion
- Complete namespace coverage without per-service configuration
- Pushes data into `AnomalyDetector` continuously (proactive, not reactive)

---

### Area 5 — Proactive Polling Agent: CloudWatch Metric Polling Background Task

**Priority:** Medium\
**Effort:** Medium (3–4 days)\
**Impact:** Enables proactive anomaly detection without waiting for CloudWatch to fire an alarm

#### Problem

The agent currently has no ability to detect anomalies before CloudWatch raises an alarm.
CloudWatch alarms have a minimum evaluation period of 60 seconds, and composite alarms or
percentile anomaly detection are not always configured.

#### Solution

Add a background polling task (FastAPI `lifespan` or `asyncio.create_task`) that runs every 60
seconds and calls `CloudWatchMetricsAdapter.query_instant()` for a configured set of service +
metric pairs:

```python
async def metric_polling_loop(metrics_adapter: MetricsQuery,
                               detector: AnomalyDetector,
                               services: list[str]) -> None:
    while True:
        for service in services:
            for metric in WATCHED_METRICS:
                point = await metrics_adapter.query_instant(service, metric)
                if point:
                    anomalies = await detector.detect(service, metric, point.value)
                    for anomaly in anomalies:
                        await event_bus.publish(AnomalyDetectedEvent(anomaly))
        await asyncio.sleep(60)
```

**Benefits:**
- Detects anomalies that are below the CloudWatch alarm threshold but statistically significant
- Can detect trends (gradual memory leak, slow error-rate climb) before they become alarms
- Activates the `AnomalyDetector` with real data for the first time

---

### Area 6 — AWS X-Ray Trace Integration

**Priority:** Medium\
**Effort:** Medium (3–4 days)\
**Impact:** Enables service-to-service root cause tracing — identifies *which* downstream call caused the failure

#### Problem

When a Lambda function fails due to a slow database query, the CloudWatch alarm tells you the Lambda
errored. X-Ray trace data tells you that the Lambda spent 4.8 seconds calling RDS, which timed out.
The agent currently has no access to this information.

#### Solution

Implement `XRayTraceAdapter` satisfying `TraceQuery`:

```python
class XRayTraceAdapter(TraceQuery):
    """TraceQuery port backed by AWS X-Ray GetTraceSummaries + BatchGetTraces."""

    async def query_traces(self, service, start_time, end_time,
                            limit=100, min_duration_ms=None,
                            status_code=None) -> list[CanonicalTrace]:
        # Get trace summaries filtered by service name
        resp = self._client.get_trace_summaries(
            StartTime=start_time,
            EndTime=end_time,
            Sampling=False,
            FilterExpression=f'service("{service}") AND error',
        )
        trace_ids = [s["Id"] for s in resp["TraceSummaries"][:limit]]

        if not trace_ids:
            return []

        # Fetch full trace segments
        full_resp = self._client.batch_get_traces(TraceIds=trace_ids)
        return [self._to_canonical(t) for t in full_resp["Traces"]]
```

**Benefit:** LLM context includes which service call in the distributed trace caused the slowdown
or error — enabling much more precise root cause identification and remediation targeting.

---

### Area 7 — EventBridge Integration: Beyond SNS Alarms

**Priority:** Medium\
**Effort:** Medium (2–3 days)\
**Impact:** Captures infrastructure change events that cause incidents but never trigger alarms

#### Problem

Many incidents are caused by infrastructure events that do not generate a CloudWatch metric alarm:
- A Lambda deployment rolls out a new version that introduces a bug
- An ECS task definition is updated with an incorrect environment variable
- An IAM policy change removes a permission that a service depends on
- An RDS maintenance window starts unexpectedly

None of these generate a `AWS/Lambda Errors` alarm. They only appear as EventBridge events.

#### Solution

Add an EventBridge rule that captures relevant event patterns and posts them to a new
`POST /api/v1/events/aws` endpoint:

```json
{
  "source": ["aws.lambda", "aws.ecs", "aws.rds", "aws.iam"],
  "detail-type": [
    "AWS API Call via CloudTrail",
    "ECS Task State Change",
    "Lambda Function Updated",
    "RDS DB Instance Event"
  ]
}
```

The agent's new event handler would:
1. Parse the EventBridge event
2. Check if the affected resource currently has elevated error rates (using the polling agent)
3. Correlate the change event with any active incident

**Benefit:** Adds causal event context to diagnoses. The LLM can reason: "The Lambda error rate
spiked at 14:32. A new function version was deployed at 14:31. Root cause is likely the recent
deployment."

---

### Area 8 — Resource Metadata Enrichment

**Priority:** Medium\
**Effort:** Low (1 day)\
**Impact:** Gives the LLM concrete resource configuration context for better remediation advice

#### Problem

When diagnosing a Lambda OOM kill, the LLM does not know the function's current memory limit,
timeout setting, concurrency limit, or which IAM role it uses. This information is available via
`lambda:GetFunctionConfiguration` at no cost and requires no additional infrastructure.

#### Solution

Add a `ResourceMetadataFetcher` component that the bridge (or the enrichment layer) calls before
constructing the `AnomalyAlert`:

```python
class AWSResourceMetadataFetcher:
    async def fetch_lambda_context(self, function_name: str) -> dict:
        config = self._lambda.get_function_configuration(FunctionName=function_name)
        return {
            "memory_mb": config["MemorySize"],
            "timeout_s": config["Timeout"],
            "runtime": config["Runtime"],
            "reserved_concurrency": config.get("ReservedConcurrentExecutions"),
            "last_modified": config["LastModified"],
        }

    async def fetch_ecs_context(self, cluster: str, service: str) -> dict:
        svc = self._ecs.describe_services(cluster=cluster, services=[service])["services"][0]
        return {
            "desired_count": svc["desiredCount"],
            "running_count": svc["runningCount"],
            "pending_count": svc["pendingCount"],
            "task_definition": svc["taskDefinition"],
            "deployment_status": svc["deployments"][0]["status"],
        }
```

**Benefit:** LLM can reason: "Memory limit is 128 MB and the process is using 127 MB — this is an
OOM condition, not a code error." Or: "ECS service has 0 running tasks out of 3 desired — this is
a total service outage, not degraded performance."

---

### Area 9 — AWS Health Events Integration

**Priority:** Low\
**Effort:** Low (1–2 days)\
**Impact:** Prevents false-positive diagnoses when AWS itself is having an outage

#### Problem

When an AWS availability zone or service (e.g., Lambda in eu-west-1) experiences a partial outage,
the SRE Agent diagnoses every Lambda error as a code bug or DB connection issue. It has no way to
know that the root cause is an upstream AWS infrastructure event.

#### Solution

Poll the AWS Health API every 5 minutes for events affecting the monitored account's regions and
services:

```python
health = boto3.client("health", region_name="us-east-1")  # Health API is global
resp = health.describe_events(
    filter={
        "regions": ["eu-west-3"],
        "eventStatusCodes": ["open", "upcoming"],
        "eventTypeCategories": ["issue", "scheduledChange"],
    }
)
```

Inject active Health events as context into the `DiagnosisRequest`. The LLM prompt should include:
> "Note: AWS Health reports the following active events in eu-west-3: [Lambda: Increased Lambda
> invocation error rates (opened 14:15 UTC)]"

**Benefit:** The agent correctly attributes outages to AWS infrastructure issues rather than
generating incorrect remediation advice.

---

### Area 10 — Severity Calibration: Dynamic `deviation_sigma` from Baseline

**Priority:** High (for operational accuracy)\
**Effort:** Low (once CloudWatch adapter exists)\
**Impact:** Removes hardcoded `deviation_sigma = 10.0`; enables accurate SEV1/SEV2/SEV3 triage

#### Problem

`deviation_sigma` is always `10.0` — every alert appears equally critical to the confidence scorer
and severity classifier. A single Lambda error in a dev environment gets the same sigma as a
production payment service with 1,000 errors per second.

#### Solution

Once `CloudWatchMetricsAdapter` exists, compute `deviation_sigma` from a real sliding baseline:

```python
# In bridge enrichment (Area 1) or in AnomalyDetector
baseline_mean, baseline_std = baseline_service.get_baseline(service, metric)
current_value = metric_data_points[-1]
deviation_sigma = abs(current_value - baseline_mean) / baseline_std
```

The `BaselineService` already has the `ingest()` and `compute_deviation()` methods. It needs to
be fed real CloudWatch data by the polling agent (Area 5).

---

## Improvement Roadmap Summary

| # | Improvement | Priority | Effort | Unlocks |
|---|---|---|---|---|
| 1 | Bridge enrichment (GetMetricData + FilterLogEvents) | Critical | Medium | LLM log + metric context |
| 2 | `CloudWatchMetricsAdapter` | High | Medium | `AnomalyDetector`, `SignalCorrelator` |
| 3 | `CloudWatchLogsAdapter` | High | Medium | LLM log excerpts |
| 10 | Dynamic `deviation_sigma` | High | Low | Accurate severity triage |
| 5 | Background metric polling agent | Medium | Medium | Proactive detection |
| 6 | X-Ray trace adapter | Medium | Medium | Distributed trace RCA |
| 7 | EventBridge change events | Medium | Medium | Causal correlation |
| 8 | Resource metadata fetcher | Medium | Low | Config-aware diagnosis |
| 4 | CloudWatch Metric Streams | High | Large | Real-time metric push |
| 9 | AWS Health events | Low | Low | AWS-outage awareness |

### Recommended Phase Order

**Phase A (1–2 weeks):** Items 1, 10, 8 — immediate LLM quality improvement, minimal code change,
no new infrastructure required.

**Phase B (2–4 weeks):** Items 2, 3, 5 — build CloudWatch adapters, wire the detection domain
layer, activate proactive polling.

**Phase C (4–8 weeks):** Items 6, 7, 4 — distributed tracing, change correlation, Metric Streams
pipeline.

**Phase D (ongoing):** Item 9 — AWS Health polling as a background health-check task.

---

## Implementation Notes

### IAM Permissions Required

To implement the above improvements, the agent's IAM role needs these additional read-only
permissions on top of the current remediation permissions:

```json
{
  "Effect": "Allow",
  "Action": [
    "cloudwatch:GetMetricData",
    "cloudwatch:GetMetricStatistics",
    "cloudwatch:ListMetrics",
    "cloudwatch:DescribeAlarms",
    "cloudwatch:DescribeAlarmHistory",
    "logs:FilterLogEvents",
    "logs:GetLogEvents",
    "logs:DescribeLogGroups",
    "logs:DescribeLogStreams",
    "logs:StartQuery",
    "logs:GetQueryResults",
    "xray:GetTraceSummaries",
    "xray:BatchGetTraces",
    "lambda:GetFunctionConfiguration",
    "lambda:ListFunctions",
    "ecs:DescribeServices",
    "ecs:DescribeTasks",
    "ecs:ListTasks",
    "autoscaling:DescribeAutoScalingGroups",
    "health:DescribeEvents",
    "health:DescribeEventDetails",
    "health:DescribeAffectedEntities"
  ],
  "Resource": "*"
}
```

### Configuration Changes

Add the following to `config/agent.yaml` for the new adapters:

```yaml
telemetry:
  provider: cloudwatch          # or "otel" for Prometheus/OTel stack
  cloudwatch:
    region: eu-west-3
    metric_poll_interval_seconds: 60
    log_fetch_window_minutes: 30
    log_filter_pattern: "ERROR"
    metric_streams_enabled: false  # Phase C feature flag
  enrichment:
    fetch_metrics: true
    fetch_logs: true
    fetch_traces: false           # Enable when XRayTraceAdapter is built
    fetch_resource_metadata: true

aws_health:
  enabled: false                  # Enable in Phase D
  poll_interval_seconds: 300
  regions: ["eu-west-3"]
```

---

## Reference: Related Documents

- [Current state review](../reports/analysis/aws_data_collection_review.md)
- [AGENTS.md](../../AGENTS.md) — multi-agent coordination protocol
- [Phase 1.5 status](../reports/analysis/phase_1_5_test_findings.md)
- [Observability improvement areas](../reports/analysis/observability_improvement_areas.md)
