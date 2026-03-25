---
title: Live Incident Response Demonstrations
description: Execution-validated guide for running all Autonomous SRE Agent live demos across AWS, Azure, HTTP, EventBridge, Kubernetes operations, and multi-agent lock coordination.
ms.date: 2026-03-19
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

* All `../../scripts/demo/live_demo_*.py` scripts were executed in non-interactive mode (`SKIP_PAUSES=1`) with result capture
* Full-suite validation completed with `TOTAL 25`, `PASS 25`, `FAIL 0`, `TIMEOUT 0`
* Kubernetes Demo 12 was validated in both simulation mode and live `kubectl` mode
* Results were cross-checked against `docs/reports/live_demo_verification_report.md`, `docs/reports/live_demo_review_report.md`, and `docs/operations/localstack_live_incident_demo.md`

## Demo inventory

| Demo | Script | Focus Area | LocalStack | LLM Required |
|---|---|---|---|---|
| 1 | [../../scripts/demo/live_demo_1_telemetry_baseline.py](../../scripts/demo/live_demo_1_telemetry_baseline.py) | Phase 1 telemetry adapter-to-domain mapping | Community | No |
| 2 | [../../scripts/demo/live_demo_cascade_failure.py](../../scripts/demo/live_demo_cascade_failure.py) | Multi-service cascade correlation and event isolation | No | Yes (Anthropic) |
| 3 | [../../scripts/demo/live_demo_deployment_regression.py](../../scripts/demo/live_demo_deployment_regression.py) | Deployment-induced diagnosis, circuit breaker, certificate expiry | No | Yes (Anthropic) |
| 4 | [../../scripts/demo/live_demo_localstack_aws.py](../../scripts/demo/live_demo_localstack_aws.py) | AWS operators (ECS/Lambda/ASG) via LocalStack | Pro for full coverage | No |
| 5 | [../../scripts/demo/live_demo_http_server.py](../../scripts/demo/live_demo_http_server.py) | Compatibility wrapper delegating to Demo 6 | No | Yes (Anthropic) |
| 6 | [../../scripts/demo/live_demo_http_optimizations.py](../../scripts/demo/live_demo_http_optimizations.py) | HTTP end-to-end with token optimization and caching | No | Yes (Anthropic) |
| 7 | [../../scripts/demo/live_demo_localstack_incident.py](../../scripts/demo/live_demo_localstack_incident.py) | Lambda incident chain: alarm → SNS → bridge → diagnosis | Community or Pro | Yes (Anthropic) |
| 8 | [../../scripts/demo/live_demo_ecs_multi_service.py](../../scripts/demo/live_demo_ecs_multi_service.py) | ECS multi-service cascade and severity override workflow | Pro | Yes (Anthropic) |
| 9 | [../../scripts/demo/live_demo_cloudwatch_enrichment.py](../../scripts/demo/live_demo_cloudwatch_enrichment.py) | AlertEnricher with CloudWatch metrics and logs | Community | No |
| 10 | [../../scripts/demo/live_demo_eventbridge_reaction.py](../../scripts/demo/live_demo_eventbridge_reaction.py) | Event routing and timeline building via FastAPI TestClient simulation | No | No |
| 11 | [../../scripts/demo/live_demo_11_azure_operations.py](../../scripts/demo/live_demo_11_azure_operations.py) | Azure App Service and Functions operator behavior | No | No |
| 12 | [../../scripts/demo/live_demo_kubernetes_operations.py](../../scripts/demo/live_demo_kubernetes_operations.py) | Kubernetes restart and scale operations (simulation or real `kubectl`) | No | No |
| 13 | [../../scripts/demo/live_demo_multi_agent_lock_protocol.py](../../scripts/demo/live_demo_multi_agent_lock_protocol.py) | Lock schema, preemption, cooling-off, and human override simulation | No | No |
| 14 | [../../scripts/demo/live_demo_14_disk_exhaustion.py](../../scripts/demo/live_demo_14_disk_exhaustion.py) | Disk exhaustion anomaly simulation payload | No | No |
| 15 | [../../scripts/demo/live_demo_15_traffic_anomaly.py](../../scripts/demo/live_demo_15_traffic_anomaly.py) | Traffic anomaly simulation payload | No | No |
| 16 | [../../scripts/demo/live_demo_16_xray_tracing_placeholder.py](../../scripts/demo/live_demo_16_xray_tracing_placeholder.py) | X-Ray tracing placeholder for future phase work | No | No |

