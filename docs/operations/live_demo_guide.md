---
title: Live Incident Response Demonstrations
description: Execution-validated guide for running all Autonomous SRE Agent live demos across AWS, Azure, HTTP, EventBridge, Kubernetes operations, multi-agent lock coordination, and Prometheus observability.
ms.date: 2026-04-11
ms.topic: how-to
status: APPROVED
keywords:
  - live demos
  - localstack
  - incident response
  - kubernetes
  - multi-agent locks
  - prometheus
  - observability
---

## Overview

This guide is the canonical index for the live demo suite. It documents every `../../scripts/demo/live_demo_*.py` script, expected prerequisites, and execution mode.

Validation scope for this revision:

* Canonical suite now includes 20 executable demos after retiring low-value overlap and placeholder entries
* Demo 2 (`live_demo_cascade_failure.py`) re-validated end-to-end with Anthropic adapter
* Demo 25 (`live_demo_lambda_dynamodb_saturation.py`) added — Lambda Cold-Start Avalanche + DynamoDB Saturation using LocalStack Pro Chaos API; requires Pro for full execution
* Demo P6 (`live_demo_p6_full_observability.py`) added — Full Prometheus observability loop validated end-to-end; all 7 PromQL queries returned live TSDB data
* Kubernetes Demo 12 was validated in both simulation mode and live `kubectl` mode
* Demo 19 (`live_demo_rag_error_evaluation.py`) was validated in non-interactive mode (`SKIP_PAUSES=1`)
* Demos 20-23 were validated in non-interactive mode (`SKIP_PAUSES=1`)
* Results were cross-checked against `docs/reports/verification/live_demo_verification_report.md`, `docs/reports/analysis/live_demo_review_report.md`, and `docs/operations/localstack_live_incident_demo.md`

## Demo inventory

