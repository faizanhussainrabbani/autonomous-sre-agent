---
title: Live Incident Response Demonstrations
description: Execution-validated guide for running all Autonomous SRE Agent live demos across AWS, Azure, HTTP, EventBridge, Kubernetes operations, and multi-agent lock coordination.
ms.date: 2026-03-31
ms.topic: how-to
status: APPROVED
keywords:
  - live demos
  - localstack
  - incident response
  - kubernetes
  - multi-agent locks
---

## Overview

This guide is the canonical index for the live demo suite. It documents every `../../scripts/demo/live_demo_*.py` script, expected prerequisites, and execution mode.

Validation scope for this revision:

* Canonical suite now includes 18 executable demos after retiring low-value overlap and placeholder entries
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
* Pro demos: 8, plus full-feature execution for Demo 4
* No LocalStack required: 2, 3, 6, 10, 11, 12, 13, 18, 24

Community quick start:

```bash
docker run --rm -d -p 4566:4566 localstack/localstack:latest
```

Pro quick start:

```bash
localstack start -d --services=ecs,ec2,lambda,cloudwatch,sns,logs --pro --region=us-east-1
```

### LLM credentials

The LLM-driven demos (2, 3, 6, 7, 8, 19, 20, 21, 22, 24) require a valid Anthropic API key.

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

## Execution notes from validation runs

Observed during this guide update:

* Full batch execution across all `live_demo_*.py` scripts completed successfully (`25/25` pass)
* Single canonical script entry point is maintained per demo under `../../scripts/demo/`
* HTTP Demo 6 is stable in non-interactive mode (`SKIP_PAUSES=1`)
* Demo 12 live mode failed with `connection refused` when no reachable cluster context was configured
* Demo 19 completed successfully end to end, including retrieval-miss fallback path and per-error RAG scorecard output
* Demos 20, 21, and 22 completed against live API routes with LocalStack-backed incident/change context in non-interactive mode
* Demo 23 completed deterministic deny-then-allow remediation flow with LocalStack Lambda operator execution in non-interactive mode

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

## Cross-reference alignment

* Demo 7 behavior here matches script reality and recent runtime validation. The separate `localstack_live_incident_demo.md` document contains both Community and Pro-oriented instructions. For this guide, LocalStack requirement is based on services used by the script itself.
* Validation outcomes align with `docs/reports/verification/live_demo_verification_report.md` and expand it with explicit runtime caveats observed during full-suite execution.
* Troubleshooting entries include issues highlighted in `docs/reports/analysis/live_demo_review_report.md` and issues observed during current execution.

## References

* [Architecture overview](../architecture/architecture.md)
* [LocalStack incident deep-dive](localstack_live_incident_demo.md)
* [Live demo verification report](../reports/verification/live_demo_verification_report.md)
* [Live demo critical review](../reports/analysis/live_demo_review_report.md)
* [LocalStack Pro guide](../testing/localstack_pro_guide.md)
* [Incident taxonomy and severity model](../architecture/models/incident_taxonomy.md)
* [Multi-agent coordination contract](../../AGENTS.md)
