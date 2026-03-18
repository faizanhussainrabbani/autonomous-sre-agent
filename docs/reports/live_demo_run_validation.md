---
title: Live Demo Run and Validation Report
description: Step 6 run-time validation evidence for the live demo findings implementation.
author: SRE Agent Engineering Team
ms.date: 2026-03-18
ms.topic: reference
keywords:
  - runtime validation
  - smoke test
  - live demos
estimated_reading_time: 6
---

## Execution summary

The implementation was executed and validated using targeted unit tests and runtime smoke flows for impacted demos.

## Commands and outcomes

| Command | Result | Notes |
|---|---|---|
| `.venv/bin/python -m pytest -q tests/unit/adapters/test_azure_operators.py` | ✅ Pass | 6 passed; includes new ARM resource ID name extraction tests |
| `SKIP_PAUSES=1 .venv/bin/python /Users/faizanhussain/Documents/Project/Practice/AiOps/scripts/demo/live_demo_eventbridge_reaction.py` | ✅ Pass | Non-interactive flow works; TestClient-based event ingestion and timeline output verified |
| `SKIP_PAUSES=1 .venv/bin/python /Users/faizanhussain/Documents/Project/Practice/AiOps/scripts/demo/live_demo_cloudwatch_enrichment.py` | ✅ Pass | Non-interactive flow works end-to-end with enrichment output |
| `SKIP_PAUSES=1 .venv/bin/python /Users/faizanhussain/Documents/Project/Practice/AiOps/scripts/demo/live_demo_11_azure_operations.py` | ✅ Pass | Restart/scale semantics align with app/function name behavior |
| `SKIP_PAUSES=1 .venv/bin/python /Users/faizanhussain/Documents/Project/Practice/AiOps/scripts/demo/live_demo_kubernetes_operations.py` | ✅ Pass | Simulation mode executes full command sequence without runtime errors |
| `SKIP_PAUSES=1 .venv/bin/python /Users/faizanhussain/Documents/Project/Practice/AiOps/scripts/demo/live_demo_multi_agent_lock_protocol.py` | ✅ Pass | Demonstrates grant, preemption, cooldown denial, and human override denial |
| `.venv/bin/python /Users/faizanhussain/Documents/Project/Practice/AiOps/scripts/demo/live_demo_14_disk_exhaustion.py` | ✅ Pass | Disk exhaustion simulation payload produced successfully |
| `.venv/bin/python /Users/faizanhussain/Documents/Project/Practice/AiOps/scripts/demo/live_demo_15_traffic_anomaly.py` | ✅ Pass | Traffic anomaly simulation payload produced successfully |
| `.venv/bin/python /Users/faizanhussain/Documents/Project/Practice/AiOps/scripts/demo/live_demo_16_xray_tracing_placeholder.py` | ✅ Pass | Trace demo placeholder executes cleanly |
| `SKIP_PAUSES=1 .venv/bin/python /Users/faizanhussain/Documents/Project/Practice/AiOps/scripts/demo/live_demo_09_cloudwatch_enrichment.py` | ✅ Pass | Numbered alias wrapper executes and delegates correctly |

## Primary flow checks

* No runtime errors observed in validated command set
* Non-interactive (`SKIP_PAUSES=1`) behavior confirmed for updated demos
* New demos execute successfully in default-safe mode
* Azure operator semantics validated by both runtime demo and unit tests

## Edge-case checks

* Demo 10 explicitly runs without live EventBridge dependency (FastAPI TestClient simulation)
* Demo 12 defaults to safe simulation mode when `RUN_KUBECTL` is not enabled
* Demo 7 bridge callback host is now environment-controlled through `BRIDGE_HOST`
