---
title: LocalStack Live Incident Response Demo Guide
description: End-to-end walkthrough for inducing a Lambda failure in LocalStack and watching the Autonomous SRE Agent detect, diagnose, and explain the root cause via LLM-powered analysis.
author: SRE Agent Engineering Team
ms.date: 2026-03-11
ms.topic: tutorial
keywords:
  - localstack
  - incident response
  - lambda
  - cloudwatch
  - sns
  - live demo
  - autonomous sre agent
estimated_reading_time: 15
---

## Overview

This guide walks you through a fully interactive, end-to-end incident response demonstration. You will manually trigger a runtime failure in local AWS infrastructure (LocalStack), and watch the Autonomous SRE Agent automatically detect it, correlate telemetry, and generate an LLM-powered root cause analysis in real time.

By the end you will have proven four capabilities:

1. A vulnerable Lambda function crashes on demand inside LocalStack.
2. CloudWatch transitions an alarm to `ALARM` state and publishes to SNS.
3. An incident bridge webhook translates the AWS alarm JSON into the canonical `AnomalyAlert` format.
4. The SRE Agent's Intelligence Layer receives the alert, queries the vector database, and returns a structured diagnosis with root cause and remediation.

## Architecture

```text
┌──────────────────────────────────────────────────────────────────────┐
│                        LocalStack (port 4566)                        │
│                                                                      │
│  ┌─────────────┐    ┌───────────────────┐    ┌───────────────────┐  │
│  │   Lambda     │───▶│  CloudWatch Alarm  │───▶│   SNS Topic       │  │
│  │  (payment-   │    │  (Errors >= 1)     │    │  (sre-agent-      │  │
│  │  processor)  │    │                    │    │   alerts)         │  │
│  └─────────────┘    └───────────────────┘    └────────┬──────────┘  │
│                                                        │             │
└────────────────────────────────────────────────────────┼─────────────┘
                                                         │ HTTP POST
                                                         ▼
                                              ┌─────────────────────┐
                                              │  Incident Bridge    │
                                              │  (port 8080)        │
                                              │                     │
                                              │  AWS Alarm JSON     │
                                              │    → AnomalyAlert   │
                                              └────────┬────────────┘
                                                       │ HTTP POST
                                                       ▼
                                              ┌─────────────────────┐
                                              │  SRE Agent FastAPI  │
                                              │  (port 8181)        │
                                              │                     │
                                              │  /api/v1/diagnose   │
                                              │  RAG + Anthropic    │
                                              └─────────────────────┘
```

Five components participate in the workflow:

| Component              | Role                                                                                         | Port  |
|------------------------|----------------------------------------------------------------------------------------------|-------|
| LocalStack             | Simulates AWS Lambda, CloudWatch, and SNS locally via Docker.                                | 4566  |
| Vulnerable Lambda      | A Python function that crashes when invoked with `{"induce_error": true}`.                   | n/a   |
| CloudWatch Alarm       | Monitors the Lambda `Errors` metric and transitions to `ALARM` when the threshold is met.    | n/a   |
| Incident Bridge        | A lightweight FastAPI webhook that translates AWS Alarm JSON into the canonical alert format. | 8080  |
| SRE Agent FastAPI      | The Intelligence Layer endpoint that runs the RAG pipeline and Anthropic LLM diagnosis.      | 8181  |

## Prerequisites

Before starting, confirm the following tools are installed and accessible:

| Requirement              | Install Command                           | Verify Command                  |
|--------------------------|-------------------------------------------|---------------------------------|
| Docker                   | <https://docs.docker.com/get-docker/>     | `docker --version`              |
| LocalStack CLI           | `pip install localstack`                  | `localstack --version`          |
| AWS CLI Local (`awslocal`) | `pip install awscli-local`              | `awslocal --version`            |
| Python 3.11+             | System package manager                    | `python --version`              |
| Project virtual env       | `python -m venv .venv && source .venv/bin/activate` | `which python` |
| Project dependencies      | `pip install -e ".[dev]"`                | `python -c "import sre_agent"` |
| Anthropic API key         | Set `ANTHROPIC_API_KEY` in `.env`        | `echo $ANTHROPIC_API_KEY`       |

