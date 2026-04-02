# Demo Suite — Critical Evaluation Report

**Date:** 2026-03-31 (updated post-remediation)
**Scope:** 18 active `live_demo_*.py` scripts across `scripts/demo/` (5 retired)
**Analyst:** SRE Agent Engineering
**Status:** FINAL — Five critical findings resolved
**Supersedes:** Partial findings in `live_demo_review_report.md` (2026-03-18) and `live_demo_analysis_report.md` (DRAFT)

---

## Executive Summary

The live demo suite has grown from 11 scripts at the time of the last formal review (2026-03-18) to **18 canonical scripts** — a deliberate expansion driven by the Phase 2.3 governance slice followed by a consolidation pass that retired 5 low-value scripts. The suite now covers Phase 1 through Phase 2.3 with meaningful depth. All five critical findings identified in the initial evaluation have been **resolved** through the Five Critical Findings Remediation Slice (2026-03-31).

**Health Verdict: GREEN** — The suite is substantial, consolidated, and all flagship demos (7, 8, 19–23) represent genuine showcase quality. The remediation slice eliminated false-confidence stubs, resolved correctness defects, and reduced maintenance surface by retiring overlapping scripts.

### Five Critical Findings — Resolution Status

| # | Finding | Severity | Status | Resolution |
|---|---------|----------|--------|------------|
| F1 | Demo 5 is a strict functional subset of Demo 6 and adds no unique coverage | HIGH | **RESOLVED** | `live_demo_http_server.py` deleted; guide references removed. Demo 6 is canonical HTTP-layer path. |
| F2 | Demo 7 hardcodes `host.docker.internal` — fails on Linux LocalStack native | HIGH | **RESOLVED** | Demo 7 now uses `BRIDGE_HOST` env var (default `127.0.0.1`); guide instructs Docker users to set `BRIDGE_HOST=host.docker.internal`. |
| F3 | Demo 6 Act 3 audit trail parsing uses `str.split(":")` but the audit trail returns structured dicts — produces silent incorrect output | HIGH | **RESOLVED** | `act3_lightweight_validation()` now handles both dict and string entries via `_extract_stage_and_action()`, raises `RuntimeError` on empty or missing expected actions. Edge cases validated: empty audit trail, mixed-format entries. |
| F4 | Demos 14, 15, 16 are non-executable stubs — generate no meaningful signal and create false confidence in anomaly-type coverage | MEDIUM | **RESOLVED** | All three files deleted; guide references removed. Disk exhaustion, traffic anomaly, and X-Ray tracing documented as explicit coverage gaps. |
| F5 | Demos 17 and 23 demonstrate nearly identical guardrail denial → execution flows; Demo 13 and Demo 17 both exercise in-memory lock coordination — three-way overlap across action-lock demos | MEDIUM | **RESOLVED** | Demo 17 deleted. Demo 13 (protocol narrative) and Demo 23 (real LocalStack guardrail proof) retained as complementary. |

**Remediation artifacts:** Implementation plan, compliance check, acceptance criteria (9/9 pass), verification report, and run validation — all at `docs/reports/*/live_demo_five_critical_findings_*.md`. CHANGELOG entry with full traceability at `[2026-03-31] Live Demo Five Critical Findings Remediation Slice`.

### Coverage Snapshot

| Area | Status |
|------|--------|
| Phase 1 telemetry (CW adapter → CanonicalMetric) | ✅ Covered (Demo 1) |
| Phase 1.5 AWS operators (ECS, Lambda, ASG) | ✅ Covered (Demo 4) |
| Phase 1.5 Azure operators | ⚠️ Mock-only (Demo 11) |
| Phase 1.5 Kubernetes operators | ⚠️ Simulation-only (Demo 12) |
| Phase 2 RAG + LLM diagnosis | ✅ Deep coverage (Demos 2, 3, 6, 7, 8, 19) |
| Phase 2.1 Observability / AlertEnricher | ✅ Covered (Demo 9) |
| Phase 2.2 Token optimizations | ✅ Covered (Demo 6, Act 3 hardened) |
| Phase 2.3 EventBridge timelines | ⚠️ TestClient only, no real LS (Demo 10) |
| Phase 2.3 Multi-agent lock coordination | ⚠️ In-memory simulation (Demo 13) |
| Phase 2.3 Safety guardrails + blast radius | ✅ Covered (Demo 23) |
| Phase 2.3 Governance (severity override) | ✅ Covered (Demo 21) |
| Phase 2.3 Change event causality | ✅ Covered (Demo 22) |
| Phase 2.3 Unknown incident safety net | ✅ Covered (Demo 20) |
| Phase 3 Remediation saga / rollback | ❌ Not covered |
| Phase 3 etcd distributed lock (real) | ✅ Covered (Demo 18) |
| X-Ray / distributed tracing | ❌ Not covered (placeholder retired) |
| Disk exhaustion anomaly type | ❌ Not covered (stub retired) |
| Traffic anomaly type | ❌ Not covered (stub retired) |
| Kafka / alternative event bus | ❌ Not covered |

---

## Demo Inventory Table

