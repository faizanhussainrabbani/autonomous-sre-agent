# Live Demo Suite — Comprehensive Critical Review

**Date:** 2026-03-18  
**Scope:** 11 `live_demo_*.py` scripts + [docs/operations/live_demo_guide.md](file:///Users/faizanhussain/Documents/Project/Practice/AiOps/docs/operations/live_demo_guide.md)

---

## Executive Summary

The live demo suite is **substantial and well-engineered**, covering a diverse range of capabilities across Phase 1 through Phase 2.3. However, significant documentation gaps, redundancy between closely-related demos, missing feature coverage, and inconsistent LocalStack configuration undermine its effectiveness as both a showcase tool and a regression test suite.

**Key Findings:**
- **5 of 11 demos are undocumented** in the landing page guide (Demos 2, 3, 4, 5, 6)
- **No demo covers Kubernetes operations**, multi-agent lock coordination, or Phase 3 remediation
- **Demos 5 and 7 overlap heavily** with insufficient differentiation
- **LocalStack usage is inconsistent** — region varies (`us-east-1` vs `eu-west-3`), and Community vs Pro requirements differ silently across demos
- **Demo numbering in filenames is inconsistent** — only Demos 1 and 11 have numbers in their filenames

---

## Demo Inventory & Coverage Matrix

| # | Script | Phase | LLM? | LocalStack? | Documented? |
|---|--------|-------|------|-------------|-------------|
| 1 | [live_demo_1_telemetry_baseline.py](file:///Users/faizanhussain/Documents/Project/Practice/AiOps/scripts/demo/live_demo_1_telemetry_baseline.py) | 1 | ❌ | Community | ✅ |
| 2 | [live_demo_cascade_failure.py](file:///Users/faizanhussain/Documents/Project/Practice/AiOps/scripts/demo/live_demo_cascade_failure.py) | 2 | ✅ | ❌ | ❌ |
| 3 | [live_demo_deployment_regression.py](file:///Users/faizanhussain/Documents/Project/Practice/AiOps/scripts/demo/live_demo_deployment_regression.py) | 2 | ✅ | ❌ | ❌ |
| 4 | [live_demo_localstack_aws.py](file:///Users/faizanhussain/Documents/Project/Practice/AiOps/scripts/demo/live_demo_localstack_aws.py) | 1.5 | ❌ | Pro | ❌ |
| 5 | [live_demo_http_server.py](file:///Users/faizanhussain/Documents/Project/Practice/AiOps/scripts/demo/live_demo_http_server.py) | 2 | ✅ | ❌ | ❌ |
| 6 | [live_demo_http_optimizations.py](file:///Users/faizanhussain/Documents/Project/Practice/AiOps/scripts/demo/live_demo_http_optimizations.py) | 2.2 | ✅ | ❌ | ❌ |
| 7 | [live_demo_localstack_incident.py](file:///Users/faizanhussain/Documents/Project/Practice/AiOps/scripts/demo/live_demo_localstack_incident.py) | 2 | ✅ | Pro | ✅ |
| 8 | [live_demo_ecs_multi_service.py](file:///Users/faizanhussain/Documents/Project/Practice/AiOps/scripts/demo/live_demo_ecs_multi_service.py) | 2 | ✅ | Pro | ✅ |
| 9 | [live_demo_cloudwatch_enrichment.py](file:///Users/faizanhussain/Documents/Project/Practice/AiOps/scripts/demo/live_demo_cloudwatch_enrichment.py) | 2.3 | ❌ | Community | ✅ |
| 10 | [live_demo_eventbridge_reaction.py](file:///Users/faizanhussain/Documents/Project/Practice/AiOps/scripts/demo/live_demo_eventbridge_reaction.py) | 2.3 | ❌ | ❌ | ✅ |
| 11 | [live_demo_11_azure_operations.py](file:///Users/faizanhussain/Documents/Project/Practice/AiOps/scripts/demo/live_demo_11_azure_operations.py) | 1.5 | ❌ | ❌ | ✅ |

### Feature Coverage Across Demos

| Feature | Demo(s) Covering It | Gap? |
|---------|---------------------|------|
| CloudWatch metrics fetch | 1, 9 | ✅ Covered |
| ECS operator (restart/scale) | 4, 8 | ✅ Covered |
| Lambda operator (create/invoke/scale) | 4, 7 | ✅ Covered |
| EC2 ASG operator (scale) | 4 | ✅ Covered |
| Azure App Service restart/scale | 11 | ✅ Covered |
| Azure Functions restart/scale | 11 | ✅ Covered |
| RAG pipeline (ingest + retrieve) | 2, 3, 5, 6, 7, 8 | ✅ Covered |
| LLM diagnosis (Anthropic/OpenAI) | 2, 3, 5, 6, 7, 8 | ✅ Covered |
| Severity classification | 2, 3, 7, 8 | ✅ Covered |
| Severity override API | 8 | ✅ Single demo only |
| Circuit breaker (CLOSED→OPEN→HALF_OPEN→CLOSED) | 3, 4 | ✅ Covered |
| EventBridge timeline | 10 | ✅ Covered |
| AlertEnricher enrichment | 9 | ✅ Covered |
| Multi-service cascade correlation | 2, 8 | ✅ Covered |
| Deployment-induced detection | 3 | ✅ Single demo only |
| Certificate expiry detection | 3 | ✅ Single demo only |
| Token optimization (novel short-circuit) | 6 | ✅ Single demo only |
| Semantic caching | 6 | ✅ Single demo only |
| **Kubernetes operations (kubectl)** | ❌ None | 🔴 **MISSING** |
| **Multi-agent lock protocol** | ❌ None | 🔴 **MISSING** |
| **Cooling-off / preemption protocol** | ❌ None | 🔴 **MISSING** |
| **Human Kill Switch** | ❌ None | 🔴 **MISSING** |
| **Phase 3 remediation execution** | ❌ None | 🔴 **MISSING** |
| **Disk exhaustion anomaly type** | ❌ None | 🟡 No demo |
| **Traffic anomaly detection** | ❌ None | 🟡 No demo |
| **X-Ray / distributed tracing** | ❌ None | 🟡 No demo |

---

## Per-Demo Findings

### Demo 1: Telemetry Baseline (108 lines)

**What it claims:** Phase 1 telemetry baseline — adapter-to-domain metric mapping.

| Criterion | Finding |
|-----------|---------|
| Feature Accuracy | ✅ Correctly demonstrates `CloudWatchMetricsAdapter` → `CanonicalMetric` conversion |
| Missing Gaps | Does not demonstrate other metric types (Lambda, ASG) — only ECS CPU |
| Correctness | ✅ Clean, focused, minimal |
| Redundancy | None — unique in its scope |
| LocalStack | Uses Community edition, region `us-east-1`. **Inconsistent with Demos 7/8 which use `eu-west-3`** |

> [!NOTE]
> Minor issue: References `AC 1.1-1.3` without linking to actual acceptance criteria.

---

### Demo 2: Cascade Failure (434 lines)

**What it claims:** Flash sale multi-service cascade (OOM → HTTP 503 → latency spike).

| Criterion | Finding |
|-----------|---------|
| Feature Accuracy | ✅ Demonstrates 3 independent diagnosis pipeline runs with realistic scenarios |
| Missing Gaps | Undocumented in guide; no LocalStack — purely synthetic alerts fed into domain pipeline |
| Correctness | ✅ Good event isolation verification (Phase 3). ✅ Prometheus counter check |
| Redundancy | **Overlaps significantly with Demo 8** for cascade detection. Demo 2 uses Kubernetes `ComputeMechanism`, Demo 8 uses ECS — but both prove multi-service cascades |
| LocalStack | ❌ Not used — runs entirely in-process |

> [!WARNING]
> This demo is **entirely undocumented** in [live_demo_guide.md](file:///Users/faizanhussain/Documents/Project/Practice/AiOps/docs/operations/live_demo_guide.md). It's an excellent showcase of event isolation and Prometheus observability but invisible to new users.

---

### Demo 3: Deployment Regression (562 lines)

**What it claims:** Deployment-induced failure + circuit breaker + certificate expiry advisory.

| Criterion | Finding |
|-----------|---------|
| Feature Accuracy | ✅ Correctly exercises `DEPLOYMENT_INDUCED` anomaly type with deployment metadata |
| Missing Gaps | Undocumented; does not exercise deployment rollback API (only diagnosis) |
| Correctness | ✅ Circuit breaker state machine demo is thorough with Prometheus gauge tracking |
| Redundancy | **Circuit breaker demo duplicates Demo 4's Act 4** — nearly identical logic |
| LocalStack | ❌ Not used |

> [!IMPORTANT]
> The certificate expiry scenario (Act 3) is the **only demo** that exercises `AnomalyType.CERTIFICATE_EXPIRY`. If this demo is removed, that coverage is lost entirely.

---

### Demo 4: AWS LocalStack Operators (586 lines)

**What it claims:** AWS remediation operators (ECS, Lambda, EC2 ASG) against LocalStack.

| Criterion | Finding |
|-----------|---------|
| Feature Accuracy | ✅ Excellent demonstration of real boto3 API calls through the operator abstraction layer |
| Missing Gaps | Undocumented; header says "Demo 4" but guide jumps from Demo 1 to Demo 7 |
| Correctness | ✅ Thorough — creates real resources, exercises operator methods, verifies state transitions |
| Redundancy | Act 4 (circuit breaker) duplicates Demo 3's Act 2 |
| LocalStack | **Requires Pro** for ECS + ASG. Region: `us-east-1`. Good edition detection + fallback messaging |

> [!WARNING]
> The docstring says "Live Demo 4" but it's stored as [live_demo_localstack_aws.py](file:///Users/faizanhussain/Documents/Project/Practice/AiOps/scripts/demo/live_demo_localstack_aws.py). The naming convention mismatch with [live_demo_1_telemetry_baseline.py](file:///Users/faizanhussain/Documents/Project/Practice/AiOps/scripts/demo/live_demo_1_telemetry_baseline.py) and [live_demo_11_azure_operations.py](file:///Users/faizanhussain/Documents/Project/Practice/AiOps/scripts/demo/live_demo_11_azure_operations.py) is confusing.

---

### Demo 5: HTTP Server (156 lines)

**What it claims:** End-to-end HTTP demo verifying the REST API layer.

| Criterion | Finding |
|-----------|---------|
| Feature Accuracy | ✅ Boots FastAPI app, sends diagnosis request over HTTP |
| Missing Gaps | Very thin — single alert, no knowledge seeding, minimal verification |
| Correctness | ⚠️ Sends `billing-api` alert with no runbooks ingested — will always return a novel/fallback diagnosis |
| Redundancy | **Nearly entirely subsumed by Demo 6** which does everything Demo 5 does plus KB seeding, token optimizations, and caching |
| LocalStack | ❌ Not used |

> [!CAUTION]
> Demo 5 is a **strict subset** of Demo 6. Keeping both adds maintenance burden without educational value. Demo 5 should be removed or consolidated into Demo 6.

---

### Demo 6: HTTP Token Optimizations (305 lines)

**What it claims:** Phase 2.2 token optimizations over live HTTP.

| Criterion | Finding |
|-----------|---------|
| Feature Accuracy | ✅ Validates 4 optimizations: novel incident short-circuit, timeline filtering, lightweight validation, semantic caching |
| Missing Gaps | Undocumented in guide despite being the **only demo** for Phase 2.2 |
| Correctness | ⚠️ Act 3 ([act3_lightweight_validation](file:///Users/faizanhussain/Documents/Project/Practice/AiOps/scripts/demo/live_demo_http_optimizations.py#218-234)) parses the audit trail as strings with `split(":")` — breaks if audit trail format changes to structured dicts (which Demo 7/8 already handle) |
| Redundancy | None — unique Phase 2.2 coverage |
| LocalStack | ❌ Not used |

> [!WARNING]
> The audit trail parsing in Act 3 (line 226) assumes string format but the codebase's audit trail has evolved to return structured dicts (as seen in Demos 7 and 8). This likely fails silently by producing empty output.

---

### Demo 7: Lambda Incident (931 lines)

**What it claims:** Full end-to-end Lambda incident response with LocalStack.

| Criterion | Finding |
|-----------|---------|
| Feature Accuracy | ✅ Comprehensive — real Lambda deployment, CloudWatch → SNS → Bridge → Agent chain |
| Missing Gaps | None — this is the most complete full-stack demo |
| Correctness | ✅ Well-structured with excellent error handling, auto-start for LocalStack, sigint cleanup |
| Redundancy | Some overlap with Demo 8 in infra setup/bridge/agent startup boilerplate (duplicated ~300 lines of identical helper functions) |
| LocalStack | Uses `eu-west-3` region. **Uses `host.docker.internal`** for bridge endpoint (macOS Docker-specific). SNS subscription uses the hardcoded `host.docker.internal` even though `BRIDGE_HOST` env var exists in Demo 8 but not here |

> [!IMPORTANT]
> Demo 7 hardcodes `host.docker.internal` on line 518 whereas Demo 8 correctly uses a configurable `BRIDGE_HOST` env var. This inconsistency means Demo 7 will fail on Linux (where LocalStack runs natively, not in Docker Desktop).

---

### Demo 8: ECS Multi-Service (1295 lines)

**What it claims:** ECS cascade + correlated signals + severity override API.

| Criterion | Finding |
|-----------|---------|
| Feature Accuracy | ✅ Excellent — dual alarm chains, enriched correlated signals, severity override POST + GET |
| Missing Gaps | None — this is the richest demo |
| Correctness | ✅ Proper cleanup, sigint handler, Phase 12/13 severity override well-structured |
| Redundancy | Significant boilerplate duplication with Demo 7 (color helpers, LocalStack health, port kill, agent/bridge startup) |
| LocalStack | Uses configurable `BRIDGE_HOST`. Uses `eu-west-3`. Sets `desiredCount=0` for ECS services to avoid LocalStack Fargate scheduling GC — **well-documented workaround** |

---

### Demo 9: CloudWatch Enrichment (195 lines)

**What it claims:** AlertEnricher execution against LocalStack.

| Criterion | Finding |
|-----------|---------|
| Feature Accuracy | ✅ Correctly pushes synthetic metrics + logs to LocalStack and runs the enricher |
| Missing Gaps | Docstring says "Phase 2.3" but the AlertEnricher could also be Phase 1.5 |
| Correctness | ⚠️ Uses interactive `input()` prompts — **no `SKIP_PAUSES` support**. Cannot be used in CI/CD mode |
| Redundancy | None — unique coverage |
| LocalStack | Community edition. Region: `us-east-1`. **Inconsistent with Demos 7/8** |

---

### Demo 10: EventBridge Timelines (216 lines)

**What it claims:** EventBridge event ingestion → canonical timeline construction.

| Criterion | Finding |
|-----------|---------|
| Feature Accuracy | ✅ Exercises `/api/v1/events/aws` endpoint and `TimelineConstructor.build()` |
| Missing Gaps | Does **not** actually connect to LocalStack EventBridge — uses `FastAPI TestClient` to POST synthetic events |
| Correctness | ⚠️ Uses interactive `input()` prompts — **no `SKIP_PAUSES` support** |
| Redundancy | None — unique coverage |
| LocalStack | ❌ Not used despite the guide saying it could leverage EventBridge native support |

> [!NOTE]
> The guide doc describes Demo 10 as demonstrating "Cloud Provider events" but the demo only uses `FastAPI TestClient`—no actual EventBridge or LocalStack integration. This is acceptable since EventBridge webhooks don't require a live AWS service, but the guide should clarify this.

---

### Demo 11: Azure Operations (117 lines)

**What it claims:** Phase 1.5 multi-cloud Azure operator abstractions.

| Criterion | Finding |
|-----------|---------|
| Feature Accuracy | ✅ Correctly validates `AppServiceOperator` and `FunctionsOperator` through `CloudOperatorPort` |
| Missing Gaps | Only tests `restart` and `scale` — does not test error paths, circuit breaker on Azure operators |
| Correctness | ⚠️ Line 59-62: `restart` is called with `RESOURCE_ID_APP` as the full Azure resource URI, but then `assert_called_with(NAMESPACE, RESOURCE_ID_APP)` — this passes the full URI as the `name` parameter, which is incorrect for the real Azure SDK where `name` should be just the app name |
| Redundancy | None — unique Azure coverage |
| LocalStack | ❌ Not applicable — uses unittest mocks |

> [!WARNING]
> The mock assertions may not match the real Azure SDK call signatures. The `restart` method is asserted as `restart(resource_group, resource_id)` but the real `WebAppsOperations.restart()` takes [(resource_group_name, name)](file:///Users/faizanhussain/Documents/Project/Practice/AiOps/scripts/demo/live_demo_cascade_failure.py#46-56) where `name` is the app name, not the full resource URI.

---

## Documentation Assessment: [live_demo_guide.md](file:///Users/faizanhussain/Documents/Project/Practice/AiOps/docs/operations/live_demo_guide.md)

### Issues Found

1. **5 demos completely undocumented:** Demos 2 (cascade), 3 (deployment), 4 (LocalStack AWS operators), 5 (HTTP server), 6 (HTTP optimizations) are absent from the guide.

2. **"Two fully-scripted demonstrations" claim is wrong** (line 23): The overview says "Two fully-scripted demonstrations" but actually describes 6 demos in the table. This appears to be leftover copy from when only Demos 7 and 8 existed.

3. **"Both demos include" checklist is stale** (lines 34-39): The features listed apply to Demos 7/8 but not to Demos 1, 9, 10, or 11.

4. **Missing "Next Steps" placement** (line 289-298): The "Next Steps" and "Integrate into CI/CD" sections are awkwardly placed between Demo 8 and Demo 9 — they should be at the bottom.

5. **Inconsistent Demo ordering**: Demos 9, 10, 11 are documented after the troubleshooting section, creating a disjointed reading experience.

6. **Prerequisites section claims Pro is required for both demos** (line 160) but Demo 1 and Demo 9 can run on Community edition.

7. **Hardcoded path** on line 86-87: `cd /Users/faizanhussain/Documents/Project/Practice/AiOps` — machine-specific path should not be in docs.

---

## Prioritized Recommendations

### 🔴 HIGH Priority

| # | Recommendation | Rationale |
|---|----------------|-----------|
| H1 | **Document Demos 2, 3, 4, 6 in [live_demo_guide.md](file:///Users/faizanhussain/Documents/Project/Practice/AiOps/docs/operations/live_demo_guide.md)** | 5 demos are invisible to users. Demos 4 and 6 are particularly important (only operator demo, only token optimization demo) |
| H2 | **Fix the "Two fully-scripted demonstrations" stale copy** (line 23) | Actively misleading — the guide now covers 6 demos and should say so |
| H3 | **Standardize LocalStack region** across all demos | Demos 1, 4, 9 use `us-east-1`; Demos 7, 8 use `eu-west-3`. Pick one and make it configurable via `AWS_DEFAULT_REGION` everywhere |
| H4 | **Fix Demo 7's hardcoded `host.docker.internal`** | Demo 7 (line 518) hardcodes it whereas Demo 8 correctly uses `BRIDGE_HOST` env var. Demo 7 will fail on Linux native LocalStack |
| H5 | **Add `SKIP_PAUSES` support to Demos 9 and 10** | These use raw `input()` calls, making them unusable in CI/CD pipelines despite the guide suggesting CI integration |
| H6 | **Add a Kubernetes operations demo** | The `AGENTS.md` states K8s pods/deployments/statefulsets as the primary operating scope, yet no demo exercises `kubectl` operations. This is the largest feature gap |
| H7 | **Remove machine-specific path** on line 86-87 of the guide | `cd /Users/faizanhussain/...` should be `cd <project-root>` or removed |

### 🟡 MEDIUM Priority

| # | Recommendation | Rationale |
|---|----------------|-----------|
| M1 | **Consolidate Demo 5 into Demo 6** | Demo 5 is a strict functional subset of Demo 6. Remove or merge to reduce maintenance burden |
| M2 | **Extract shared helpers** (color class, LocalStack health, port-kill) from Demos 7/8 into a shared `_demo_utils.py` | ~300 lines of duplicated boilerplate |
| M3 | **Add multi-agent lock protocol demo** | `AGENTS.md` defines detailed lock schemas, preemption protocol, and cooling-off implementation. No demo validates this critical coordination layer |
| M4 | **Fix Demo 6 Act 3 audit trail parsing** | Line 226 uses `a.split(":")` on audit trail entries, but the audit trail now returns structured dicts. This will silently produce incorrect output |
| M5 | **Standardize demo file naming** | Only `live_demo_1_*.py` and `live_demo_11_*.py` have numbers. Name all demos consistently: `live_demo_02_cascade_failure.py`, etc. |
| M6 | **Fix Prerequisites section** in guide | "Both demos require LocalStack Pro" is inaccurate — Demo 1 and Demo 9 only need Community |
| M7 | **Restructure guide document** | Move Demos 9/10/11 up with the other demos; move "Next Steps" and "CI/CD" to the bottom |
| M8 | **Validate Demo 11 Azure mock assertions** against actual `azure-mgmt-web` SDK call signatures | The `restart()` assertion passes the full resource URI as `name`, which doesn't match the real SDK |

### 🟢 LOW Priority

| # | Recommendation | Rationale |
|---|----------------|-----------|
| L1 | **Deduplicate circuit breaker demos** | Demo 3 Act 2 and Demo 4 Act 4 demonstrate nearly identical circuit breaker state machines. Consolidate into one canonical demo |
| L2 | **Add a disk exhaustion demo** | `AnomalyType.DISK_EXHAUSTION` exists in the codebase but no demo exercises it |
| L3 | **Add a traffic anomaly demo** | `AnomalyType.TRAFFIC_ANOMALY` exists but is not demonstrated |
| L4 | **Add Demo 10 actual EventBridge integration** | Currently uses `TestClient` only. Could leverage LocalStack's EventBridge support for a real simulation |
| L5 | **Add X-Ray/tracing demo** | CHANGELOG mentions X-Ray Service Map as planned for Phase 2.4. A demo placeholder would be valuable |
| L6 | **Document LocalStack Community vs Pro requirements per-demo** in the guide | Currently, users can't tell which demos require Pro without reading the script |
| L7 | **Explore LocalStack Cloud Pods** for demo state snapshots | Could pre-seed resources and reduce demo setup time |

---

## LocalStack Utilization Assessment

### Current Usage

| Demo | Edition | Services Used | Quirks Handled? |
|------|---------|---------------|-----------------|
| 1 | Community | `cloudwatch` | ✅ `time.sleep(1)` for metric indexing |
| 4 | Pro | `ecs, lambda, autoscaling, ec2` | ✅ Edition detection, synthetic task ARN fallback |
| 7 | Pro | `lambda, cloudwatch, sns, logs` | ✅ `LAMBDA_SYNCHRONOUS_CREATE=1`, waiter config, auto-start |
| 8 | Pro | `ecs, ec2, cloudwatch, sns` | ✅ `desiredCount=0` to prevent Fargate GC, `set_alarm_state` to skip evaluation window |
| 9 | Community | `cloudwatch, logs` | ✅ `time.sleep(2)` for consistency |

### Improvement Opportunities

1. **Cloud Pods:** No demo uses Cloud Pods for state management. Pre-seeding ECS/Lambda resources as a Cloud Pod snapshot would reduce Demos 7/8 setup from ~3 minutes to ~30 seconds.

2. **Ephemeral Instances:** No demo uses testcontainers for ephemeral isolated containers. The integration tests use this pattern (per [localstack_pro_guide.md](file:///Users/faizanhussain/Documents/Project/Practice/AiOps/docs/testing/localstack_pro_guide.md)), but demos could benefit from it for CI isolation.

3. **Alarm manual triggering quirk:** Demos 7/8 correctly use `set_alarm_state()` to skip the CloudWatch evaluation window — this is well-handled.

4. **SNS subscription confirmation:** Demo 7 line 530-537 handles the pending/auto-confirmed distinction well, but only Demo 8 documents `BRIDGE_HOST` for Docker vs native LocalStack — Demo 7 is missing this.

5. **Region inconsistency** is the biggest configuration problem. `us-east-1` vs `eu-west-3` across demos could confuse users running multiple demos in sequence against the same LocalStack instance.

6. **`LOCALSTACK_LAMBDA_SYNCHRONOUS_CREATE=1`:** Demo 7 correctly sets `LAMBDA_SYNCHRONOUS_CREATE=1` during auto-start. Demo 4 does not set this — it may encounter race conditions if the Lambda function isn't ready before invocation.

---

## Conclusion

The demo suite is a significant asset — particularly Demos 7 and 8 which provide genuinely impressive end-to-end LocalStack integration. However, the **documentation gap** (5 undocumented demos) and **missing feature areas** (Kubernetes ops, multi-agent coordination) are the most critical issues to address. Consolidating Demo 5 into Demo 6 and extracting shared utilities would immediately improve maintainability.
