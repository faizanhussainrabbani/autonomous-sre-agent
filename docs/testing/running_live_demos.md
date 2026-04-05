---
title: Running Live Demos
description: Single process for starting LocalStack Pro and running any live demo in this repository.
ms.date: 2026-04-05
ms.topic: how-to
author: SRE Agent Engineering Team
status: APPROVED
---

## Before You Start

Every demo follows the same three steps:

```
1. Set up .env          (one time)
2. Start LocalStack     (one command)
3. Run the demo         (one command)
```

There is one way to authenticate, one way to start LocalStack, and one way to run demos.

## Step 1: Configure .env (One Time)

Copy the example and fill in your tokens:

```bash
cp .env.example .env
```

Edit `.env` and set these values:

```bash
# Required for all LocalStack demos
LOCALSTACK_AUTH_TOKEN=ls-your-token-here

# Required for demos that use LLM diagnosis (marked with * below)
ANTHROPIC_API_KEY=sk-ant-your-key-here
# OR
OPENAI_API_KEY=sk-your-key-here
```

Get your LocalStack token at [app.localstack.cloud](https://app.localstack.cloud/workspace/auth-tokens).

This is the **only** place tokens are configured. No other files, no JSON configs, no manual exports.

## Step 2: Start LocalStack Pro (One Command)

```bash
bash scripts/dev/setup_deps.sh start
```

This starts LocalStack Pro via Docker Compose with the correct image, services, ports, and tuning variables. It reads `LOCALSTACK_AUTH_TOKEN` from your `.env` automatically.

Verify it is ready:

```bash
bash scripts/dev/localstack_check.sh
```

Expected output:

```
━━━ LocalStack Pro Readiness Check ━━━

[✓] Container image: localstack/localstack-pro:latest
[✓] Edition: pro
[✓] Services: ready=12/12

[✓] All checks passed — LocalStack Pro is ready.
```

You only need to do this once per session. LocalStack stays running until you stop it.

## Step 3: Run a Demo (One Command)

Every demo runs the same way:

```bash
SKIP_PAUSES=1 .venv/bin/python scripts/demo/<demo_script>.py
```

Remove `SKIP_PAUSES=1` if you want interactive mode (press ENTER between phases).

## Demo Catalog

### Tier 1: No External Dependencies

These demos run without LocalStack or LLM keys.

| Demo | Script | What It Proves |
|------|--------|---------------|
| 11 — Azure Operations | `live_demo_11_azure_operations.py` | Azure App Service and Functions operator adapters |
| 12 — Kubernetes Operations | `live_demo_kubernetes_operations.py` | Kubernetes pod restart and scaling operators |
| 13 — Multi-Agent Lock Protocol | `live_demo_multi_agent_lock_protocol.py` | Redis-based lock acquisition, preemption, cooldown |
| 17 — Action Lock Orchestration | `live_demo_17_action_lock_orchestration.py` | Action layer lock semantics and priority ordering |
| 18 — etcd Lock Flow | `live_demo_18_etcd_action_lock_flow.py` | etcd-backed distributed locking |
| 25 — Kubernetes Log Fallback | `live_demo_25_kubernetes_log_fallback.py` | Log fetching fallback chain |
| 10 — EventBridge Timeline | `live_demo_eventbridge_reaction.py` | Canonical event timeline construction |
| Phase 3 — Remediation E2E | `live_demo_phase3_remediation_e2e.py` | Remediation planning and execution pipeline |

### Tier 2: LocalStack Only (No LLM Key)

These require LocalStack Pro running but no LLM API key.

| Demo | Script | What It Proves |
|------|--------|---------------|
| 1 — Telemetry Baseline | `live_demo_1_telemetry_baseline.py` | CloudWatch metric publishing and retrieval |
| 4 — AWS Operators | `live_demo_localstack_aws.py` | ECS stop task, Lambda concurrency cap, ASG scale-out, circuit breaker |
| 9 — CloudWatch Enrichment | `live_demo_cloudwatch_enrichment.py` | Metric + log enrichment from CloudWatch into alert context |
| 23 — AI Says No | `live_demo_23_ai_says_no_before_it_acts.py` | Safety guardrail blocks dangerous remediation actions |

### Tier 3: LocalStack + LLM Key

These require both LocalStack Pro and an LLM API key (`ANTHROPIC_API_KEY` or `OPENAI_API_KEY`).

| Demo | Script | What It Proves |
|------|--------|---------------|
| 7 — Incident Response | `live_demo_localstack_incident.py` | Full chain: Lambda crash -> CloudWatch alarm -> SNS -> Bridge -> RAG diagnosis |
| 8 — ECS Multi-Service Cascade | `live_demo_ecs_multi_service.py` | Two-service cascade, correlated signals, severity override API |
| 19 — RAG Error Evaluation | `live_demo_rag_error_evaluation.py` | RAG retrieval accuracy and error classification |
| 20 — Unknown Incident Safety Net | `live_demo_20_unknown_incident_safety_net.py` | Novel incident detection when no runbook matches |
| 21 — Human Governance | `live_demo_21_human_governance_lifecycle.py` | Human-in-the-loop approval gates and kill switch |
| 22 — Change Event Causality | `live_demo_22_change_event_causality.py` | Deployment correlation with incident timeline |
| 24 — CloudWatch Bootstrap | `live_demo_24_cloudwatch_provider_bootstrap.py` | CloudWatch provider initialization and metric mapping |

### Tier 4: LLM Key Only (No LocalStack)

These need an LLM key but not LocalStack.

| Demo | Script | What It Proves |
|------|--------|---------------|
| 2 — Cascade Failure | `live_demo_cascade_failure.py` | Multi-service failure correlation and diagnosis |
| 3 — Deployment Regression | `live_demo_deployment_regression.py` | Regression detection from deployment events |
| 6 — HTTP Optimizations | `live_demo_http_optimizations.py` | Token optimization: novel incident skip, timeline filtering, semantic cache |
| 26 — Log Fetching | `live_demo_26_log_fetching_before_after.py` | Before/after log comparison across incidents |

## Recommended Demo Order

If you are new to the project, run these in order to see the system progressively:

```bash
# 1. See the AWS operators work (LocalStack only, fast)
SKIP_PAUSES=1 .venv/bin/python scripts/demo/live_demo_localstack_aws.py

# 2. See CloudWatch enrichment (LocalStack only, fast)
SKIP_PAUSES=1 .venv/bin/python scripts/demo/live_demo_cloudwatch_enrichment.py

# 3. See the full incident chain (LocalStack + LLM, ~2 min)
SKIP_PAUSES=1 .venv/bin/python scripts/demo/live_demo_ecs_multi_service.py

# 4. See token optimizations (LLM only, ~1 min)
SKIP_PAUSES=1 .venv/bin/python scripts/demo/live_demo_http_optimizations.py
```

## Stopping LocalStack

When you are done:

```bash
bash scripts/dev/setup_deps.sh stop
```

To also remove stored data:

```bash
bash scripts/dev/setup_deps.sh clean
```

## Troubleshooting

### "LOCALSTACK_AUTH_TOKEN is required"

Your `.env` file is missing or does not contain `LOCALSTACK_AUTH_TOKEN`. Fix your `.env` and retry.

### "LocalStack container is not running"

Run `bash scripts/dev/setup_deps.sh start` first.

### "edition is 'community'"

The token is invalid or expired. Get a new one from [app.localstack.cloud](https://app.localstack.cloud/workspace/auth-tokens), update `.env`, then:

```bash
bash scripts/dev/setup_deps.sh clean
bash scripts/dev/setup_deps.sh start
```

### "Service 'sns' is not enabled"

The LocalStack container was started with an older config. Recreate it:

```bash
bash scripts/dev/setup_deps.sh clean
bash scripts/dev/setup_deps.sh start
```

### Demo fails with "No LLM key found"

The demo requires `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` in `.env`. See the Tier 3/4 tables above.

### Lambda invocation timeout

Lambda execution needs Docker-in-Docker. Ensure Docker has at least 4 GB RAM allocated. The `LAMBDA_RUNTIME_ENVIRONMENT_TIMEOUT=120` tuning is already set by `setup_deps.sh`.