| Demo | Script | Phase | LocalStack | Edition | LLM | Lines | Guide Doc? |
|------|--------|-------|-----------|---------|-----|-------|-----------|
| 1 | `live_demo_1_telemetry_baseline.py` | 1 | ✅ Community | Community | ❌ | 103 | ✅ |
| 2 | `live_demo_cascade_failure.py` | 2 | ❌ | — | ✅ | 434 | ✅ (updated) |
| 3 | `live_demo_deployment_regression.py` | 2 | ❌ | — | ✅ | 562 | ✅ (updated) |
| 4 | `live_demo_localstack_aws.py` | 1.5 | ✅ Pro | Pro | ❌ | 586 | ✅ (updated) |
| ~~5~~ | ~~`live_demo_http_server.py`~~ | — | — | — | — | — | **Retired (F1)** |
| 6 | `live_demo_http_optimizations.py` | 2.2 | ❌ | — | ✅ | 305 | ✅ (Act 3 hardened) |
| 7 | `live_demo_localstack_incident.py` | 2 | ✅ Pro | Pro | ✅ | 931 | ✅ |
| 8 | `live_demo_ecs_multi_service.py` | 2 | ✅ Pro | Pro | ✅ | 1295 | ✅ |
| 9 | `live_demo_cloudwatch_enrichment.py` | 2.1 | ✅ Community | Community | ❌ | 195 | ✅ |
| 10 | `live_demo_eventbridge_reaction.py` | 2.3 | ❌ | — | ❌ | 216 | ✅ |
| 11 | `live_demo_11_azure_operations.py` | 1.5 | ❌ | — | ❌ | 124 | ✅ |
| 12 | `live_demo_kubernetes_operations.py` | 1.5/3 | ❌ | — | ❌ | 101 | ✅ |
| 13 | `live_demo_multi_agent_lock_protocol.py` | 2.3 | ❌ | — | ❌ | 136 | ✅ |
| ~~14~~ | ~~`live_demo_14_disk_exhaustion.py`~~ | — | — | — | — | — | **Retired (F4)** |
| ~~15~~ | ~~`live_demo_15_traffic_anomaly.py`~~ | — | — | — | — | — | **Retired (F4)** |
| ~~16~~ | ~~`live_demo_16_xray_tracing_placeholder.py`~~ | — | — | — | — | — | **Retired (F4)** |
| ~~17~~ | ~~`live_demo_17_action_lock_orchestration.py`~~ | — | — | — | — | — | **Retired (F5)** |
| 18 | `live_demo_18_etcd_action_lock_flow.py` | 2.3 | Docker/etcd | External | ❌ | 193 | ✅ |
| 19 | `live_demo_rag_error_evaluation.py` | 2+ | ✅ Community | Community | ✅ | ~700 | ✅ |
| 20 | `live_demo_20_unknown_incident_safety_net.py` | 2.3 | ✅ Community | Community | ✅ | 479 | ✅ |
| 21 | `live_demo_21_human_governance_lifecycle.py` | 2.3 | ✅ Community | Community | ✅ | 456 | ✅ |
| 22 | `live_demo_22_change_event_causality.py` | 2.3 | ✅ Community | Community | ✅ | 431 | ✅ |
| 23 | `live_demo_23_ai_says_no_before_it_acts.py` | 2.3 | ✅ Community | Community | ❌ | 271 | ✅ |

**Totals:** 18 active demos (5 retired) · 12 use LocalStack (9 Community, 4 Pro, 1 Docker/etcd) · 9 require LLM API key
**Documentation gap from prior review (5 undocumented demos) has been fully resolved as of 2026-03-31.**
**Five critical findings remediation completed 2026-03-31. See artifacts at `docs/reports/*/live_demo_five_critical_findings_*.md`.**

---

## Per-Demo Analysis

---

### Demo 1 — Telemetry Baseline

**Stated purpose:** Phase 1 adapter-to-domain metric mapping. Provisions 5 CloudWatch metric datums via LocalStack, fetches them through `CloudWatchMetricsAdapter`, and asserts conversion to `CanonicalMetric` structs.

**Phase alignment:** Phase 1 ✅

**Feature coverage assessment:**
- Correctly exercises `CloudWatchMetricsAdapter` → `CanonicalMetric` conversion with real boto3 calls against LocalStack.
- Covers only `CpuUtilized` for ECS. Lambda metrics, ASG metrics, and other `CanonicalMetric` variants are absent.
- References acceptance criteria `AC 1.1-1.3` with no link to source — cosmetic but creates documentation debt.

**Correctness evaluation:**
- Clean, well-scoped, idiomatic async code.
- `time.sleep(1)` is appropriate for LocalStack metric indexing lag.
- Region hardcoded to `us-east-1`. **Inconsistent with Demos 7/8 which use `eu-west-3`.** Running both in sequence against the same LocalStack instance creates confusing namespace separation. No `AWS_DEFAULT_REGION` env override.
- No cleanup of pushed metrics (minor — LocalStack resets on restart).

**Redundancy analysis:** None. Unique coverage of the Phase 1 adapter layer.

**Significance:** **HIGH** — The only executable proof that the CloudWatch adapter produces valid domain objects. Loss of this demo would remove all Phase 1 telemetry regression coverage.

---

### Demo 2 — Flash Sale Cascade Failure

**Stated purpose:** Three-service Black Friday OOM → HTTP 503 → latency spike cascade. Validates multi-incident isolation, cross-service event store integrity, and cascade reasoning via LLM.

**Phase alignment:** Phase 2 ✅

**Feature coverage assessment:**
- Exercises the full RAG diagnosis pipeline three times against independent event buses and event stores.
- Prometheus counter assertions validate observability instrumentation.
- Uses Kubernetes `ComputeMechanism` — the only demo that does so in a diagnosis context.
- Does **not** provision real infrastructure. All alerts are synthetic in-process — no LocalStack. This is acceptable for a diagnosis pipeline test, but means no adapter-layer coverage.

