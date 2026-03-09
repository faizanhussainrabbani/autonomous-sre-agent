---
title: "Live E2E Demo — Critical Evaluation Report"
description: "Post-run analysis of the Phase 2 Intelligence Layer live demonstration. Covers what worked perfectly, what requires improvement, and detailed recommendations per pipeline stage."
ms.date: 2026-03-09
version: "1.0"
status: "FINAL"
author: "SRE Agent Engineering"
---

# Live E2E Demo — Critical Evaluation Report

**Run Date:** 2026-03-09  
**Script:** `scripts/live_e2e_demo.py`  
**LLM Provider:** Anthropic Claude (claude-sonnet-4-20250514)  
**Embedding Model:** `all-MiniLM-L6-v2` (sentence-transformers)  
**Vector Store:** ChromaDB (in-memory)  
**Total Pipeline Duration:** 19.10 s  
**Commit at Time of Run:** `3126ba0` + patch (fence-stripping fix)

---

## 1. Executive Summary

The live demo validated the end-to-end Intelligence Layer (Phase 2) against a real Anthropic LLM API. After a targeted fix to the JSON response parser (Anthropic returns markdown-fenced JSON; OpenAI does not), all pipeline stages produced correct output. Confidence scoring improved from 39.6% (failed parse) to **69.3%** (successful parse). The ThrottledLLMAdapter priority queue, Event Bus wiring, HITL guardrail, and token tracking all functioned as designed.

Seven improvement areas were identified ranging from severity misclassification to cold-start latency and prompt injection risk.

---

## 2. Stage-by-Stage Evaluation

| # | Stage | Status | Observation |
|---|---|---|---|
| 0 | Bootstrap (adapters) | ✅ **Perfect** | ChromaDB + sentence-transformers + Anthropic loaded in 2.64 s (excluding model download) |
| 1 | Knowledge ingestion | ✅ **Perfect** | 2 documents vectorized and stored; ingestion pipeline correctly logged `chunks=1` per doc |
| 2 | Anomaly construction | ✅ **Perfect** | `AnomalyAlert` built with correct `KUBERNETES` compute mechanism, Tier-1, 12.5σ deviation |
| 3 | Vector retrieval | ✅ **Perfect** | nginx-502 post-mortem matched at **0.90 relevance**; DB runbook at 0.62; top-k filtering working |
| 4 | LLM hypothesis generation | ✅ **Fixed** | Root cause correctly parsed after fence-stripping fix; matches post-mortem RCA exactly |
| 5 | Second-opinion validation | ✅ **Fixed** | Validation LLM call (seq=1) completed; reasoning list normalized to numbered string |
| 6 | Confidence scoring | ⚠️ **Needs Tuning** | 69.3% for a Tier-1 0.90-relevance match; service tier weight not factored in scorer |
| 7 | Severity classification | ❌ **Bug** | `SEV3` assigned to Tier-1 + 12.5σ alert; expected `SEV1` or `SEV2` |
| 8 | ThrottledLLMAdapter | ✅ **Perfect** | Both LLM calls enqueued at `priority=3`; drain loop active; `queue_depth` observable |
| 9 | Event emission | ✅ **Perfect** | 4 domain events emitted (INCIDENT_DETECTED → DIAGNOSIS_GENERATED → SECOND_OPINION_COMPLETED → SEVERITY_ASSIGNED) |
| 10 | HITL Guardrail | ✅ **Perfect** | `requires_human_approval=True` fired correctly; auto-remediation blocked |
| 11 | Token tracking | ✅ **Perfect** | 946 prompt / 703 completion / 1649 total — exact Anthropic API counts |
| 12 | Display formatting | ✅ **Fixed** | Reasoning rendered as numbered list; remediation word-wrapped; empty-field fallbacks shown |

---

## 3. What Worked Perfectly

### 3.1 Retrieval Accuracy