> [!IMPORTANT]
> LocalStack Community edition supports Lambda, CloudWatch, and SNS. You do NOT need LocalStack Pro for this demo.

## Step 1: Start LocalStack

Open a dedicated terminal and start LocalStack in detached mode:

```bash
localstack start -d
```

Verify it is healthy:

```bash
localstack status services
```

You should see `lambda`, `cloudwatch`, and `sns` listed as `available` or `running`.

> [!TIP]
> If you prefer Docker Compose, the project ships a `docker-compose.deps.yml` that includes LocalStack. Run `docker compose -f docker-compose.deps.yml up -d localstack` instead.

## Step 2: Deploy the Vulnerable Lambda

The demo uses a small Python handler at `scripts/mock_lambda.py` that crashes when it receives `{"induce_error": true}`.

### 2.1 Review the handler

```python
# scripts/mock_lambda.py
import json

def handler(event, context):
    if event.get("induce_error"):
        raise RuntimeError(
            "Database connection pool exhausted: "
            "active=128/128, wait_queue=347, "
            "avg_checkout_ms=12400"
        )
    return {"statusCode": 200, "body": json.dumps({"message": "Payment processed successfully"})}
```

When `induce_error` is truthy, the function raises a `RuntimeError` that mimics a real database connection pool exhaustion. CloudWatch records this as an invocation error.

### 2.2 Package and deploy

```bash
cd scripts
zip function.zip mock_lambda.py
cd ..

awslocal lambda create-function \
    --function-name payment-processor \
    --runtime python3.11 \
    --role arn:aws:iam::000000000000:role/lambda-role \
    --handler mock_lambda.handler \
    --zip-file fileb://scripts/function.zip
```

### 2.3 Verify deployment

```bash
awslocal lambda invoke \
    --function-name payment-processor \
    --cli-binary-format raw-in-base64-out \
    --payload '{}' \
    /dev/stdout
```

You should see `{"statusCode": 200, "body": "{\"message\": \"Payment processed successfully\"}"}`.

## Step 3: Configure CloudWatch Alarm and SNS

### 3.1 Create the SNS topic

```bash
awslocal sns create-topic --name sre-agent-alerts
```

Note the returned `TopicArn`. It will be `arn:aws:sns:us-east-1:000000000000:sre-agent-alerts`.

### 3.2 Create the CloudWatch alarm

This alarm fires when the Lambda `Errors` metric reaches 1 or more within a 60-second evaluation period:

```bash
awslocal cloudwatch put-metric-alarm \
    --alarm-name PaymentProcessorErrorSpike \
    --metric-name Errors \
    --namespace AWS/Lambda \
    --statistic Sum \
    --period 60 \
    --evaluation-periods 1 \
    --threshold 1 \
    --comparison-operator GreaterThanOrEqualToThreshold \
    --dimensions Name=FunctionName,Value=payment-processor \
    --alarm-actions arn:aws:sns:us-east-1:000000000000:sre-agent-alerts \
    --treat-missing-data notBreaching
```

### 3.3 Verify the alarm exists

```bash
awslocal cloudwatch describe-alarms \
    --alarm-names PaymentProcessorErrorSpike
```

The `StateValue` should be `INSUFFICIENT_DATA` or `OK` (no errors yet).

## Step 4: Start the SRE Agent FastAPI Server

Open a second terminal, activate the virtual environment, and start the agent:

```bash
source .venv/bin/activate
python scripts/live_demo_http_server.py
```

Wait until you see `✔  FastAPI server is up and responding to /health`.

The server listens on `http://127.0.0.1:8181` and exposes:

| Endpoint                  | Purpose                                           |
|---------------------------|---------------------------------------------------|
| `GET  /health`            | Liveness probe                                    |
| `POST /api/v1/diagnose`  | Trigger the RAG diagnostic pipeline               |
| `POST /api/v1/diagnose/ingest` | Seed runbooks into the vector database       |

> [!TIP]
> If you want to pre-seed the knowledge base with relevant runbooks before the demo, send a POST to `/api/v1/diagnose/ingest` with your payment-processor runbook content. This enables the RAG pipeline to retrieve more targeted evidence during diagnosis.