**Correctness evaluation:**
- Architecturally sound. Event isolation verified post-run with `get_events()` assertions.
- **Known live-run finding (2026-03-09):** Blast radius is always passed as `0.0` to `SeverityClassifier`, causing Tier-1/Tier-2 services to receive `SEV3` despite flash sale scale. Fix proposed in `live_demo_evaluation.md §7.5` — **not yet applied**.
- **Known live-run finding:** `SEVERITY_ASSIGNED` Prometheus metric always tags `service_tier=unknown` because `AnomalyAlert` has no `service_tier` field. Fix proposed — **not yet applied**.

**Redundancy analysis:** Overlaps with Demo 8 for multi-service cascade narrative, but Demo 2 is the only demo exercising Kubernetes `ComputeMechanism` in a diagnosis context and the only demo validating event store isolation across concurrent incidents.

**Significance:** **HIGH** — Only demo for event isolation verification and Kubernetes compute path in Phase 2. Two known unfixed bugs degrade its value as a correctness gate.

---

### Demo 3 — Deployment Regression and Infrastructure Fragility

**Stated purpose:** Three-act demo: (1) deployment-induced error rate surge with LLM second-opinion disagreement, (2) circuit breaker full state-machine cycle, (3) TLS certificate expiry advisory.

**Phase alignment:** Phase 2 ✅

**Feature coverage assessment:**
- Act 1 is the **only demo** exercising `DEPLOYMENT_INDUCED` anomaly type with deployment metadata.
- Act 3 is the **only demo** exercising `AnomalyType.CERTIFICATE_EXPIRY`. If this demo is removed, that coverage vanishes entirely.
- Validates the confidence score disagreement penalty in live conditions (LLM validator disagreement → −7.5 pp reduction confirmed in run).
- `severity_deployment_elevation` (SEV3 → SEV2 override for TIER_2 + deployment) confirmed working.

**Correctness evaluation:**
- Circuit breaker demo (Act 2) duplicates Act 4 of Demo 4 with near-identical Prometheus gauge assertions. Not a bug but creates maintenance surface.
- **Known live-run finding (2026-03-09):** Certificate expiry severity does not scale by `hours_remaining`. A cert expiring in 5.8 h and one expiring in 5 days receive identical treatment. Fix proposed in `live_demo_evaluation.md §8.6` — **not yet applied**.
- **Known live-run finding:** `circuit-breaker-fragility.md` appears as evidence citation for a certificate expiry alert — evidence ranking noise, anomaly-type metadata filtering not implemented.
- Approval guard: Tier 1 + SEV3 + AUTONOMOUS confidence bypasses the human approval requirement (design gap documented in `live_demo_evaluation.md §8.6`). This is a correctness risk, not just a demo issue.

**Redundancy analysis:** Circuit breaker overlaps with Demo 4 Act 4. Certificate expiry (Act 3) is unique.

**Significance:** **HIGH** — Sole carrier of `CERTIFICATE_EXPIRY` and `DEPLOYMENT_INDUCED` coverage. Three known bugs diminish its value as a correctness gate.

---

### Demo 4 — AWS LocalStack Cloud Operators

**Stated purpose:** Phase 1.5 cloud operator layer (ECS restart/scale, Lambda create/invoke/scale, EC2 ASG scale) via real boto3 calls against LocalStack Pro.

**Phase alignment:** Phase 1.5 ✅

**Feature coverage assessment:**
- Exercises real AWS API calls: creates Lambda function, deploys ECS service, scales ASG — verifying end-to-end operator contract with live cloud state transitions.
- Act 4 (circuit breaker) is partially duplicated in Demo 3 but includes different operator context.
- Only demo that exercises `EC2 AutoScaling` operator.

**Correctness evaluation:**
- Requires LocalStack Pro for ECS and ASG. Community edition detection and fallback messaging is handled — good defensive pattern.
- Does **not** set `LAMBDA_SYNCHRONOUS_CREATE=1` during auto-start, unlike Demo 7. May cause intermittent failures if Lambda function creation is async and invocation races.
- Region: `us-east-1`. Inconsistent with Demos 7/8 (`eu-west-3`).
- Docstring names it "Demo 4" but filename is `live_demo_localstack_aws.py`. This naming mismatch persists from the prior review.

**Redundancy analysis:** Act 4 (circuit breaker) overlaps Demo 3 Act 2. Otherwise uniquely covers EC2 ASG, Lambda creation/invocation lifecycle, and ECS operator.

**Significance:** **CRITICAL** — The only end-to-end proof that cloud operators issue real boto3 calls and transition real cloud state. Loss of this demo eliminates all Phase 1.5 AWS operator regression coverage.

---

### Demo 5 — HTTP Server End-to-End (RETIRED)

> **Status: RETIRED** — Deleted as part of the Five Critical Findings Remediation Slice (F1). Demo 6 is the canonical HTTP-layer validation path.

**Original purpose:** Boot FastAPI server, POST single alert, receive diagnosis over HTTP. Was a strict functional subset of Demo 6 with no unique coverage. Retired to reduce maintenance surface.

---

### Demo 6 — HTTP Token Optimizations

**Stated purpose:** Phase 2.2 token optimizations over live HTTP — four acts: novel short-circuit, timeline filtering, lightweight validation, semantic caching.

**Phase alignment:** Phase 2.2 ✅

**Feature coverage assessment:**
- Only demo validating novel incident short-circuit, cross-encoder reranking, evidence compression (TLDRify), and semantic caching.
- Mathematically proves Phase 2.2 value by comparing token counts before and after optimization.