The vector retrieval stage delivered a **0.90 relevance score** for the nginx-502 post-mortem against an alert for the same service and symptom pattern. This demonstrates that `all-MiniLM-L6-v2` embeddings capture semantic intent even in short runbook excerpts. The DB-latency runbook scored 0.62 and was correctly ranked second (lower relevance to a 502 error scenario).

### 3.2 LLM Hypothesis Quality

Claude's hypothesis matched the ground-truth root cause from the post-mortem without hallucination:

> *"Upstream backend-api service overwhelmed and crashing due to connection pool exhaustion, causing nginx-gateway to return 502 Bad Gateway errors when unable to reach healthy backend instances."*

All 6 reasoning steps cited specific evidence sources and discriminated between high-relevance (nginx post-mortem) and lower-relevance (DB latency) evidence.

### 3.3 ThrottledLLMAdapter Bulkhead

Both the hypothesis and validation LLM calls were serialized through the priority queue (`seq=0`, `seq=1`), confirming the bulkhead pattern (Gap B) is operational in a live environment. The default priority of 3 was applied (SEV propagation is a known improvement area — see §4.2).

### 3.4 Event Bus Wiring

The pipeline correctly emitted 4 ordered domain events via `InMemoryEventBus` and persisted them in `InMemoryEventStore`. The `aggregate_id` was consistent across all events, enabling CQRS event replay. Fire-and-forget emission did not add measurable latency.

### 3.5 HITL Guardrail

Despite `SEV3` classification, the `requires_human_approval` guardrail fired correctly because the severity override check applies to any Tier-1 service where auto-remediation has not been explicitly authorized. This is the correct defensive posture.

---

## 4. Improvement Areas

### 4.1 [CRITICAL] Severity Misclassification — Tier-1 + 12.5σ → SEV3

**Observation:** A Tier-1 nginx service spiking to +12.5σ at 150 eps received `SEV3`. Industry convention and the SLO definitions in `docs/operations/slos_and_error_budgets.md` mandate `SEV1` or `SEV2` for Tier-1 outages with deviation ≥ 5σ.

**Root Cause:** `SeverityClassifier` computes a composite score from `[llm_confidence, validation_confidence, deviation_sigma, service_tier]` but the current weighting produces a raw score of `0.46` which maps to `SEV3`. Service tier (TIER_1 = 1) is encoded but its weight in the linear combination is insufficient to push the score into the SEV1 band.

**Recommended Fix:** Introduce a tier-override floor: if `service_tier == TIER_1` and `deviation_sigma >= 5`, the severity floor is `SEV2`. If `deviation_sigma >= 10`, the floor is `SEV1`. The classifier should implement this as a post-scoring clamp before returning.

```python
# Proposed addition to SeverityClassifier.classify()
if request.service_tier == ServiceTier.TIER_1 and request.deviation_sigma >= 10.0:
    return Severity.SEV1
if request.service_tier == ServiceTier.TIER_1 and request.deviation_sigma >= 5.0:
    return min(severity, Severity.SEV2)  # floor at SEV2
```

**Phase Target:** Phase 3 (Remediation Intelligence).

---

### 4.2 [HIGH] LLM Priority Not Propagated from Alert Severity

**Observation:** Both LLM calls were enqueued at `priority=3` (the default). The ThrottledLLMAdapter's priority queue is designed to serve SEV1 (priority=1) ahead of SEV4 (priority=4), but the alert's deviation sigma (12.5) and Tier-1 status are not translated into a request priority before enqueueing.

**Recommended Fix:** In `RAGDiagnosticPipeline.diagnose()`, set `HypothesisRequest.priority` based on alert metadata before passing to the LLM port. A simple mapping:

```python
# In rag_pipeline.py — before calling generate_hypothesis
priority = max(1, 5 - int(request.alert.deviation_sigma // 3))  # 12.5σ → priority 1
hyp_request = HypothesisRequest(..., priority=priority)
```

**Phase Target:** Phase 3 sprint 1.

---

### 4.3 [HIGH] Embedding Model Cold-Start Latency (~13 s on First Run)