## Step 5: Start the Incident Bridge

Open a third terminal and start the bridge webhook:

```bash
source .venv/bin/activate
python scripts/localstack_bridge.py
```

You should see:

```text
LocalStack SNS → SRE Agent Bridge
Listening on http://127.0.0.1:8080/sns/webhook
Forwarding alerts to http://127.0.0.1:8181/api/v1/diagnose
```

### 5.1 Subscribe the bridge to SNS

Determine the correct endpoint URL based on how LocalStack is running:

| LocalStack Runs On  | Endpoint URL                                            |
|----------------------|---------------------------------------------------------|
| Host network directly (`localstack start`) | `http://127.0.0.1:8080/sns/webhook`     |
| Docker container     | `http://host.docker.internal:8080/sns/webhook`          |

Subscribe:

```bash
awslocal sns subscribe \
    --topic-arn arn:aws:sns:us-east-1:000000000000:sre-agent-alerts \
    --protocol http \
    --notification-endpoint http://host.docker.internal:8080/sns/webhook
```

> [!NOTE]
> If LocalStack is running natively on the host (not in Docker), replace `host.docker.internal` with `127.0.0.1`.

You should see a `SubscriptionConfirmation` message in the bridge terminal, followed by `✔  Subscription confirmed.`

## Step 6: Induce Chaos

With all three components running (LocalStack, Agent, Bridge), you are now the operator triggering the outage.

### 6.1 Invoke the Lambda with a destructive payload

```bash
awslocal lambda invoke \
    --function-name payment-processor \
    --cli-binary-format raw-in-base64-out \
    --payload '{"induce_error": true}' \
    output.txt
```

The invocation returns a `FunctionError` because the handler raised `RuntimeError`.

### 6.2 What happens automatically

The following chain executes without any further manual intervention:

```text
 1. Lambda ──────────────▶ Raises RuntimeError("Database connection pool exhausted")
                           CloudWatch Errors metric incremented to 1

 2. CloudWatch ──────────▶ Evaluates PaymentProcessorErrorSpike alarm
                           Errors (1) >= Threshold (1) → transitions to ALARM

 3. SNS ─────────────────▶ Publishes alarm state-change notification
                           HTTP POST → http://...:8080/sns/webhook

 4. Incident Bridge ─────▶ Parses AWS Alarm JSON
                           Builds canonical AnomalyAlert payload
                           Forwards POST → http://127.0.0.1:8181/api/v1/diagnose

 5. SRE Agent ───────────▶ Receives AnomalyAlert
                           Embeds alert → queries vector store (RAG)
                           Constructs timeline → filters relevant signals
                           Sends evidence to Anthropic LLM
                           Returns structured diagnosis with:
                             • Root cause explanation
                             • Severity classification
                             • Suggested remediation steps
                             • Confidence score
                             • Audit trail
```

### 6.3 Expected terminal output

In the **Bridge terminal** you will see:

```text
🚨 CloudWatch Alarm Triggered: PaymentProcessorErrorSpike
   NewStateReason: Threshold Crossed: 1 datapoint [1.0] >= 1.0
   → Forwarding to SRE Agent at http://127.0.0.1:8181/api/v1/diagnose ...

🤖 Agent Diagnosis Output:
{
  "status": "success",
  "alert_id": "...",
  "severity": "SEV2",
  "confidence": 0.85,
  "root_cause": "Lambda function payment-processor experienced a runtime crash...",
  "remediation": "1. Increase database connection pool limits...",
  "requires_approval": false,
  "citations": [...],
  "audit_trail": [...]
}
```

## Step 7: Validate and Iterate

### 7.1 Confirm the alarm state

```bash
awslocal cloudwatch describe-alarms \
    --alarm-names PaymentProcessorErrorSpike \
    --query 'MetricAlarms[0].StateValue'
```

The value should be `"ALARM"`.

### 7.2 Invoke again to test repeated detection

```bash
awslocal lambda invoke \
    --function-name payment-processor \
    --cli-binary-format raw-in-base64-out \
    --payload '{"induce_error": true}' \
    output.txt
```