**Correctness evaluation:**
- **Act 3 audit trail parsing has been fixed (F3).** The `act3_lightweight_validation()` function now uses `_extract_stage_and_action()` which handles both dict entries (via `stage`/`step`/`type`/`event` keys) and legacy string entries (via `split(":", 1)` + `/` parsing). Raises `RuntimeError` on empty audit trail or missing expected actions (`hypothesis_generated`, `hypothesis_validated`). Edge cases validated: empty list, mixed dict+string entries.
- Starts a live FastAPI server (port management, uvicorn subprocess). No SKIP_PAUSES env guard needed but worth noting.
- No LocalStack dependency makes it portable.

**Redundancy analysis:** None — unique Phase 2.2 coverage.

**Significance:** **HIGH** — Only Phase 2.2 coverage. Now fully functional as a correctness gate after F3 remediation.

---

### Demo 7 — Lambda Incident (LocalStack End-to-End)

**Stated purpose:** Full-stack Lambda incident response: provision Lambda in LocalStack, trigger CloudWatch alarm, route through SNS → Bridge → SRE Agent webhook, produce LLM-powered audit trail.

**Phase alignment:** Phase 2 ✅ (most complete single-service end-to-end)

**Feature coverage assessment:**
- Exercises the complete alert propagation chain: LocalStack Lambda → CloudWatch → SNS → HTTP Bridge → SRE Agent.
- Validates real SNS subscription confirmation, `set_alarm_state()` shortcut, Lambda creation with synchronous waiter, and the SNS-to-HTTP bridging layer.
- Shares ~300 lines of boilerplate helpers (color printing, LocalStack health check, port kill, agent startup) with Demo 8. Extracted to `_demo_utils.py` partially but duplication persists.

**Correctness evaluation:**
- **Bridge host bug has been fixed (F2).** Demo 7 now uses `BRIDGE_HOST` env var (default `127.0.0.1`) to build the SNS subscription endpoint via `bridge_endpoint`. Guide instructs Docker LocalStack users to set `BRIDGE_HOST=host.docker.internal`. No hardcoded callback endpoint remains.
- `LAMBDA_SYNCHRONOUS_CREATE=1` is set correctly during auto-start.
- Region: `eu-west-3`. Inconsistent with Demos 1, 4, 9.
- SIGINT handler present — clean exit on Ctrl+C.

**Redundancy analysis:** Overlaps with Demo 8 in LocalStack setup boilerplate and diagnosis pipeline invocation. Demo 7 focuses on Lambda; Demo 8 focuses on ECS multi-service. Coverage is complementary.

**Significance:** **CRITICAL** — One of two flagship full-stack LocalStack demos. Now fully portable across Linux and macOS after F2 remediation.

---

### Demo 8 — ECS Multi-Service Cascade

**Stated purpose:** ECS dual-alarm cascade with correlated signals, severity override API (POST + GET), and enriched multi-dimensional incident context.

**Phase alignment:** Phase 2 ✅

**Feature coverage assessment:**
- Richest single demo in the suite. Exercises: dual ECS service alarm chains, correlated signal population, `AlertEnricher` in the incident path, severity override POST/GET lifecycle.
- Uses `BRIDGE_HOST` env var for portability (Linux and macOS compatible).
- `desiredCount=0` workaround for LocalStack Fargate scheduling is well-documented.

**Correctness evaluation:**
- Highest code quality in the suite: proper cleanup, SIGINT handler, structured phase progression.
- `set_alarm_state()` used correctly to bypass CloudWatch evaluation window.
- Region: `eu-west-3`. Inconsistent with other demos.
- Boilerplate duplication with Demo 7 (~300 lines) remains — the `_demo_utils.py` refactor is partial.

**Redundancy analysis:** Unique in ECS multi-service cascade, correlated signals, and severity override API coverage.

**Significance:** **CRITICAL** — The most feature-complete demo in the suite. Serves as the primary reference for full-stack LocalStack integration quality.

---

### Demo 9 — CloudWatch Enrichment

**Stated purpose:** AlertEnricher execution: push synthetic metrics and logs to LocalStack, run the enricher, validate dynamic context extraction before diagnosis.

**Phase alignment:** Phase 2.1 ✅

**Feature coverage assessment:**
- Only demo exercising the `AlertEnricher` enrichment pathway — pre-diagnosis context fetching that prevents token waste on stale signal context.
- Correctly validates that enriched context carries freshness metadata.

**Correctness evaluation:**
- Uses `input()` prompts for interactive pauses — **no `SKIP_PAUSES` support**. Makes it unusable in CI/CD pipelines.
- Region `us-east-1`. `time.sleep(2)` for consistency. Both appropriate.
- Docstring phase label ("Phase 2.3") is imprecise — `AlertEnricher` is Phase 2.1.

**Redundancy analysis:** None. Unique coverage.

**Significance:** **HIGH** — Sole carrier of `AlertEnricher` coverage. Blocked from CI use by missing `SKIP_PAUSES` support.

---

### Demo 10 — EventBridge Timeline Reaction

**Stated purpose:** EventBridge event ingestion → canonical timeline construction. POST synthetic infrastructure state-change events to the `/api/v1/events/aws` endpoint.

**Phase alignment:** Phase 2.3 ✅ (partial)

**Feature coverage assessment:**
- Validates `TimelineConstructor.build()` and the events REST endpoint.
- Does **not** use LocalStack EventBridge — events are POSTed via `FastAPI TestClient`. No real AWS EventBridge webhook integration is demonstrated, despite the guide describing "Cloud Provider events".