| Demo | Script | Focus Area | LocalStack | LLM Required |
|---|---|---|---|---|
| 1 | [../../scripts/demo/live_demo_1_telemetry_baseline.py](../../scripts/demo/live_demo_1_telemetry_baseline.py) | Phase 1 telemetry adapter-to-domain mapping | Community | No |
| 2 | [../../scripts/demo/live_demo_cascade_failure.py](../../scripts/demo/live_demo_cascade_failure.py) | Multi-service cascade correlation and event isolation | No | Yes (Anthropic) |
| 3 | [../../scripts/demo/live_demo_deployment_regression.py](../../scripts/demo/live_demo_deployment_regression.py) | Deployment-induced diagnosis, circuit breaker, certificate expiry | No | Yes (Anthropic) |
| 4 | [../../scripts/demo/live_demo_localstack_aws.py](../../scripts/demo/live_demo_localstack_aws.py) | AWS operators (ECS/Lambda/ASG) via LocalStack | Pro for full coverage | No |
| 6 | [../../scripts/demo/live_demo_http_optimizations.py](../../scripts/demo/live_demo_http_optimizations.py) | HTTP end-to-end with token optimization and caching | No | Yes (Anthropic) |
| 7 | [../../scripts/demo/live_demo_localstack_incident.py](../../scripts/demo/live_demo_localstack_incident.py) | Lambda incident chain: alarm → SNS → bridge → diagnosis | Community or Pro | Yes (Anthropic) |
| 8 | [../../scripts/demo/live_demo_ecs_multi_service.py](../../scripts/demo/live_demo_ecs_multi_service.py) | ECS multi-service cascade and severity override workflow | Pro | Yes (Anthropic) |
| 9 | [../../scripts/demo/live_demo_cloudwatch_enrichment.py](../../scripts/demo/live_demo_cloudwatch_enrichment.py) | AlertEnricher with CloudWatch metrics and logs | Community | No |
| 10 | [../../scripts/demo/live_demo_eventbridge_reaction.py](../../scripts/demo/live_demo_eventbridge_reaction.py) | Event routing and timeline building via FastAPI TestClient simulation | No | No |
| 11 | [../../scripts/demo/live_demo_11_azure_operations.py](../../scripts/demo/live_demo_11_azure_operations.py) | Azure App Service and Functions operator behavior | No | No |
| 12 | [../../scripts/demo/live_demo_kubernetes_operations.py](../../scripts/demo/live_demo_kubernetes_operations.py) | Kubernetes restart and scale operations (simulation or real `kubectl`) | No | No |
| 13 | [../../scripts/demo/live_demo_multi_agent_lock_protocol.py](../../scripts/demo/live_demo_multi_agent_lock_protocol.py) | Lock schema, preemption, cooling-off, and human override simulation | No | No |
| 18 | [../../scripts/demo/live_demo_18_etcd_action_lock_flow.py](../../scripts/demo/live_demo_18_etcd_action_lock_flow.py) | External etcd-backed lock acquisition and remediation execution | No | No |
| 19 | [../../scripts/demo/live_demo_rag_error_evaluation.py](../../scripts/demo/live_demo_rag_error_evaluation.py) | Complex LocalStack multi-error RAG evaluation marathon with per-error scorecard and fallback-path probe | Community or Pro | Yes (Anthropic) |
| 20 | [../../scripts/demo/live_demo_20_unknown_incident_safety_net.py](../../scripts/demo/live_demo_20_unknown_incident_safety_net.py) | Unknown-incident safety flow before and after runbook grounding | Community | Yes (Anthropic) |
| 21 | [../../scripts/demo/live_demo_21_human_governance_lifecycle.py](../../scripts/demo/live_demo_21_human_governance_lifecycle.py) | Full severity override lifecycle (apply, verify, revoke) | Community | Yes (Anthropic) |
| 22 | [../../scripts/demo/live_demo_22_change_event_causality.py](../../scripts/demo/live_demo_22_change_event_causality.py) | EventBridge-style change events correlated into diagnosis context | Community | Yes (Anthropic) |
| 23 | [../../scripts/demo/live_demo_23_ai_says_no_before_it_acts.py](../../scripts/demo/live_demo_23_ai_says_no_before_it_acts.py) | Guardrail-first remediation: deny risky plan, allow safe plan | Community | No |
| 24 | [../../scripts/demo/live_demo_kubernetes_log_aggregation_scale.py](../../scripts/demo/live_demo_kubernetes_log_aggregation_scale.py) | K8s pod log aggregation, RAG diagnosis, and horizontal scale remediation | No (K8s cluster for live mode) | Yes (Anthropic) |
| 25 | [../../scripts/demo/live_demo_lambda_dynamodb_saturation.py](../../scripts/demo/live_demo_lambda_dynamodb_saturation.py) | Lambda cold-start avalanche + DynamoDB saturation via LocalStack Chaos API | Pro (required) | Yes (Anthropic) |
| P6 | [../../scripts/demo/live_demo_p6_full_observability.py](../../scripts/demo/live_demo_p6_full_observability.py) | Full Prometheus observability loop — scrape, PromQL, and alert rule evaluation | No | Yes (Anthropic) |

Retired demos:

* Demo 5, Demo 14, Demo 15, Demo 16, and Demo 17 were retired due to duplicate coverage, placeholder behavior, or overlap with stronger demos.

### Demo naming

Each demo has one canonical script entry point.

## Prerequisites

### Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

### LocalStack

* Community demos: 1, 7, 9, 19, 20, 21, 22, 23
* Pro demos: 8, 25, plus full-feature execution for Demo 4
* No LocalStack required: 2, 3, 6, 10, 11, 12, 13, 18, 24, P6

Community quick start:

```bash
docker run --rm -d -p 4566:4566 localstack/localstack:latest
```

Pro quick start:

```bash
localstack start -d --services=ecs,ec2,lambda,cloudwatch,dynamodb,events,sns,logs --pro --region=us-east-1
```

### Prometheus

Demo P6 requires a running Prometheus instance configured to scrape the agent's `/metrics` endpoint. The repository ships a ready-to-use configuration in `infra/prometheus/`.

```bash
docker compose -f docker-compose.deps.yml up -d prometheus
```

Prometheus will be available at `http://localhost:9090`. It is pre-configured (via `infra/prometheus/prometheus.yml`) to scrape `host.docker.internal:8080` every 15 s and load the SLO alert rules from `infra/prometheus/rules/sre_agent_slo.yaml`.