**Observation:** The `all-MiniLM-L6-v2` model requires ~13 s to load on first invocation (includes HuggingFace Hub check and weight loading). Subsequent runs within the same process are instant (model cached in memory). In a production scenario, this cold-start adds 13 s to the first alert after process restart.

**Recommended Fix:**
1. Add a `warm_up()` call in `intelligence_bootstrap.py` that embeds a no-op string at startup.
2. Alternatively, persist the downloaded model path in a Docker layer or pre-bake into the container image to eliminate the download step.
3. Consider `TOKENIZERS_PARALLELISM=false` as a default environment variable in `config/agent.yaml` or the service Dockerfile.

**Phase Target:** Phase 3 (pre-production hardening).

---

### 4.4 [HIGH] Total Pipeline Latency: 19.10 s (Sequential LLM Calls)

**Observation:** The hypothesis generation call and validation call are executed sequentially (await hypothesis → await validation). Each Anthropic API call takes ~9–10 s at current load, for a combined total of ~19 s per diagnosis.

**Target SLO from `docs/operations/slos_and_error_budgets.md`:** Alert diagnosis latency ≤ 60 s (Phase 2). Currently within SLO but leaves only 41 s margin.

**Recommended Fix:** For Phase 3, the validation call can be launched concurrently with post-hypothesis bookkeeping steps using `asyncio.gather()`:

```python
# Concurrent hypothesis + timeline expansion (if decoupled)
hypothesis, _ = await asyncio.gather(
    self._llm.generate_hypothesis(hyp_request),
    self._timeline.expand_async(correlated_signals),
)
```

The validation call must wait for the hypothesis but can overlap with confidence scoring preparation.

**Phase Target:** Phase 3 sprint 2 (latency optimization).

---

### 4.5 [MEDIUM] Single-Chunk Document Ingestion (No Smart Chunking)

**Observation:** Both documents were ingested as single chunks (`chunks=1`). Long runbooks or post-mortems with multiple sections would be stored as one large embedding vector, degrading retrieval precision (the embedding averages across all sections).

**Recommended Fix:** Implement a `MarkdownChunker` in `adapters/storage/` that splits on `##` headings, with a max-chunk-size of 512 tokens. This ensures each chunk encodes a semantically coherent section.

**Phase Target:** Phase 3 sprint 1 (knowledge base quality).

---

### 4.6 [MEDIUM] `HuggingFace` FutureWarning: `resume_download` Deprecated

**Observation:**
```
FutureWarning: `resume_download` is deprecated and will be removed in version 1.0.0.
```

This is emitted by `huggingface_hub` because `sentence-transformers` calls an older HuggingFace API. This warning will become an error in a future `huggingface_hub` release.

**Recommended Fix:** Pin `huggingface_hub>=0.24` in `pyproject.toml` under `[intelligence]` extras, which includes the `force_download` migration. Alternatively, upgrade `sentence-transformers` to the latest version which should resolve this internally.

**Phase Target:** Maintenance sprint (dependency pinning).

---

### 4.7 [LOW] Demo Script Accesses Private Attributes Directly

**Observation:** The demo script sets `pipeline._event_bus` and `pipeline._event_store` directly, bypassing the public API. This is fragile and will break silently if the constructor parameter names change.

**Recommended Fix:** Expose `event_bus` and `event_store` as properties on `RAGDiagnosticPipeline`, or pass them through `create_diagnostic_pipeline()` in `intelligence_bootstrap.py` so the demo uses the public factory:

```python
pipeline = create_diagnostic_pipeline(
    vector_store=vs,
    embedding=emb,
    llm=llm,
    service_tiers={"nginx-gateway": ServiceTier.TIER_1},
    context_budget=4000,
    event_bus=InMemoryEventBus(),      # ← pass through public factory
    event_store=InMemoryEventStore(),
)
```

**Phase Target:** Phase 3 sprint 1 (API hygiene).

---

## 5. Quantitative Summary