**Correctness evaluation:**
- Uses `input()` for pauses — **no `SKIP_PAUSES` support**.
- `TestClient` usage means no real HTTP server lifecycle is exercised.
- Guide documentation implies EventBridge integration exists; this should be clarified.

**Redundancy analysis:** Demo 22 now covers event posting (to `/api/v1/events/aws`) and event retrieval with LocalStack-triggered change events. Demo 10's synthetic `TestClient` approach is a weaker version of the same story.

**Significance:** **MEDIUM** — Provides lightweight timeline construction coverage but functionally weaker than Demo 22. With Demo 22 now present, Demo 10 is partially superseded. Candidate for upgrade to real LocalStack EventBridge integration or consolidation with Demo 22.

---

### Demo 11 — Azure Operations

**Stated purpose:** Phase 1.5 multi-cloud Azure operator abstractions — App Service and Functions operators through `CloudOperatorPort`.

**Phase alignment:** Phase 1.5 ✅

**Feature coverage assessment:**
- Only coverage of Azure operator adapters anywhere in the live demo suite.
- Validates `restart` and `scale` via `AppServiceOperator` and `FunctionsOperator`.
- Does not test error paths or circuit breaker behavior on Azure operators.

**Correctness evaluation:**
- Uses `unittest.mock` — no real Azure SDK calls. The mock assertion passes the full Azure resource URI as `name`, which does not match the real `azure-mgmt-web` SDK signature (expects app name only). Mock assertions may not catch real SDK call failures.
- The test value of this demo is limited: it validates the Python object model but not the real Azure REST API contract.

**Redundancy analysis:** None — unique Azure coverage.

**Significance:** **MEDIUM** — Important for multi-cloud narrative but the mock-only approach means it validates Python structure rather than real Azure behavior. Upgrade path: use LocalStack's Azure emulation layer or a dedicated Azure SDK test account.

---

### Demo 12 — Kubernetes Operations

**Stated purpose:** Phase 3 gap-closure for Kubernetes workloads — demonstrates `kubectl scale`, `rollout restart deployment`, and `rollout restart statefulset`.

**Phase alignment:** Phase 1.5 / Phase 3 ✅ (but simulation-only by default)

**Feature coverage assessment:**
- Addresses the critical K8s gap from the 2026-03-18 review — the `AGENTS.md` defines Kubernetes as the primary operating scope.
- By default runs in `SIMULATION` mode (`RUN_KUBECTL=0`) — no real cluster interaction. Commands are printed but not executed.
- `RUN_KUBECTL=1` triggers real `kubectl` calls, requiring a live cluster.

**Correctness evaluation:**
- The simulation mode is self-honest — clearly labelled, safe for CI.
- No integration with the domain layer: `kubectl` calls are raw subprocess invocations, not routed through `CloudOperatorPort`. This means the demo does not validate the adapter abstraction — it only demonstrates that the right commands would be issued.
- `SKIP_PAUSES` supported ✅.

**Redundancy analysis:** None. Unique K8s coverage.

**Significance:** **MEDIUM** — Closes the documentation gap but does not close the integration gap. A demo that wires `KubernetesOperator` through `CloudOperatorPort` and routes through the domain would be CRITICAL-tier. Current simulation-only mode limits this to LOW-MEDIUM.

---

### Demo 13 — Multi-Agent Lock Protocol

**Stated purpose:** Simulate lock acquisition, priority preemption, cooling-off enforcement, and human override as defined in `AGENTS.md`.

**Phase alignment:** Phase 2.3 ✅

**Feature coverage assessment:**
- Addresses the multi-agent lock gap from the 2026-03-18 review.
- Exercises four scenarios: initial acquisition, higher-priority preemption, cooldown enforcement on re-acquisition, human override kill-switch.
- `DemoLockManager` is a purpose-built standalone class — does **not** use the production `DistributedLockManager` or `EtcdDistributedLockManager` adapters.

**Correctness evaluation:**
- Completely in-memory, no external dependencies.
- `SKIP_PAUSES` supported ✅.
- The standalone `DemoLockManager` faithfully implements the AGENTS.md protocol specification but does not validate the production code paths. This is a design-level demo, not an integration test.
- The KUBERNETES resource type in `record()` provides visual narrative but isn't wired to any real K8s adapter.

**Redundancy analysis:** With Demo 17 retired (F5), Demo 13 and Demo 18 form a clean two-tier ladder: Demo 13 explains the protocol conceptually, Demo 18 validates it with real etcd coordination.

**Significance:** **MEDIUM** — Valuable for explaining the lock protocol conceptually. Downstream trust comes from Demo 18 (etcd).

---

### Demo 14 — Disk Exhaustion (RETIRED)

> **Status: RETIRED** — Deleted as part of the Five Critical Findings Remediation Slice (F4). Was a payload-only stub that generated no pipeline signal and created false confidence in anomaly-type coverage. Disk exhaustion is now documented as an explicit coverage gap.

---

### Demo 15 — Traffic Anomaly (RETIRED)

> **Status: RETIRED** — Deleted as part of the Five Critical Findings Remediation Slice (F4). Same rationale as Demo 14. Traffic anomaly is now documented as an explicit coverage gap.

---

### Demo 16 — X-Ray Tracing (RETIRED)

> **Status: RETIRED** — Deleted as part of the Five Critical Findings Remediation Slice (F4). Was a placeholder with no functional code. X-Ray tracing is now documented as an explicit coverage gap for Phase 2.4+.

---

### Demo 17 — Action-Lock Orchestration (RETIRED)

