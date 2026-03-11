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

> [!IMPORTANT]
> **Lambda v2 asynchronous creation (the 30-minute hang):** Since LocalStack 2.0, `create-function` returns HTTP 201 immediately and places the function in `Pending` state. It becomes `Active` only after LocalStack initialises the Docker runtime container. Any `invoke` call issued while the function is still `Pending` throws a `ResourceConflictException` and the AWS CLI retries indefinitely with no visible output — causing an apparent infinite hang.
>
> **The fix:** start LocalStack with `LOCALSTACK_LAMBDA_SYNCHRONOUS_CREATE=1`. The `LOCALSTACK_` prefix is required when passing the variable through the LocalStack CLI:
>
> ```bash
> LOCALSTACK_LAMBDA_SYNCHRONOUS_CREATE=1 localstack start -d
> ```
>
> **Or**, if LocalStack is already running, always follow `create-function` with an explicit boto3/CLI wait (covered in Step 2.3 below). Never invoke the function before confirming `State: Active`.

> [!NOTE]
> **AWS region:** LocalStack Pro derives the default region from your `~/.aws/config` or the `AWS_DEFAULT_REGION` environment variable. All ARNs produced by LocalStack will use that region (e.g. `eu-west-3`). Run `aws configure get region` to see yours, then substitute it wherever `us-east-1` appears in command examples below.

Open a dedicated terminal and start LocalStack Pro in detached mode:

```bash
localstack auth set-token <your-token>
LOCALSTACK_LAMBDA_SYNCHRONOUS_CREATE=1 localstack start -d
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
zip -j function.zip mock_lambda.py
cd ..

awslocal lambda create-function \
    --function-name payment-processor \
    --runtime python3.11 \
    --role arn:aws:iam::000000000000:role/lambda-role \
    --handler mock_lambda.handler \
    --zip-file fileb://scripts/function.zip \
    --no-cli-pager
```

> [!NOTE]
> `create-function` returns immediately with `"State": "Pending"`. Do **not** invoke it yet — doing so causes `ResourceConflictException` and the CLI retries silently forever.

### 2.3 Wait for the function to become Active

Always run this immediately after `create-function`:

```bash
awslocal lambda wait function-active-v2 --function-name payment-processor
```

The waiter polls `GetFunction` every 5 seconds for up to 300 seconds. With a pre-pulled `python:3.11` image it completes in under 15 seconds. If it times out, check LocalStack logs:

```bash
docker logs localstack-main 2>&1 | grep -i "lambda\|error\|failed" | tail -20
```

Pre-pull the image once to eliminate the delay on future runs:

```bash
docker pull public.ecr.aws/lambda/python:3.11
```

### 2.4 Verify deployment

```bash
awslocal lambda invoke \
    --function-name payment-processor \
    --cli-binary-format raw-in-base64-out \
    --payload '{}' \
    --no-cli-pager \
    /dev/stdout
```

You should see `{"statusCode": 200, "body": "{\"message\": \"Payment processed successfully\"}"}`.

## Step 3: Configure CloudWatch Alarm and SNS

### 3.1 Create the SNS topic

```bash
awslocal sns create-topic --name sre-agent-alerts --no-cli-pager
```

Note the returned `TopicArn`. The region in the ARN matches your configured AWS region:

```bash
# Capture it for use in subsequent commands:
TOPIC_ARN=$(awslocal sns create-topic --name sre-agent-alerts --query TopicArn --output text)
echo $TOPIC_ARN
# Example output: arn:aws:sns:eu-west-3:000000000000:sre-agent-alerts
```

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
    --alarm-actions "$TOPIC_ARN" \
    --treat-missing-data notBreaching \
    --no-cli-pager
```

### 3.3 Verify the alarm exists

```bash
awslocal cloudwatch describe-alarms \
    --alarm-names PaymentProcessorErrorSpike \
    --query 'MetricAlarms[0].{State:StateValue,Actions:AlarmActions}' \
    --no-cli-pager
```

The `StateValue` should be `INSUFFICIENT_DATA` or `OK` (no errors yet).

## Step 4: Start the SRE Agent FastAPI Server

Open a second terminal and start the server directly via `uvicorn`. Do **not** use `python scripts/live_demo_http_server.py` here — that script is self-contained and shuts the server down after one request.

```bash
source .venv/bin/activate
.venv/bin/uvicorn sre_agent.api.main:app --host 127.0.0.1 --port 8181
```

For background operation (so the terminal stays free for other commands):

```bash
nohup .venv/bin/uvicorn sre_agent.api.main:app --host 127.0.0.1 --port 8181 \
    > /tmp/sre_agent.log 2>&1 &