| Metric | Observed | Target | Status |
|---|---|---|---|
| Total pipeline latency | 19.10 s | ≤ 60 s | ✅ Within SLO |
| Embedding cold-start (first run) | ~13 s | ≤ 3 s (warm) | ⚠️ Cold-start gap |
| Vector retrieval relevance (top-1) | 0.90 | ≥ 0.75 | ✅ |
| LLM hypothesis confidence | 85% (Claude internal) | ≥ 70% | ✅ |
| Composite confidence score | 69.3% | ≥ 80% for SEV1 | ⚠️ Calibration needed |
| Severity assigned | SEV3 | SEV1 (Tier-1, 12.5σ) | ❌ Misclassified |
| Token usage (total) | 1,649 | ≤ 4,000 context budget | ✅ |
| Guardrail (HITL) correctness | Fired | Must fire for SEV1–3 | ✅ |
| Evidence citations returned | 2 | ≥ 1 | ✅ |
| Parse failure rate | 0% (post-fix) | 0% | ✅ |

---

## 6. Priority Improvement Roadmap

| Priority | Item | Effort | Phase Target |
|---|---|---|---|
| P0 | Severity classifier tier-floor clamp | S (< 1 day) | Phase 3 sprint 1 |
| P1 | LLM priority propagation from alert sigma | S (< 1 day) | Phase 3 sprint 1 |
| P2 | Embedding model warm-up at startup | S (< 1 day) | Phase 3 sprint 1 |
| P3 | Markdown-aware document chunking | M (2–3 days) | Phase 3 sprint 1 |
| P4 | Concurrent hypothesis + validation calls | M (2–3 days) | Phase 3 sprint 2 |
| P5 | Expose event_bus/event_store via factory | XS (hours) | Phase 3 sprint 1 |
| P6 | Pin `huggingface_hub>=0.24` | XS (hours) | Maintenance |

---

*Report generated from live run output captured at 2026-03-09 13:35:52 UTC.*

---

## 7. Demo 2 — Flash Sale Cascade Failure (2026-03-09)

**Script:** `scripts/live_demo_cascade_failure.py`
**LLM Provider:** Anthropic Claude (claude-sonnet-4-20250514)
**Total Token Usage:** 4,148 prompt / 1,905 completion / 6,053 total

### 7.1 Scenario Summary

Three simultaneous Black Friday incidents: order-service OOM, downstream checkout-service HTTP 503 surge, and api-gateway latency spike. Designed to validate multi-incident isolation, cross-service cascade tracing, and event store isolation.

### 7.2 Results

| Service | Anomaly Type | Severity | Confidence | Approval | Diagnosis Time |
|---|---|---|---|---|---|
| order-service | OOM kill | SEV3 | 72.6% | Required | ~16 s |
| checkout-service | HTTP 503 surge | SEV3 | 78.2% | Required | ~14 s |
| api-gateway | Latency spike | SEV3 | 70.9% | Required | ~15 s |

### 7.3 LLM Response Quality

**order-service:** "Unbounded in-memory shopping cart object pool accumulation during flash sale event" — exact root cause match to the ingested post-mortem. Remediation correctly called for pod restart + JVM heap limit patch.

**checkout-service:** "order-service unavailable or crashing, likely due to resource exhaustion (OOM)" — correctly traced the cascade origin upstream without being told the two incidents were related.

**api-gateway:** "Upstream order-service degradation causing cascade through checkout-service to api-gateway." Remediation explicitly advised: "Do NOT restart api-gateway pods until upstream root cause is fixed" — matching runbook guidance verbatim.

**Overall:** Cascade chain reasoning is strong. The LLM identified the root → intermediate → symptom chain purely from evidence context, with no explicit cross-incident signal in the alert payloads.

### 7.4 Event Isolation Verification

Each incident used an isolated `InMemoryEventBus` and `InMemoryEventStore`. Post-run checks confirmed:

- 4 events per incident (INCIDENT_DETECTED → DIAGNOSIS_GENERATED → SECOND_OPINION_COMPLETED → SEVERITY_ASSIGNED)
- Zero cross-contamination across 3 aggregate IDs
- `await es.get_events(str(alert_id))` pattern confirmed as the correct API call signature