> **Status: RETIRED** — Deleted as part of the Five Critical Findings Remediation Slice (F5). Overlapped significantly with Demo 23 (same guardrail denial → execution narrative but without real cloud state verification). Demo 13 (protocol narrative) and Demo 23 (LocalStack guardrail proof) are retained as complementary demos covering the action-lock domain.

---

### Demo 18 — External Etcd Action-Lock Flow

**Stated purpose:** Real etcd-backed distributed lock acquisition and remediation execution using a Docker-provisioned etcd container via testcontainers.

**Phase alignment:** Phase 2.3 ✅

**Feature coverage assessment:**
- Only demo validating `EtcdDistributedLockManager` with real external coordination.
- Unique in the suite: real distributed lock semantics verified against an actual etcd process.
- Graceful degradation if etcd3 or testcontainers packages are absent — important for developer onboarding.

**Correctness evaluation:**
- Docker dependency is a hard requirement (not always available in CI). The conditional import check and user-facing error message handle this gracefully.
- 30-second etcd readiness timeout is appropriate.
- Container cleanup on completion ✅.
- Does not integrate with the full diagnosis pipeline — creates a remediation plan directly without going through the LLM/RAG layer.

**Redundancy analysis:** Unique — the only demo using a real external distributed store.

**Significance:** **HIGH** — Critical proof-point that the distributed lock mechanism works with real external coordination, not just in-memory simulations. Should be retained and promoted as the canonical lock integration test.

---

### Demo 19 — RAG Error Evaluation Marathon

**Stated purpose:** Stress-test the RAG pipeline with a stream of heterogeneous production-like errors against LocalStack, producing a scored evaluation with retrieval-grounded and fallback paths distinguished.

**Phase alignment:** Phase 2+ ✅

**Feature coverage assessment:**
- Provisions LocalStack CloudWatch alarms and SNS topic.
- Ingests multi-document runbooks via chunked ingestion.
- Exercises heterogeneous anomaly types in sequence.
- Produces a scorecard comparing: severity, confidence, evidence citations, retrieval path (grounded vs. fallback).
- The most comprehensive LLM + LocalStack combined test in the suite.

**Correctness evaluation:**
- Well-structured, multi-phase execution with clear progress logging.
- `SKIP_PAUSES` supported ✅.
- `LOCALSTACK_ENDPOINT` and `AWS_DEFAULT_REGION` parameterizable ✅.
- Complex orchestration (API startup, LocalStack provisioning, multi-error loop) — failure modes in individual error evaluations should not abort the entire run. Review failure handling in the main loop.
- Relatively underpromoted: it is the deepest RAG validation demo but received less documentation attention than Demos 20-23.

**Redundancy analysis:** Partially overlaps with Demo 7 and Demo 8 in LocalStack + LLM setup patterns but serves a distinct purpose (multi-error evaluation vs. single-incident showcase).

**Significance:** **HIGH** — The primary regression fixture for RAG pipeline correctness under diverse alert types. Should be elevated alongside Demos 7 and 8 as a CRITICAL-tier reference.

---

### Demo 20 — Unknown Incident Safety Net

**Stated purpose:** Demonstrate safe unknown-incident response: baseline diagnosis without a matching runbook (retrieval-miss → human escalation), then re-diagnosis after runbook ingestion, comparing safety signals before and after.

**Phase alignment:** Phase 2.3 ✅

**Feature coverage assessment:**
- Validates the fallback path explicitly: diagnosis with no matching runbook should not produce confident autonomous action.
- Before/after comparison metrics: citation count, confidence, fallback marker presence.
- Runbook ingest-then-re-diagnose flow validates that the knowledge base actively improves outcomes.
- LocalStack Lambda provides realistic incident triggering context.

**Correctness evaluation:**
- Complex orchestration (LocalStack + API startup + multi-phase execution) handled well.
- `SKIP_PAUSES` supported ✅.
- File handle management for API log file present — check for proper cleanup on failure paths.
- LLM key validated upfront — good defensive gate.
- Meets all acceptance criteria documented in `live_demo_20_23_acceptance_criteria.md` ✅.

**Redundancy analysis:** None — unique coverage of the fallback behavior and knowledge base improvement loop.

**Significance:** **HIGH** — Critical for demonstrating safe behavior under uncertainty. The before/after comparison structure makes it compelling for stakeholder presentations.

---

### Demo 21 — Human Governance Lifecycle

**Stated purpose:** Full severity override lifecycle: apply override (POST), verify active state (GET), revoke (DELETE), confirm post-delete 404.

**Phase alignment:** Phase 2.3 ✅

**Feature coverage assessment:**
- Exercises all three REST verbs on the severity override endpoint.
- Validates complete state transitions: APPLIED → ACTIVE → REVOKED.
- POST 200/201, GET 200, DELETE 204, GET 404 (post-delete) all verified.
- LocalStack Lambda provides realistic incident context for the governance action.

**Correctness evaluation:**
- Proper HTTP status code validation at each transition ✅.
- `SKIP_PAUSES` supported ✅.
- Cleanup on exit ✅.
- Meets all acceptance criteria in `live_demo_20_23_acceptance_criteria.md` ✅.

**Redundancy analysis:** Demo 8 also exercises severity override POST + GET but as a secondary feature within a larger ECS demo. Demo 21 makes governance the primary subject with the full DELETE/revoke path that Demo 8 does not cover.

**Significance:** **HIGH** — The canonical governance lifecycle demo. Unique in covering the DELETE/revoke path and presenting governance as the primary narrative rather than a secondary feature.

---

### Demo 22 — Change Event Causality

**Stated purpose:** EventBridge-style change events correlated into diagnosis context — capture Lambda configuration change, post it as an AWS event, retrieve recent events for service, diagnose with event-causality timeline.