> [!NOTE]
> Port 8080 must be free before running Demo P6. The demo exposes the process-local Prometheus registry on that port for Prometheus to scrape.

### LLM credentials

The LLM-driven demos (2, 3, 6, 7, 8, 19, 20, 21, 22, 24, 25, P6) require a valid Anthropic API key.

```bash
export ANTHROPIC_API_KEY=<your-key>
```

> [!NOTE]
> Validation runs in this guide revision succeeded with Anthropic configured. OpenAI is optional and not required by these scripts.

### Optional environment variables

```bash
export AWS_DEFAULT_REGION=us-east-1
export SKIP_PAUSES=1
export BRIDGE_HOST=127.0.0.1
```

Notes:

* Set `BRIDGE_HOST=host.docker.internal` when LocalStack runs in Docker and must reach host services
* Keep `AWS_DEFAULT_REGION` consistent when running multiple LocalStack demos against the same instance

### Kubernetes live mode (Demo 12, Demo 24)

For live mode only:

* `kubectl` installed and available
* `KUBECONFIG` points to a reachable cluster
* Target namespace and workloads exist

## Demo details

### Demo 1: Telemetry baseline

```bash
SKIP_PAUSES=1 python3 ../../scripts/demo/live_demo_1_telemetry_baseline.py
```

Expected behavior: pushes synthetic CloudWatch metrics and confirms canonical metric retrieval.

### Demo 2: Cascade failure

```bash
SKIP_PAUSES=1 python3 ../../scripts/demo/live_demo_cascade_failure.py
```

Expected behavior: runs three LLM diagnoses across cascading alerts and prints incident summary.

### Demo 3: Deployment regression

```bash
SKIP_PAUSES=1 python3 ../../scripts/demo/live_demo_deployment_regression.py
```

Expected behavior: validates deployment-induced signal handling, circuit breaker behavior, and diagnostics.

### Demo 4: AWS LocalStack operators

```bash
SKIP_PAUSES=1 python3 ../../scripts/demo/live_demo_localstack_aws.py
```

Expected behavior: exercises ECS/Lambda/ASG operator actions through LocalStack adapters.

### Demo 6: HTTP token optimizations

```bash
SKIP_PAUSES=1 python3 ../../scripts/demo/live_demo_http_optimizations.py
```

Expected behavior: demonstrates novel-incident short-circuit, timeline filtering, lightweight validation, and cache behavior.

### Demo 7: Lambda incident cascade

```bash
SKIP_PAUSES=1 python3 ../../scripts/demo/live_demo_localstack_incident.py
```

Expected behavior: complete chain Lambda crash → CloudWatch alarm → SNS → bridge → diagnosis, then cleanup.

### Demo 8: ECS multi-service cascade

```bash
SKIP_PAUSES=1 python3 ../../scripts/demo/live_demo_ecs_multi_service.py
```

Expected behavior: dual-service cascade diagnosis, severity override API, and cleanup.

### Demo 9: CloudWatch enrichment

```bash
SKIP_PAUSES=1 python3 ../../scripts/demo/live_demo_cloudwatch_enrichment.py
```

Expected behavior: enrichment payload shows metric and log context without interactive pauses.

### Demo 10: EventBridge reaction (simulated ingress)

```bash
SKIP_PAUSES=1 python3 ../../scripts/demo/live_demo_eventbridge_reaction.py
```

Expected behavior: FastAPI TestClient posts synthetic AWS-style events to `/api/v1/events/aws` and builds timeline output.

### Demo 11: Azure operations

```bash
SKIP_PAUSES=1 python3 ../../scripts/demo/live_demo_11_azure_operations.py
```

Expected behavior: validates restart and scale behavior with Azure SDK-style name semantics.

### Demo 12: Kubernetes operations

Simulation mode:

```bash
SKIP_PAUSES=1 python3 ../../scripts/demo/live_demo_kubernetes_operations.py
```

Live mode:

```bash
SKIP_PAUSES=1 RUN_KUBECTL=1 python3 ../../scripts/demo/live_demo_kubernetes_operations.py
```