If the SRE Agent has semantic caching enabled (Phase 2.2), the second invocation's diagnosis returns nearly instantly from cache, saving all LLM token costs.

### 7.3 Invoke with a healthy payload

```bash
awslocal lambda invoke \
    --function-name payment-processor \
    --cli-binary-format raw-in-base64-out \
    --payload '{}' \
    output.txt
```

This succeeds without errors. Once the CloudWatch alarm re-evaluates, it transitions back to `OK` and SNS fires a non-alarm notification that the bridge safely ignores.

## Terminal Layout Reference

For a live demo presentation, arrange four terminal panes:

```text
┌────────────────────────────┬────────────────────────────┐
│  Terminal 1: LocalStack    │  Terminal 2: SRE Agent     │
│  localstack start -d       │  python scripts/           │
│  awslocal commands...      │    live_demo_http_server.py│
├────────────────────────────┼────────────────────────────┤
│  Terminal 3: Bridge        │  Terminal 4: Chaos Trigger │
│  python scripts/           │  awslocal lambda invoke    │
│    localstack_bridge.py    │    --payload '{"induce_    │
│                            │     error": true}'         │
└────────────────────────────┴────────────────────────────┘
```

## Troubleshooting

| Symptom                                    | Cause                                              | Resolution                                                                       |
|--------------------------------------------|-----------------------------------------------------|---------------------------------------------------------------------------------|
| Bridge never receives a webhook            | SNS subscription endpoint is unreachable            | Use `http://host.docker.internal:8080` if LocalStack runs in Docker.             |
| Agent returns HTTP 500 on `/api/v1/diagnose` | `ANTHROPIC_API_KEY` is missing or invalid         | Set the key in your `.env` or export it: `export ANTHROPIC_API_KEY=sk-...`       |
| `awslocal: command not found`              | `awscli-local` is not installed                     | Run `pip install awscli-local`.                                                  |
| CloudWatch alarm stays `INSUFFICIENT_DATA` | Lambda error metric was not recorded by LocalStack  | Invoke the Lambda with `induce_error` first, then wait up to 60 seconds.         |
| `ConnectionRefused` on port 8181           | SRE Agent server is not running                     | Start it: `python scripts/live_demo_http_server.py`.                             |
| Bridge confirms subscription but no alarm fires | Alarm period has not elapsed yet                | Wait 60 seconds after the Lambda error for the alarm evaluation period to pass.  |

## Cleanup

Remove all LocalStack resources and stop services:

```bash
awslocal lambda delete-function --function-name payment-processor
awslocal sns delete-topic --topic-arn arn:aws:sns:us-east-1:000000000000:sre-agent-alerts
awslocal cloudwatch delete-alarms --alarm-names PaymentProcessorErrorSpike
localstack stop
```

Delete the generated zip file:

```bash
rm -f scripts/function.zip output.txt
```

## Alternative: Showcasing LLM Reasoning Without LocalStack

If the goal is to highlight how the LLM reasons through genuine incidents (without setting up LocalStack infrastructure), use the existing diagnostics demo:

```bash
source .venv/bin/activate
python scripts/live_demo_diagnostics.py
```

This script bypasses HTTP and optimizations entirely, pumping a complex simulated database crash directly into the Anthropic LLM. It prints the step-by-step reasoning to the console in a formatted output, making it the fastest way to showcase the agent's analytical capabilities to an audience.

## Related Resources

| Resource                                     | Path                                           |
|----------------------------------------------|-------------------------------------------------|
| Incident Bridge script                       | `scripts/localstack_bridge.py`                  |
| Mock Lambda handler                          | `scripts/mock_lambda.py`                        |
| HTTP server demo                             | `scripts/live_demo_http_server.py`              |
| HTTP optimizations demo                      | `scripts/live_demo_http_optimizations.py`       |
| AWS remediation operators demo (LocalStack)  | `scripts/live_demo_localstack_aws.py`           |
| LocalStack Pro testing guide                 | `docs/testing/localstack_pro_guide.md`          |
| External dependencies reference              | `docs/operations/external_dependencies.md`      |