**Phase alignment:** Phase 2.3 ✅

**Feature coverage assessment:**
- Validates the `/api/v1/events/aws` endpoint with real AWS-format event payloads.
- Exercises the event retrieval endpoint for service-scoped recent events.
- Diagnosis request includes event correlation context.
- Demonstrates the "deploy → incident → cause" narrative with evidence from the event timeline.

**Correctness evaluation:**
- EventBridge payload format matches AWS standards ✅.
- `SKIP_PAUSES` supported ✅.
- LocalStack Lambda change is real (configuration update on actual Lambda resource) ✅.
- Meets all acceptance criteria in `live_demo_20_23_acceptance_criteria.md` ✅.

**Redundancy analysis:** Partially supersedes Demo 10 (EventBridge timelines) — Demo 22 uses real LocalStack Lambda changes and actual HTTP server interaction vs. Demo 10's `TestClient` approach. Demo 10 is now the weaker version of this story.

**Significance:** **HIGH** — Strong causal narrative (infrastructure change → incident → AI correlates them). The most compelling Phase 2.3 demo for engineering leadership.

---

### Demo 23 — AI Says No Before It Acts

**Stated purpose:** Guardrail-first remediation — high blast-radius plan denied, low blast-radius plan executed with lock, real LocalStack Lambda concurrency modified as execution proof.

**Phase alignment:** Phase 2.3 ✅

**Feature coverage assessment:**
- High blast-radius (0.95) → guardrail denial ✅.
- Low blast-radius (0.05) → execution with distributed lock ✅.
- Pre/post Lambda concurrency comparison proves actual cloud state was modified ✅.
- Uses in-memory components for lock (not etcd) — deterministic.

**Correctness evaluation:**
- Verifies denial path correctness: if high-risk plan incorrectly succeeds, demo fails with explicit error ✅.
- `SKIP_PAUSES` supported ✅.
- Real cloud state verification (concurrency change) makes this the strongest guardrail proof in the suite ✅.
- Meets all acceptance criteria in `live_demo_20_23_acceptance_criteria.md` ✅.

**Redundancy analysis:** With Demo 17 retired (F5), Demo 23 is the sole guardrail-first remediation demo with real cloud state verification. No remaining overlap.

**Significance:** **HIGH** — The canonical guardrail demonstration in the suite. Compelling for safety-conscious audiences.

---

## Coverage Gap Analysis

Features implemented in the codebase but not demonstrated by any executable (non-stub, non-placeholder) demo:

| Gap | Severity | Notes |
|-----|----------|-------|
| Phase 3 remediation saga / rollback | **CRITICAL** | `src/sre_agent/domain/remediation/` contains saga orchestration; no demo exercises compensating transactions or rollback |
| `AnomalyType.DISK_EXHAUSTION` in live pipeline | HIGH | Demo 14 stub retired (F4); disk exhaustion payload never enters the diagnosis pipeline |
| `AnomalyType.TRAFFIC_ANOMALY` in live pipeline | HIGH | Demo 15 stub retired (F4); traffic anomaly payload never enters the diagnosis pipeline |
| Kubernetes operator through `CloudOperatorPort` | HIGH | Demo 12 shells out raw `kubectl`; does not route through the domain adapter abstraction |
| Human kill switch (`kill_switch.py`) | HIGH | `phase_gate.py` and `kill_switch.py` exist in `domain/safety/`; no demo exercises the kill switch endpoint |
| X-Ray / distributed tracing | MEDIUM | Demo 16 placeholder retired (F4); no `XRayAdapter` integration |
| Phase gate graduation criteria | MEDIUM | `phase_gate.py` enforces graduation; no demo validates phase promotion gates |
| Multi-cloud Azure with real SDK calls | MEDIUM | Demo 11 uses mocks; no real Azure endpoint tested |
| Event bus diversity (Kafka, Redis) | LOW | In-memory event bus only; `events/` layer supports alternatives not demonstrated |
| Cooldown enforcement in production lock manager | LOW | Demo 13 simulates cooldown; `EtcdDistributedLockManager` cooldown not validated in Demo 18 |
| Concurrent multi-agent lock contention | LOW | Demo 13 serializes scenarios; no concurrent async contention test |

---

## Recommendations

Prioritized for engineering leadership decision-making on demo maintenance, consolidation, and expansion.

### Priority 1 — Fix Remaining Correctness Defects (Immediate)

| ID | Action | Target Demo | Effort | Impact | Status |
|----|--------|-------------|--------|--------|--------|
| ~~R1~~ | ~~Fix Demo 7 `host.docker.internal` hardcode~~ | ~~Demo 7~~ | ~~XS~~ | ~~Unblocks Linux/CI users~~ | **DONE (F2)** |
| ~~R2~~ | ~~Fix Demo 6 Act 3 audit trail parsing~~ | ~~Demo 6~~ | ~~XS~~ | ~~Restores Phase 2.2 correctness assertion~~ | **DONE (F3)** |
| R3 | Apply blast radius propagation fix to `RAGDiagnosticPipeline` (proposed in `live_demo_evaluation.md §7.5`) | Demos 2, 3 | S | Fixes SEV3 misclassification for Tier-1 flash sale scenarios | Open |
| R4 | Add `SKIP_PAUSES` env guard to Demos 9 and 10 | Demos 9, 10 | XS | Enables CI/CD pipeline inclusion | Open |

### Priority 2 — Retire Low-Value Scripts (Near-Term) — COMPLETED