### 7.5 Improvement Areas Discovered

**[CRITICAL] — Blast Radius Not Propagated to Severity Classifier**

All three Tier 1/Tier 2 services received SEV3 despite a flash sale affecting thousands of users. `RAGDiagnosticPipeline` always passes `blast_radius_ratio=0.0` to `SeverityClassifier.classify()`. For a flash sale scenario, `blast_radius_ratio` should be `1.0` (all users affected), which would push the ImpactDimensions score from ~0.46 into the SEV1/SEV2 band.

**Fix:**

```python
# In rag_pipeline.py — DiagnosisRequest should include blast_radius
blast_radius = getattr(request.alert, "blast_radius_ratio", 0.0)
severity = self._severity.classify(
    SeverityRequest(
        service=request.alert.service,
        deviation_sigma=request.alert.deviation_sigma,
        blast_radius_ratio=blast_radius,   # ← propagate from alert
        ...
    )
)
```

**[MEDIUM] — SEVERITY_ASSIGNED Metric Always Shows `service_tier=unknown`**

The Prometheus counter uses `getattr(request.alert, "service_tier", "unknown")` but `AnomalyAlert` has no `service_tier` attribute. The tier lives only inside `SeverityClassifier._service_tiers`.

**Fix:** After calling `self._severity.classify()`, use the returned tier label as the metric tag rather than reading from the alert object.

---

## 8. Demo 3 — Deployment Regression and Infrastructure Fragility (2026-03-09)

**Script:** `scripts/live_demo_deployment_regression.py`
**LLM Provider:** Anthropic Claude (claude-sonnet-4-20250514)
**Total Token Usage:** 3,219 prompt / 1,353 completion / 4,572 total

### 8.1 Scenario Summary

Three-act demo covering: (1) a bad canary deployment detected via error rate surge, (2) circuit breaker state machine trip and recovery under simulated cloud operator failure, and (3) TLS certificate expiry advisory 5.8 hours before deadline.

### 8.2 Results

| Act | Scenario | Severity | Confidence | LLM Agreed | Approval |
|---|---|---|---|---|---|
| 1 | Deployment regression (checkout v2.3.1) | SEV2 | 73.4% | No (−7.5 pp) | Required |
| 2 | Circuit breaker CLOSED→OPEN→HALF_OPEN→CLOSED | — | — | — | — |
| 3 | TLS certificate expiry (5.8 h) | SEV3 | 80.7% | Yes | Required |

### 8.3 Act 1 — LLM Response Quality

Root cause identified: "Pydantic v3 field serialization changed default encoding for UUID fields in checkout-service v2.3.1, causing 400+ legacy API clients to receive malformed responses and generate HTTP 503 errors."

Recommended action: `kubectl rollout undo deployment/checkout-service` — the exact command from the ingested deployment runbook.

Key observation: The validator disagreed with the hypothesis (`validation_agrees=False`), correctly applying the 30% penalty (LLM confidence: 0.92 → Composite: 0.7337). This confirms that the confidence scoring disagreement penalty operates correctly in live conditions.

The pipeline's `severity_deployment_elevation` log shows `elevated=SEV2 original=SEV3` — confirming the deployment-induced elevation override is functioning. Checkout-service (TIER_2) scored SEV3 on impact dimensions alone, but the pipeline correctly elevated to SEV2 because a deployment was detected in the alert metadata.

### 8.4 Act 2 — Circuit Breaker State Machine

The complete CLOSED → OPEN → HALF_OPEN → CLOSED cycle was observed with correct Prometheus gauge values:

| Transition | Trigger | State | Gauge |
|---|---|---|---|
| Initial | — | CLOSED | 0 |
| After 5 failures | Failure threshold crossed | OPEN | 2 |
| After 3 s timeout | Recovery window elapsed | HALF_OPEN | 1 |
| After successful probe | Cloud operator recovered | CLOSED | 0 |

Intermediate remediation call during OPEN state correctly raised `CircuitOpenError` with the remaining recovery time, confirming the fail-fast mechanism blocks wasted latency on a known-failing operator.