Expected behavior:

* Simulation mode prints planned `kubectl` commands and exits successfully
* Live mode executes commands and fails if cluster connectivity is unavailable

### Demo 13: Multi-agent lock protocol

```bash
SKIP_PAUSES=1 python3 ../../scripts/demo/live_demo_multi_agent_lock_protocol.py
```

Expected behavior: shows lock acquisition, preemption, cooldown denial, and human override denial.

### Demo 18: External etcd action-lock flow

```bash
SKIP_PAUSES=1 python3 ../../scripts/demo/live_demo_18_etcd_action_lock_flow.py
```

Expected behavior: starts an ephemeral etcd container, executes approved action with etcd-backed lock manager, prints fencing token, and stops the container.

### Demo 19: LocalStack RAG error evaluation marathon

Canonical script:

```bash
SKIP_PAUSES=1 python3 ../../scripts/demo/live_demo_rag_error_evaluation.py
```

Expected behavior:

* Provisions LocalStack CloudWatch alarms and SNS topic for a multi-error stream
* Starts SRE Agent API and ingests multi-service runbooks through the diagnose ingest route
* Runs a pre-ingestion retrieval-miss probe to demonstrate fallback reasoning path
* Evaluates each reported error through the RAG pipeline and prints per-error diagnostics
* Emits a final scorecard with severity, confidence, evidence count, approval, and evaluation path per incident
* Cleans up LocalStack resources and terminates demo-managed processes

### Demo 20: Unknown incident safety net

```bash
SKIP_PAUSES=1 python3 ../../scripts/demo/live_demo_20_unknown_incident_safety_net.py
```

Expected behavior:

* Triggers a LocalStack Lambda incident to generate live telemetry context
* Runs diagnosis before runbook ingest to show retrieval-miss or fallback behavior
* Ingests targeted runbook content through the diagnose ingest route
* Re-runs equivalent diagnosis with a fresh LocalStack incident and prints a before-versus-after grounding summary

### Demo 21: Human governance lifecycle

```bash
SKIP_PAUSES=1 python3 ../../scripts/demo/live_demo_21_human_governance_lifecycle.py
```

Expected behavior:

* Triggers a LocalStack Lambda incident to establish incident context
* Generates a diagnosis to establish incident context
* Applies severity override via POST endpoint
* Verifies active override via GET endpoint
* Revokes override via DELETE endpoint and confirms removal

### Demo 22: Change event causality

```bash
SKIP_PAUSES=1 python3 ../../scripts/demo/live_demo_22_change_event_causality.py
```

Expected behavior:

* Captures LocalStack Lambda change activity and converts it into AWS-style event payloads
* Posts AWS-style change events to the events ingress endpoint
* Retrieves service-scoped recent events
* Attaches retrieved events to correlated diagnosis signals
* Produces diagnosis output with event-causality context

### Demo 23: AI says no before it acts

```bash
SKIP_PAUSES=1 python3 ../../scripts/demo/live_demo_23_ai_says_no_before_it_acts.py
```

Expected behavior:

* Uses LocalStack Lambda operator execution as the remediation target
* Denies high blast-radius remediation execution path
* Executes low blast-radius remediation path successfully
* Prints verification result, lock-backed execution evidence, and LocalStack concurrency impact

### Demo 24: Kubernetes pod log aggregation and horizontal scale remediation

Simulation mode:

```bash
SKIP_PAUSES=1 python3 ../../scripts/demo/live_demo_kubernetes_log_aggregation_scale.py
```

Live mode (requires a reachable Kubernetes cluster):

```bash
SKIP_PAUSES=1 RUN_KUBECTL=1 START_AGENT=1 python3 ../../scripts/demo/live_demo_kubernetes_log_aggregation_scale.py
```

Environment variables:

* `K8S_NAMESPACE` — Target namespace (default: `sre-demo`)
* `K8S_CLUSTER` — Cluster display name (default: `sre-local`)
* `RUN_KUBECTL` — Set to `1` to execute real kubectl commands
* `START_AGENT` — Set to `1` to auto-start the SRE Agent server
* `AGENT_PORT` — SRE Agent port (default: `8181`)

