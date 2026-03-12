---
title: Live Incident Response Demonstrations
description: End-to-end guides for running the Autonomous SRE Agent against LocalStack with realistic incident scenarios.
ms.date: 2026-03-12
ms.topic: how-to
status: APPROVED
keywords:
  - localstack
  - incident response
  - demonstration
  - ecs
  - lambda
---

# Live Incident Response Demonstrations

This document serves as a landing page for end-to-end live demonstrations of the Autonomous SRE Agent responding to simulated infrastructure incidents using LocalStack Pro as the cloud provider.

---

## Overview

Two fully-scripted demonstrations showcase the agent's detection, diagnosis, and remediation capabilities in realistic multi-service failure scenarios:

| Demo | Services | Incident Pattern | Learning Focus |
|---|---|---|---|
| **Demo 7: Lambda Cascade** | Single Lambda function + payment processing | Synchronous Lambda timeout → cascade to dependent services | Single-service root cause identification, retry storm detection |
| **Demo 8: ECS Multi-Service Cascade** | Order service + payment service (2-tier dependency) | Memory exhaustion (OOM kill) → upstream failure → downstream CPU spike | Multi-service cascade diagnosis, correlated signals enrichment, LLM cross-validation |

Both demos include:
- ✅ Real CloudWatch alarms + SNS notifications
- ✅ Agent-side anomaly detection ingesting correlated signals
- ✅ LLM-powered root cause hypothesis + cross-validation
- ✅ Severity classification and human override API
- ✅ Full audit trail with LLM decision tracking

---

## Demo 7: Lambda Incident Cascade

**File:** [localstack_live_incident_demo.md](localstack_live_incident_demo.md)

### Scenario

A vulnerable Lambda function (`payment-processor-lambda`) written in Python handles payment requests from an order service. During a traffic spike:

1. Lambda memory exhaustion (512 MB limit hit due to request buffering)
2. Lambda crash (exit code 137 = OOMKilled)
3. Upstream order service clients retry payments aggressively
4. Retry storm → dependent services (downstream) start timing out

### Agent Response

The SRE Agent:
1. Detects `LambdaErrors` spike via CloudWatch metrics
2. Ingests Lambda CloudWatch Logs showing OOM kill
3. Generates hypothesis: "Memory exhaustion in payment processor"
4. Suggests remediation: increase Lambda memory + implement DLQ + add circuit breaker

### Duration

~3 minutes end-to-end (most time spent waiting for LLM diagnosis).

### Run It

```bash
# Prerequisites: LocalStack Pro running, Python venv active
cd /Users/faizanhussain/Documents/Project/Practice/AiOps
SKIP_PAUSES=1 python scripts/live_demo_localstack_incident.py > /tmp/demo7.log 2>&1 &
tail -f /tmp/demo7.log
```

---

## Demo 8: ECS Multi-Service Cascade

**File:** [ECS Multi-Service Cascade Demo](live_demo_ecs_multi_service.md) *(currently implemented inline in script; see [scripts/live_demo_ecs_multi_service.py](../../scripts/live_demo_ecs_multi_service.py))*

### Scenario

Two co-located ECS services simulate a realistic microservice architecture:

1. **Order Service** (upstream) — handles order placement
   - 3 running tasks in steady state
   - Memory-constrained: 512 MB per task
   - During traffic spike: all 3 tasks OOM-killed simultaneously

2. **Payment Service** (downstream) — processes payments for orders
   - 2 running tasks in steady state
   - Depends on order-service for order context
   - When order-service goes down: retry storm → CPU spike to 94%

### Agent Response

The SRE Agent ingests two independent alarms:

**Phase 8 — order-service crash:**
- Detects: RunningTaskCount dropped from 3 → 0
- Correlated signals: metric trend (3-minute decline), error logs showing OOM kills
- Hypothesis: "All order-service tasks terminated due to memory exhaustion"
- Confidence: 74.7% (LLM cross-validation disagrees slightly on depth)

**Phase 10 — payment-service cascade:**
- Detects: CpuUtilized spiked from 45% → 94%
- Correlated signals: error logs showing Stripe timeout + thread pool exhaustion
- Hypothesis: "Retry storm from upstream order-service outage"
- Confidence: 75.2% (LLM validates cascade pattern)

### Severity Override Demo (Phase 12)

Shows the human operator API in action:
- Agent auto-classified payment alert as SEV2 (critical)
- Operator uses POST `/api/v1/incidents/{alert_id}/severity-override` to downgrade to SEV3
- System halts autonomous remediation while manual recovery is in progress

### Duration

~5 minutes end-to-end (includes two LLM diagnoses).

### Run It

```bash
# Prerequisites: LocalStack Pro running, Python venv active, ports 8080/8181 free
cd /Users/faizanhussain/Documents/Project/Practice/AiOps
SKIP_PAUSES=1 python scripts/live_demo_ecs_multi_service.py > /tmp/demo8.log 2>&1 &
tail -f /tmp/demo8.log
```

### Key Differences from Demo 7