All items in this priority tier have been completed in the Five Critical Findings Remediation Slice:

| ID | Action | Status |
|----|--------|--------|
| ~~R5~~ | ~~Delete Demo 5 (strict subset of Demo 6)~~ | **DONE (F1)** |
| ~~R6~~ | ~~Delete Demo 14 payload stub~~ | **DONE (F4)** |
| ~~R7~~ | ~~Delete Demo 15 payload stub~~ | **DONE (F4)** |
| ~~R8~~ | ~~Delete Demo 16 placeholder~~ | **DONE (F4)** |

### Priority 3 — Close Critical Coverage Gaps (Medium-Term)

| ID | Action | Addresses Gap | Effort |
|----|--------|--------------|--------|
| R9 | Build **Demo 24: Phase 3 Saga Rollback** — trigger a failed remediation and validate compensating transaction execution | Phase 3 remediation | L |
| R10 | Expand Demo 12 to route through `KubernetesOperator` and `CloudOperatorPort` rather than raw subprocess; require `kubeconfig` or use `kind` in testcontainers | K8s operator integration | M |
| R11 | Build new disk exhaustion and traffic anomaly demos as real diagnosis runs: POST to the agent API, capture LLM diagnosis output for `DISK_EXHAUSTION` and `TRAFFIC_ANOMALY` | Anomaly type coverage | S |
| R12 | Add a **human kill switch demo** — activate kill switch via API, attempt remediation, confirm all agents denied | Kill switch | S |

### Priority 4 — Reduce Overlap and Improve Cohesion (Backlog)

| ID | Action | Details | Status |
|----|--------|---------|--------|
| ~~R13~~ | ~~Consolidate action-lock demos: retire Demo 17~~ | ~~Reduces 3 overlapping demos to 2 complementary ones~~ | **DONE (F5)** |
| R14 | Upgrade Demo 10 to use real LocalStack EventBridge or retire and consolidate into Demo 22 | Removes `TestClient` weakness, avoids guide confusion | Open |
| R15 | Standardize LocalStack region to `us-east-1` across all demos via `AWS_DEFAULT_REGION` env var — currently split between `us-east-1` (Demos 1, 4, 9, 19–23) and `eu-west-3` (Demos 7, 8) | Eliminates namespace confusion when running multiple demos against the same LocalStack instance | Open |
| R16 | Standardize file naming: rename all unnamed demos to `live_demo_NN_<name>.py` with zero-padded numbers (e.g., `live_demo_02_cascade_failure.py`) | Consistent naming enables glob-based CI ordering | Open |
| R17 | Elevate Demo 19 (RAG Error Evaluation Marathon) in guide documentation to CRITICAL tier alongside Demos 7 and 8 — it is the deepest LLM regression fixture and currently receives insufficient prominence | Guide update only | Open |

---

## Summary Scorecard

| Demo | Significance | Correctness | CI-Ready | Status |
|------|-------------|-------------|----------|--------|
| 1 | HIGH | ✅ | ✅ | Retain |
| 2 | HIGH | ⚠️ (blast radius) | ✅ | Fix R3 |
| 3 | HIGH | ⚠️ (blast radius) | ✅ | Fix R3 |
| 4 | CRITICAL | ⚠️ (LAMBDA_SYNC) | ✅ | Minor fix |
| ~~5~~ | — | — | — | **RETIRED (F1)** |
| 6 | HIGH | ✅ (Act 3 fixed) | ✅ | Retain |
| 7 | CRITICAL | ✅ (bridge fixed) | ✅ | Retain |
| 8 | CRITICAL | ✅ | ✅ | Retain |
| 9 | HIGH | ✅ | ❌ (no SKIP_PAUSES) | Fix R4 |
| 10 | MEDIUM | ✅ | ❌ (no SKIP_PAUSES) | Fix R4 + R14 |
| 11 | MEDIUM | ⚠️ (mock assertions) | ✅ | Retain/Upgrade |
| 12 | MEDIUM | ✅ (simulation) | ✅ | Upgrade (R10) |
| 13 | MEDIUM | ✅ | ✅ | Retain |
| ~~14~~ | — | — | — | **RETIRED (F4)** |
| ~~15~~ | — | — | — | **RETIRED (F4)** |
| ~~16~~ | — | — | — | **RETIRED (F4)** |
| ~~17~~ | — | — | — | **RETIRED (F5)** |
| 18 | HIGH | ✅ | ⚠️ (Docker req) | Retain |
| 19 | HIGH | ✅ | ✅ | Elevate (R17) |
| 20 | HIGH | ✅ | ✅ | Retain |
| 21 | HIGH | ✅ | ✅ | Retain |
| 22 | HIGH | ✅ | ✅ | Retain |
| 23 | HIGH | ✅ | ✅ | Retain |

**Completed (Five Critical Findings Remediation):** R1, R2, R5, R6, R7, R8, R13
**Remaining immediate actions (0-2 days):** R3 (blast radius propagation), R4 (SKIP_PAUSES on Demos 9/10)
**High-leverage investments (1-2 sprints):** R9 (Phase 3 saga demo), R10 (K8s operator integration), R11 (disk/traffic anomaly real runs)

---

*This report supersedes the partial findings in `live_demo_review_report.md` (2026-03-18) and `live_demo_analysis_report.md` (DRAFT). Prior reports remain valuable for historical context on the blast-radius and severity bugs documented in live runs.*

*Updated 2026-03-31 to reflect resolution of all five critical findings via the Five Critical Findings Remediation Slice. Verification artifacts at `docs/reports/*/live_demo_five_critical_findings_*.md`.*