Expected behavior:

* Deploys three sample services (svc-a, svc-b, svc-c) to a dedicated namespace
* Collects baseline pod metrics across all services
* Injects memory pressure fault on svc-a causing OOMKill and CrashLoopBackOff
* Aggregates pod logs and metrics from affected pods (real or simulated)
* Sends enriched AnomalyAlert with correlated signals (pod metrics, aggregated log excerpts) to the RAG diagnostic pipeline
* Displays diagnosis result with severity, confidence, evidence citations, and audit trail
* Generates remediation plan (horizontal scale-up) with approval gate based on confidence level
* Executes scale-up from 2 to 4 replicas via kubectl
* Validates post-remediation pod health and replica count
* Cleans up all demo-created resources on exit

Kubernetes cluster setup (k3d):

```bash
k3d cluster create sre-local --agents 2
kubectl create namespace sre-demo
```

### Demo 25: Lambda cold-start avalanche and DynamoDB saturation

```bash
SKIP_PAUSES=1 python3 ../../scripts/demo/live_demo_lambda_dynamodb_saturation.py
```

Required environment variables:

```bash
export ANTHROPIC_API_KEY=<your-key>
export LOCALSTACK_AUTH_TOKEN=<pro-token>
```

Optional environment variables:

* `LOCALSTACK_ENDPOINT` — LocalStack endpoint (default: `http://localhost:4566`)
* `AGENT_PORT` — SRE Agent port (default: `8181`)
* `BRIDGE_PORT` — Incident bridge webhook port (default: `8080`)
* `BRIDGE_HOST` — Hostname LocalStack uses to reach the bridge (default: `host.docker.internal`)

Expected behavior:

* Deploys two Lambda functions (`order-processor`, `inventory-updater`) and a shared DynamoDB `orders` table via LocalStack Pro
* Creates an EventBridge rule to fan-out order events to both Lambdas
* Wires CloudWatch alarms for Lambda error rate and DynamoDB throttle events to SNS topics
* Starts the SRE Agent FastAPI server (port 8181) and the incident bridge webhook (port 8080)
* Subscribes the bridge to both SNS alert topics
* Seeds the knowledge base with Lambda cold-start and DynamoDB throughput runbooks
* Induces chaos via the LocalStack Chaos API: 70% `ProvisionedThroughputExceededException` on DynamoDB and 2000 ms artificial latency on all Lambda invocations
* Triggers the alarm chain: Lambda errors → SNS → bridge → agent diagnosis
* Displays first diagnosis (Lambda cold-start concurrency thrashing)
* Triggers the DynamoDB throttling alarm independently and displays the compound failure confirmation
* Presents a human approval gate before the concurrency limit remediation action executes
* Tears down all Chaos API rules and cleans up AWS resources on exit

> [!NOTE]
> LocalStack Pro is required for the Chaos API (`chaos/faults` endpoint). Demo 25 will not function with the Community edition.

### Demo P6: Full Prometheus observability loop

```bash
# Start Prometheus first
docker compose -f docker-compose.deps.yml up -d prometheus

# Run the demo
source .env && source .venv/bin/activate
python3 ../../scripts/demo/live_demo_p6_full_observability.py
```

Expected behavior:

* Starts a `prometheus_client` HTTP server on port 8080, exposing the process-local Prometheus registry at `GET /metrics` — the endpoint that `prometheus.yml` is configured to scrape
* Confirms Prometheus is healthy at `http://localhost:9090`
* Ingests 4 cascade-failure runbooks (order-service OOM post-mortem, checkout-service 503 runbook, api-gateway latency runbook, flash-sale cascade pattern) into a fresh ChromaDB collection
* Runs the 3-service Black Friday cascade failure scenario, emitting `sre_agent_diagnosis_duration_seconds`, `sre_agent_severity_assigned_total`, `sre_agent_evidence_relevance_score`, `sre_agent_llm_call_duration_seconds`, and `sre_agent_llm_tokens_total`
* Injects a novel GraphQL federation incident against an empty knowledge base, verifying `sre_agent_diagnosis_errors_total{error_type="novel_incident"}` increments to 1
* Drives a circuit breaker through its full state machine: `CLOSED (0) → OPEN (2) → HALF_OPEN (1) → CLOSED (0)`, emitting `sre_agent_circuit_breaker_state` at each transition
* Waits 20 seconds for at least one Prometheus scrape cycle to complete
* Queries Prometheus via 7 instant PromQL expressions against the live TSDB and prints results:
  * `sre_agent_severity_assigned_total`
  * `sre_agent_llm_tokens_total`
  * `sre_agent_diagnosis_errors_total`
  * `sre_agent_circuit_breaker_state`
  * `sre_agent:diagnosis_latency:p99` (recording rule)
  * `histogram_quantile(0.50, rate(sre_agent_evidence_relevance_score_bucket[5m]))`
  * `rate(sre_agent_llm_call_duration_seconds_count[5m]) * 60`
* Fetches loaded rule groups from `GET /api/v1/rules` and lists all alert definitions with their current state
* Fetches active alerts from `GET /api/v1/alerts` and surfaces any PENDING or FIRING conditions
* Prints a final local registry snapshot across all 12 Prometheus metrics

> [!NOTE]
> If Prometheus is not running, Demo P6 degrades gracefully: all diagnostic phases execute normally and local registry values are printed as a fallback. PromQL and alert phases display an offline warning instead of failing.

Prometheus alert rules evaluated during Demo P6 (defined in `infra/prometheus/rules/sre_agent_slo.yaml`):

| Alert | Threshold | Duration | Severity |
|---|---|---|---|
| `DiagnosisLatencySLOBreach` | P99 latency > 30 s | 5 m | critical |
| `LLMAPIErrors` | Error-to-call ratio > 10 % | 5 m | warning |
| `LLMParseFailureSpike` | > 5 failures/min | 2 m | warning |
| `ThrottleQueueSaturation` | Queue depth > 20 | 3 m | warning |
| `EvidenceQualityDrop` | P50 relevance score < 0.4 | 10 m | warning |
| `LLMTokenRateTooHigh` | > 100 k tokens/min | 5 m | warning |
| `EmbeddingColdStartHigh` | Cold-start > 60 s | immediate | info |
| `CircuitBreakerOpen` | State == 2 (OPEN) | 1 m | critical |

## Execution notes from validation runs

Observed during this guide update:

* Full batch execution across all `live_demo_*.py` scripts completed successfully (`25/25` pass for prior suite; new Demos 25 and P6 validated independently)
* Single canonical script entry point is maintained per demo under `../../scripts/demo/`
* HTTP Demo 6 is stable in non-interactive mode (`SKIP_PAUSES=1`)
* Demo 12 live mode failed with `connection refused` when no reachable cluster context was configured
* Demo 19 completed successfully end to end, including retrieval-miss fallback path and per-error RAG scorecard output
* Demos 20, 21, and 22 completed against live API routes with LocalStack-backed incident/change context in non-interactive mode
* Demo 23 completed deterministic deny-then-allow remediation flow with LocalStack Lambda operator execution in non-interactive mode
* Demo P6 completed end-to-end with Prometheus running via Docker Compose: all 6 of 7 PromQL queries returned live TSDB data; the `sre_agent:diagnosis_latency:p99` recording rule requires a second scrape interval (30 s evaluation window) to populate after a fresh run
* Demo 25 requires LocalStack Pro and has not been validated in this session; the script structure and utility imports follow the established patterns from Demos 7, 8, and 19

## Troubleshooting

### Demo appears to fail under short CI timeout

Symptom: demos exit as timeout at 60 seconds in batch automation.

Fix: use larger per-process timeout for LLM-heavy demos (2, 3, 6, 7, 8, 19, 20, 21, 22).

### Ports 8080 or 8181 already in use

Symptom: bridge or agent startup fails.

Fix: free ports before running demos, or rely on Demo 7/8 auto-cleanup behavior.

### Missing or invalid Anthropic key

Symptom: LLM demos fail during diagnosis.