### 8.5 Act 3 — LLM Response Quality

Root cause: "Let's Encrypt rate limit exceeded preventing cert-manager from automatically renewing the TLS certificate for api-gateway, requiring manual intervention before expiry at 22:00 UTC." — specific and directly actionable.

Renewal steps returned: `kubectl describe certificate api-gateway-tls -n prod`, manual CSR generation path, and `openssl s_client -connect api.example.com:443` post-renewal validation — all from the ingested runbook.

**Observation:** `circuit-breaker-fragility.md` was returned as evidence citation [2] for a certificate expiry alert. This demonstrates a retrieval noise issue: the runbook ranked highly due to term overlap ("fragility", "recovery"), not semantic relevance to certificate management.

### 8.6 Improvement Areas Discovered

**[HIGH] — Certificate Expiry Severity Should Scale Dynamically with Hours Remaining**

Current behavior: any `CERTIFICATE_EXPIRY` alert is diagnosed at a static severity regardless of the urgency window. A certificate expiring in 5.8 hours and one expiring in 5 days receive identical treatment.

**Proposed fix:**

```python
# In SeverityClassifier.classify() or rag_pipeline.py pre-processing
if alert.anomaly_type == AnomalyType.CERTIFICATE_EXPIRY:
    hours_remaining = alert.current_value  # current_value encodes hours
    if hours_remaining < 2:
        severity_floor = Severity.SEV1
    elif hours_remaining < 6:
        severity_floor = Severity.SEV2
    elif hours_remaining < 24:
        severity_floor = Severity.SEV3
    severity = min(severity, severity_floor)
```

**[MEDIUM] — Evidence Ranking Noise for Anomaly-Type Mismatches**

`circuit-breaker-fragility.md` appearing in certificate expiry results indicates that the vector retrieval stage does not filter by anomaly type affinity. Adding a lightweight metadata filter (`anomaly_type` tag at ingestion time) would increase evidence precision.

**[CRITICAL / Design Gap] — Tier 1 + SEV3 + AUTONOMOUS Confidence Bypasses Approval**

Documented in the E2E test suite (`TestS8ConfidenceThresholdBoundary`): the approval logic in `rag_pipeline.py` is:

```python
requires_approval = severity in (SEV1, SEV2) or confidence_level != "AUTONOMOUS"
```

A Tier 1 service that receives SEV3 (due to missing blast radius) and achieves confidence ≥ 0.85 (AUTONOMOUS) would be cleared for autonomous execution with no human check. This is incorrect for any Tier 1 or Tier 2 service.

**Proposed fix:**

```python
requires_approval = (
    severity in (Severity.SEV1, Severity.SEV2)
    or confidence_level != "AUTONOMOUS"
    or service_tier in (ServiceTier.TIER_1, ServiceTier.TIER_2)  # ← add tier guard
)
```

---

## 9. Combined Improvement Roadmap (All Demos)

| Priority | Gap | Demo | Effort | Phase Target |
|---|---|---|---|---|
| P0 | Tier 1/2 approval guard missing in pipeline | Demo 2, Demo 3 | S | Phase 3 sprint 1 |
| P0 | Blast radius not propagated to severity classifier | Demo 2 | S | Phase 3 sprint 1 |
| P1 | Certificate expiry severity floor based on hours_remaining | Demo 3 | S | Phase 3 sprint 1 |
| P1 | SEVERITY_ASSIGNED metric always reports service_tier=unknown | Demo 2 | S | Phase 3 sprint 1 |
| P2 | Evidence ranking noise — anomaly-type metadata filtering | Demo 3 | M | Phase 3 sprint 2 |
| P2 | Sequential LLM calls add ~15 s per diagnosis (two round trips) | Demo 2, Demo 3 | M | Phase 3 sprint 2 |
| P3 | Deployment elevation covers TIER_2 only — not Tier 1 with high sigma | Demo 3 | S | Phase 3 sprint 2 |

*Sections 7–9 added from live demo runs on 2026-03-09.*