### Standardized numbering aliases

To support consistent naming without breaking existing commands, alias wrappers are available:

* `live_demo_02_cascade_failure.py` → `live_demo_cascade_failure.py`
* `live_demo_03_deployment_regression.py` → `live_demo_deployment_regression.py`
* `live_demo_04_localstack_aws.py` → `live_demo_localstack_aws.py`
* `live_demo_05_http_server.py` → `live_demo_http_server.py`
* `live_demo_06_http_optimizations.py` → `live_demo_http_optimizations.py`
* `live_demo_07_localstack_incident.py` → `live_demo_localstack_incident.py`
* `live_demo_08_ecs_multi_service.py` → `live_demo_ecs_multi_service.py`
* `live_demo_09_cloudwatch_enrichment.py` → `live_demo_cloudwatch_enrichment.py`
* `live_demo_10_eventbridge_reaction.py` → `live_demo_eventbridge_reaction.py`

## Prerequisites

### Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

### LocalStack

* Community demos: 1, 7, 9
* Pro demos: 8, plus full-feature execution for Demo 4
* No LocalStack required: 2, 3, 5, 6, 10, 11, 12, 13, 14, 15, 16

Community quick start:

```bash
docker run --rm -d -p 4566:4566 localstack/localstack:latest
```

Pro quick start:

```bash
localstack start -d --services=ecs,ec2,lambda,cloudwatch,sns,logs --pro --region=us-east-1
```

### LLM credentials

The LLM-driven demos (2, 3, 5, 6, 7, 8) require a valid Anthropic API key.

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

### Kubernetes live mode (Demo 12)

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

### Demo 5: HTTP compatibility wrapper

```bash
SKIP_PAUSES=1 python3 ../../scripts/demo/live_demo_http_server.py
```

Expected behavior: prints delegation notice and executes Demo 6.

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

### Demo 14: Disk exhaustion simulation

```bash
SKIP_PAUSES=1 python3 ../../scripts/demo/live_demo_14_disk_exhaustion.py
```

Expected behavior: prints deterministic `disk_exhaustion` payload.

### Demo 15: Traffic anomaly simulation

```bash
SKIP_PAUSES=1 python3 ../../scripts/demo/live_demo_15_traffic_anomaly.py
```

Expected behavior: prints deterministic `traffic_anomaly` payload.

### Demo 16: X-Ray tracing placeholder

```bash
SKIP_PAUSES=1 python3 ../../scripts/demo/live_demo_16_xray_tracing_placeholder.py
```

Expected behavior: prints placeholder scope for future trace-driven coverage.

## Execution notes from validation runs

Observed during this guide update:

* Full batch execution across all `live_demo_*.py` scripts completed successfully (`25/25` pass)
* Alias wrappers and canonical scripts both executed cleanly from `../../scripts/demo/`
* HTTP Demo 6 and its Demo 5 wrapper are stable in non-interactive mode (`SKIP_PAUSES=1`)
* Demo 12 live mode failed with `connection refused` when no reachable cluster context was configured

## Troubleshooting

### Demo appears to fail under short CI timeout

Symptom: demos exit as timeout at 60 seconds in batch automation.

Fix: use larger per-process timeout for LLM-heavy demos (2, 3, 5, 6, 7, 8).

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
* Validation outcomes align with `docs/reports/live_demo_verification_report.md` and expand it with explicit runtime caveats observed during full-suite execution.
* Troubleshooting entries include issues highlighted in `docs/reports/live_demo_review_report.md` and issues observed during current execution.

## References

* [Architecture overview](../architecture/architecture.md)
* [LocalStack incident deep-dive](localstack_live_incident_demo.md)
* [Live demo verification report](../reports/live_demo_verification_report.md)
* [Live demo critical review](../reports/live_demo_review_report.md)
* [LocalStack Pro guide](../testing/localstack_pro_guide.md)
* [Incident taxonomy and severity model](../architecture/models/incident_taxonomy.md)
* [Multi-agent coordination contract](../../AGENTS.md)