Fix: set `ANTHROPIC_API_KEY` and verify outbound connectivity.

### Demo 12 live mode fails

Symptom: `kubectl` returns API server connection errors.

Fix: verify `kubectl` context, cluster reachability, namespace, and workload names.

### LocalStack bridge callback unreachable

Symptom: SNS subscription remains pending or no diagnosis arrives.

Fix:

* `BRIDGE_HOST=127.0.0.1` for native LocalStack
* `BRIDGE_HOST=host.docker.internal` for Docker LocalStack

### Demo P6: Prometheus not reachable

Symptom: Phase 6 (PromQL queries) and Phase 7 (alert rules) print `Prometheus is NOT reachable` and show local fallback values instead of TSDB data.

Fix: Start Prometheus before running the demo.

```bash
docker compose -f docker-compose.deps.yml up -d prometheus
```

Verify it is healthy before running the demo:

```bash
curl -s http://localhost:9090/-/healthy
```

### Demo P6: Port 8080 already in use

Symptom: Phase 0 prints `Could not bind :8080` and the metrics HTTP server does not start.

Fix: Identify and stop the process occupying port 8080.

```bash
lsof -i :8080
kill -9 <PID>
```

If Demo 7 or Demo 25 was run recently without cleanup, the incident bridge webhook may still be running on port 8080.

### Demo P6: `sre_agent:diagnosis_latency:p99` returns no data

Symptom: The recording rule query returns `(no data yet — may need another scrape interval)`.

Root cause: The recording rule evaluates over a 5-minute rate window (`rate(...[5m])`). After a single demo run, fewer than two scrape intervals have passed, so the rolling rate returns `NaN`.

Fix: Wait 30 additional seconds and re-query, or run the demo a second time against the same Prometheus instance to accumulate more samples.

### Demo 25: LocalStack Chaos API unavailable

Symptom: Phase 8 (chaos injection) fails with a 404 or connection error when calling the Chaos API.

Root cause: The LocalStack Chaos API is a Pro-only feature. Community edition does not support `POST /chaos/faults`.

Fix: Ensure `LOCALSTACK_AUTH_TOKEN` is set and that `localstack/localstack-pro:latest` is running.

## Cross-reference alignment

* Demo 7 behavior here matches script reality and recent runtime validation. The separate `localstack_live_incident_demo.md` document contains both Community and Pro-oriented instructions. For this guide, LocalStack requirement is based on services used by the script itself.
* Validation outcomes align with `docs/reports/verification/live_demo_verification_report.md` and expand it with explicit runtime caveats observed during full-suite execution.
* Troubleshooting entries include issues highlighted in `docs/reports/analysis/live_demo_review_report.md` and issues observed during current execution.
* Demo P6 Prometheus configuration is defined in `infra/prometheus/prometheus.yml` (scrape config) and `infra/prometheus/rules/sre_agent_slo.yaml` (8 alert rules + 1 recording rule). These files are loaded automatically when Prometheus is started via `docker compose -f docker-compose.deps.yml up -d prometheus`.
* Demo 25 follows the same Pro-required pattern as Demo 8 (`live_demo_ecs_multi_service.py`). LocalStack Pro authentication is documented in `docs/testing/localstack_pro_usage_standard.md`.
* Prometheus metrics registry and metric definitions are centralized in `src/sre_agent/observability/metrics.py`. The `src/sre_agent/adapters/telemetry/metrics.py` re-exports all symbols for backward compatibility.

## References

* [Architecture overview](../architecture/architecture.md)
* [LocalStack incident deep-dive](localstack_live_incident_demo.md)
* [Live demo verification report](../reports/verification/live_demo_verification_report.md)
* [Live demo critical review](../reports/analysis/live_demo_review_report.md)
* [LocalStack Pro guide](../testing/localstack_pro_guide.md)
* [LocalStack Pro usage standard](../testing/localstack_pro_usage_standard.md)
* [Incident taxonomy and severity model](../architecture/models/incident_taxonomy.md)
* [Observability layer architecture](../architecture/layers/observability_layer.md)
* [Multi-agent coordination contract](../../AGENTS.md)