echo "Agent PID: $!"
```

Verify it is healthy:

```bash
curl -s http://127.0.0.1:8181/health
```

The server listens on `http://127.0.0.1:8181` and exposes:

| Endpoint                       | Purpose                                      |
|--------------------------------|----------------------------------------------|
| `GET  /health`                 | Liveness probe                               |
| `POST /api/v1/diagnose`        | Trigger the RAG diagnostic pipeline          |
| `POST /api/v1/diagnose/ingest` | Seed runbooks into the vector database       |

> [!TIP]
> Seed the knowledge base with a payment-processor runbook before the demo. The RAG pipeline retrieves more targeted evidence during diagnosis when the runbook is present.

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
    --topic-arn "$TOPIC_ARN" \
    --protocol http \
    --notification-endpoint http://host.docker.internal:8080/sns/webhook \
    --no-cli-pager
```

> [!NOTE]
> If LocalStack is running natively on the host (not in Docker), replace `host.docker.internal` with `127.0.0.1`.

> [!NOTE]
> **LocalStack Pro** auto-confirms HTTP subscriptions and returns a full `SubscriptionArn` immediately. You will **not** see a separate `SubscriptionConfirmation` request in the bridge log. A `"pending confirmation"` response means the SNS delivery to the bridge endpoint failed — check that the endpoint URL is reachable from inside the LocalStack container.

## Step 6: Induce Chaos

With all three components running (LocalStack, Agent, Bridge), you are now the operator triggering the outage.

### 6.1 Invoke the Lambda with a destructive payload

```bash
awslocal lambda invoke \
    --function-name payment-processor \
    --cli-binary-format raw-in-base64-out \
    --payload '{"induce_error": true}' \
    --no-cli-pager \
    output.txt && cat output.txt
```

The invocation returns `"FunctionError": "Unhandled"` because the handler raised `RuntimeError`. The `output.txt` file contains the error details including `errorMessage: Database connection pool exhausted`.

### 6.2 Force the CloudWatch alarm to ALARM state

LocalStack does not automatically evaluate metric alarms on a 60-second schedule during demos. Use `set-alarm-state` to instantly trigger the SNS notification chain:

```bash
awslocal cloudwatch set-alarm-state \
    --alarm-name PaymentProcessorErrorSpike \
    --state-value ALARM \
    --state-reason "Threshold Crossed: 1 datapoint [1.0] was >= threshold (1.0)" \
    --no-cli-pager
```

This immediately publishes the alarm state-change to SNS, which delivers the HTTP notification to the bridge, which forwards the `AnomalyAlert` to the SRE Agent.

### 6.3 What happens automatically

After `set-alarm-state`, the following chain executes without any further manual intervention:

```text
 1. Lambda ──────────────▶ Raises RuntimeError("Database connection pool exhausted")
                           CloudWatch Errors metric incremented to 1

 2. set-alarm-state ─────▶ Forces PaymentProcessorErrorSpike → ALARM
                           (bypasses the 60 s evaluation window)

 3. SNS ─────────────────▶ Publishes alarm state-change notification
                           HTTP POST → http://host.docker.internal:8080/sns/webhook

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

### 6.4 Expected terminal output

In the **Bridge terminal** you will see:

```text
🚨 CloudWatch Alarm Triggered: PaymentProcessorErrorSpike
   NewStateReason: Threshold Crossed: 1 datapoint [1.0] was >= threshold (1.0). Lambda Errors exceeded.
   → Forwarding to SRE Agent at http://127.0.0.1:8181/api/v1/diagnose ...

🤖 Agent Diagnosis Output:
{
  "status": "success",
  "alert_id": "136a7ca7-58aa-49a8-8a99-213d203931ed",
  "severity": "SEV3",
  "confidence": 0.722,
  "root_cause": "Database connection pool exhaustion due to high Lambda concurrency during peak load,
                 causing payment-processor Lambda invocations to fail with RuntimeError",
  "remediation": "Immediately throttle Lambda concurrency to 50 to reduce database pressure,
                  then implement RDS Proxy for connection multiplexing, increase max_connections,
                  and add exponential backoff with jitter for database connection retries",
  "requires_approval": true,
  "citations": [{"source": "runbooks/payment-processor-oom.md", "relevance_score": 0.764}],
  "audit_trail": [
    "retrieval/embedding_alert: {}",
    "retrieval/vector_search_complete: {'results_count': 1}",
    "reasoning/hypothesis_generated: {'confidence': 0.76}",
    "validation/hypothesis_validated: {'agrees': True}",
    "classification/diagnosis_complete: {'severity': 'SEV3', 'confidence': 0.722}"
  ]
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

## Running the Complete Demo as a Single Script

A fully automated orchestrator script executes every phase sequentially with
colour-coded output and interactive ENTER-key pauses between phases, so you
can narrate each step during a live presentation.

```bash
source .venv/bin/activate
python scripts/live_demo_localstack_incident.py
```

The script handles everything in order:

| Phase | Action |
|-------|--------|
| 0     | Pre-flight: verify LocalStack, packages, ports |
| 1     | Package and deploy the Lambda; wait for `Active` |
| 2     | Create the SNS topic and CloudWatch alarm |
| 3     | Start the SRE Agent FastAPI server (port 8181) |
| 4     | Start the Incident Bridge webhook server (port 8080) |
| 5     | Subscribe the bridge to the SNS topic |
| 6     | Seed the knowledge base with the payment-processor runbook |
| 7     | Invoke the Lambda with the destructive payload |
| 8     | Force the CloudWatch alarm and fire the full detection chain |
| 9     | Display the structured LLM diagnosis with full audit trail |
| 10    | Clean up: delete Lambda, alarm, SNS topic; terminate servers |

To skip pauses (CI/non-interactive mode):

```bash
SKIP_PAUSES=1 python scripts/live_demo_localstack_incident.py
```

To override defaults:

```bash
LOCALSTACK_ENDPOINT=http://localhost:4566 \
AWS_DEFAULT_REGION=eu-west-3 \
python scripts/live_demo_localstack_incident.py
```

> [!IMPORTANT]
> LocalStack must already be running before you start the script. Start it in a separate terminal with `LOCALSTACK_LAMBDA_SYNCHRONOUS_CREATE=1 localstack start -d` and wait for it to become healthy (`localstack wait -t 60`) before running the demo.

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
| `create-function` or invoke hangs forever  | Function is in `Pending` state; CLI retries `ResourceConflictException` silently | Always run `awslocal lambda wait function-active-v2 --function-name payment-processor` before invoking. Start LocalStack with `LOCALSTACK_LAMBDA_SYNCHRONOUS_CREATE=1`. |
| Lambda stays `Pending` longer than 2 min   | Runtime Docker image not cached on host             | Pre-pull: `docker pull public.ecr.aws/lambda/python:3.11`                        |
| No alarm fires after `lambda invoke`       | LocalStack does not auto-evaluate alarms on schedule | Force the alarm: `awslocal cloudwatch set-alarm-state --alarm-name PaymentProcessorErrorSpike --state-value ALARM --state-reason "manual"` |
| Agent returns HTTP 500 on `/api/v1/diagnose` | `ANTHROPIC_API_KEY` is missing or invalid         | Export it: `export ANTHROPIC_API_KEY=sk-...`                                     |
| `awslocal: command not found`              | `awscli-local` is not installed                     | Run `pip install awscli-local`.                                                  |
| `ConnectionRefused` on port 8181           | Used `live_demo_http_server.py` which self-terminates | Use `nohup .venv/bin/uvicorn sre_agent.api.main:app --host 127.0.0.1 --port 8181 > /tmp/sre_agent.log 2>&1 &` instead. |
| SNS subscription stays `pending confirmation` | Bridge endpoint unreachable from LocalStack container | Use `http://host.docker.internal:8080` on macOS/Docker Desktop. Check bridge is listening: `curl http://127.0.0.1:8080/health`. |
| ARN region mismatch errors                 | LocalStack uses your configured AWS region, not `us-east-1` | Run `aws configure get region` and substitute that region in all ARNs. Use `$TOPIC_ARN` variable from Step 3.1. |

## Cleanup

Remove all LocalStack resources and stop services:

```bash
awslocal lambda delete-function --function-name payment-processor
awslocal sns delete-topic --topic-arn "$TOPIC_ARN"
awslocal cloudwatch delete-alarms --alarm-names PaymentProcessorErrorSpike

# Stop background processes
lsof -ti :8181 | xargs kill -9 2>/dev/null
lsof -ti :8080 | xargs kill -9 2>/dev/null

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