- **Correlated signals enrichment:** Demo 8 populates the `correlated_signals` field with actual metric trends + log excerpts, simulating Improvement Area 1 from the AWS data collection strategy
- **Two independent LLM calls:** Both order-service and payment-service alarms trigger separate diagnoses (vs. Demo 7's single-service focus)
- **Severity override workflow:** Human operator can intervene mid-cascade to prevent runaway autonomous actions
- **Service dependency causality:** Demonstrates how the agent must trace causality upward (payment CPU spike ← order-service outage) rather than treating each alert independently

---

## Prerequisites

### LocalStack Pro

Both demos require LocalStack Pro (not the free tier) running natively on port 4566:

```bash
# Start LocalStack Pro
localstack start -d \
  --services=ecs,ec2,cloudwatch,sns,logs,xray \
  --pro \
  --region=eu-west-3

# Check status
curl http://localhost:4566/_localstack/health
```

### Python Environment

```bash
cd /Users/faizanhussain/Documents/Project/Practice/AiOps
source .venv/bin/activate
pip install -r requirements.txt  # boto3, httpx, uvicorn, fastapi, etc.
```

### Environment Variables

```bash
# Copy example to .env
cp .env.example .env

# Fill in:
ANTHROPIC_API_KEY=sk-ant-...  # Your Anthropic API key
LOCALSTACK_AUTH_TOKEN=...      # Your LocalStack Pro auth token
```

### Cleanup Between Runs

```bash
# Kill any lingering processes
lsof -ti :8080 | xargs kill -9 2>/dev/null
lsof -ti :8181 | xargs kill -9 2>/dev/null

# Optional: reset LocalStack
localstack stop
localstack start -d ...
```

---

## Interpreting Demo Output

### Agent Startup (Phase 3)

```
▶  Launch uvicorn sre_agent.api.main:app
✔  SRE Agent UP — {'status': 'ok'}
```

The agent's FastAPI server starts on port 8181. This is where the incident bridge sends alerts via `/api/v1/diagnose`.

### Bridge Startup (Phase 4)

```
▶  Launch localstack_bridge.py
✔  Bridge UP — {'status': 'healthy', 'component': 'localstack-bridge'}
```

The incident bridge starts on port 8080 and proxies SNS notifications to the `/api/v1/diagnose` endpoint.

### Diagnosis Response (Phase 8/10)

```
✔  Diagnosis received in 22.0 s

Root Cause:
  Memory exhaustion (OOM kill) in order-service ECS tasks...

Suggested Remediation:
  • Scale up ECS service...
  • Update task definition...
  • Enable auto-scaling...
```

The LLM response includes:
- Severity classification (SEV1-4)
- Root cause hypothesis
- Suggested remediation steps
- Confidence score
- Evidence citations (which runbooks matched)
- Audit trail (all intermediate steps)

---

## Troubleshooting

### 422 Unprocessable Entity on Alarm POST

**Symptom:** `/api/v1/diagnose` returns HTTP 422

**Root Cause:** `anomaly_type` enum value is invalid or `correlated_signals` structure doesn't match the `CorrelatedSignals` Pydantic model.

**Fix:** Ensure `anomaly_type` is one of: `latency_spike`, `error_rate_surge`, `memory_pressure`, `disk_exhaustion`, `certificate_expiry`, `multi_dimensional`, `deployment_induced`, `invocation_error_surge`, `traffic_anomaly`.

### ClusterNotFoundException During Chaos Phase

**Symptom:** Phase 7 fails with "Cluster not found"

**Root Cause:** LocalStack GC'd the ECS cluster because Fargate tasks couldn't be scheduled (no container runtime). Set `desiredCount=0` when creating services to prevent task scheduling.

**Fix:** Demo scripts already handle this — ensure you're running the latest version.

### Diagnosis Hangs After 60s Timeout

**Symptom:** Agent never responds to alarm POST, request times out

**Root Cause:** LLM API call to Anthropic is blocked or very slow.

**Fix:** 
1. Verify `ANTHROPIC_API_KEY` is set and valid
2. Check network connectivity to Anthropic API
3. Increase timeout or run with `--timeout 120` if needed

### Bridge Subscription Shows "Pending Confirmation"

**Symptom:** SNS subscription remains in "PendingConfirmation" state

**Root Cause:** Native LocalStack Pro automatically confirms HTTP subscriptions, but the bridge may not be reachable from LocalStack's internal network.

**Fix:** Use `BRIDGE_HOST=127.0.0.1` (default) for native LocalStack. Use `BRIDGE_HOST=host.docker.internal` only if running LocalStack in Docker.

---

## Next Steps

### Extend the Demos

To add your own incident scenario:

1. Create a new ECS service or Lambda function in the demo script
2. Add a CloudWatch alarm that simulates failure (e.g., high error rate)
3. Add runbook content to the knowledge base (`scripts/ingest_runbooks.py`)
4. Trigger the alarm and observe the agent's diagnosis

### Integrate into CI/CD

The demos can be integrated into the CI/CD pipeline as regression tests:

```bash
# In GitHub Actions workflow:
- name: Run Live Demo (Regression Test)
  run: |
    SKIP_PAUSES=1 python scripts/live_demo_ecs_multi_service.py
    # Assert all 14 phases passed (check exit code)
```

---

## References

- [Autonomous SRE Agent — Architecture Overview](../architecture/architecture.md)
- [LocalStack Pro Guide](../testing/localstack_pro_guide.md)
- [AWS Data Collection Improvements](aws_data_collection_improvements.md)
- [Incident Taxonomy & Severity Model](../architecture/models/incident_taxonomy.md)
