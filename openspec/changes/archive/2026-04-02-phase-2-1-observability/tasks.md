## OBS-001 — Prometheus Metrics Module (Critical Path)

- [x] 1.1 Create `src/sre_agent/adapters/telemetry/metrics.py` — centralized Prometheus metric registry
- [x] 1.2 Define `DIAGNOSIS_DURATION` Histogram (labels: `service`, `severity`; buckets: 1–60s)
- [x] 1.3 Define `DIAGNOSIS_ERRORS` Counter (label: `error_type`: timeout/llm_error/parse_error/vector_error)
- [x] 1.4 Define `SEVERITY_ASSIGNED` Counter (labels: `severity`, `service_tier`)
- [x] 1.5 Define `EVIDENCE_RELEVANCE` Histogram (top-1 vector retrieval score; buckets: 0.1–1.0)
- [x] 1.6 Define `LLM_CALL_DURATION` Histogram (labels: `provider`, `call_type`; buckets: 0.5–30s)
- [x] 1.7 Define `LLM_TOKENS_USED` Counter (labels: `provider`, `token_type`)
- [x] 1.8 Define `LLM_PARSE_FAILURES` Counter (label: `provider`)
- [x] 1.9 Define `LLM_QUEUE_DEPTH` Gauge (ThrottledLLMAdapter priority queue depth)
- [x] 1.10 Define `LLM_QUEUE_WAIT` Histogram (time in queue before LLM call; buckets: 0.1–10s)
- [x] 1.11 Define `EMBEDDING_DURATION` Histogram (embedding generation latency; buckets: 0.01–5s)
- [x] 1.12 Define `EMBEDDING_COLD_START` Gauge (seconds to load model on first call)
- [x] 1.13 Define `CIRCUIT_BREAKER_STATE` Gauge (labels: `provider`, `resource_type`; values: 0/1/2)
- [x] 1.14 Expose `prometheus_client.make_wsgi_app()` endpoint on `/metrics` via FastAPI `Mount`

## OBS-003 — SLO Instrumentation (Critical)

- [x] 3.1 Add `/healthz` GET endpoint to `src/sre_agent/api/main.py`
- [x] 3.2 `/healthz` checks vector store `health_check()`, embedding `health_check()`, and LLM client initialization
- [x] 3.3 `/healthz` returns HTTP 503 with component-level detail when any check fails
- [x] 3.4 Observe `DIAGNOSIS_DURATION` histogram at the end of `RAGDiagnosticPipeline.diagnose()`
- [x] 3.5 Observe `EVIDENCE_RELEVANCE` histogram for top-1 evidence score after vector search
- [x] 3.6 Increment `SEVERITY_ASSIGNED` counter after severity classification
- [x] 3.7 Increment `DIAGNOSIS_ERRORS` on timeout, LLM error, parse error, and vector store error paths

## OBS-004 — Structured Logging (Medium)

- [x] 4.1 Add `diagnosis_started` log (info) at top of `diagnose()` with `alert_id`, `service`, `anomaly_type`
- [x] 4.2 Add `embed_alert` log (debug) before embedding call with token count estimate
- [x] 4.3 Add `vector_search_complete` log (debug) with `result_count` and `top_relevance` score
- [x] 4.4 Add `token_budget_trim` log (debug) with `evidence_before` and `evidence_after` count
- [x] 4.5 Add `llm_hypothesis_start` log (debug) with `evidence_count` and `priority`
- [x] 4.6 Add `validation_start` log (debug) with `hypothesis_confidence`
- [x] 4.7 Add `confidence_scored` log (debug) with `raw_score` and `composite_confidence`
- [x] 4.8 Add `diagnosis_completed` log (info) with `alert_id`, `severity`, `confidence`, `duration_seconds`, `requires_human_approval`
- [x] 4.9 Add `log_requests` HTTP middleware to FastAPI `create_app()` — logs `request_received` (info) and `request_completed` (info) with `request_id`, method, path, status_code, duration
- [x] 4.10 Inject `X-Request-ID` header into all HTTP responses

## OBS-006 — Token Usage as Prometheus Counters (Medium)

- [x] 6.1 Import `LLM_TOKENS_USED` and `LLM_CALL_DURATION` into `AnthropicLLMAdapter`
- [x] 6.2 Increment `LLM_TOKENS_USED{provider="anthropic", token_type="prompt"}` after each `generate_hypothesis` call
- [x] 6.3 Increment `LLM_TOKENS_USED{provider="anthropic", token_type="completion"}` after each `generate_hypothesis` call
- [x] 6.4 Observe `LLM_CALL_DURATION{provider="anthropic", call_type="hypothesis"}` histogram
- [x] 6.5 Repeat for `validate_hypothesis` (call_type="validation")
- [x] 6.6 Repeat all steps 6.1–6.5 for `OpenAILLMAdapter` (provider="openai")

## OBS-007 — Correlation ID Context Variable (High)

- [x] 7.1 Define `_current_alert_id: contextvars.ContextVar[str]` in `rag_pipeline.py`
- [x] 7.2 Set `_current_alert_id` at the start of `diagnose()` using `token = _current_alert_id.set(alert_id)`
- [x] 7.3 Reset `_current_alert_id` in a `finally` block at the end of `diagnose()`
- [x] 7.4 Add a structlog processor `_bind_alert_id` that reads `_current_alert_id.get()` and adds `alert_id` to the event dict
- [x] 7.5 Register `_bind_alert_id` in the structlog processor chain in `config/logging.py`

## OBS-008 — Prometheus Alert Rules (High)

- [x] 8.1 Create `infra/prometheus/rules/sre_agent_slo.yaml`
- [x] 8.2 Add recording rule `sre_agent:diagnosis_latency:p99`
- [x] 8.3 Add `DiagnosisLatencySLOBreach` alert (P99 > 30s for 2 min, critical)
- [x] 8.4 Add `LLMAPIErrors` alert (llm_error rate > 0.1/s for 1 min, critical)
- [x] 8.5 Add `LLMParseFailureSpike` alert (parse_failures > 0.05/s for 30s, warning)
- [x] 8.6 Add `ThrottleQueueSaturation` alert (queue_depth > 5 for 1 min, warning)
- [x] 8.7 Add `EvidenceQualityDrop` alert (median relevance < 0.5 for 5 min, warning)
- [x] 8.8 Add `LLMTokenRateTooHigh` alert (tokens/min > 80,000 for 30s, warning)
- [x] 8.9 Add `EmbeddingColdStartHigh` alert (cold_start_seconds > 15 for single occurrence, warning)

## OBS-009 — Circuit Breaker State Export (Medium)

- [x] 9.1 Import `CIRCUIT_BREAKER_STATE` gauge into `src/sre_agent/adapters/cloud/resilience.py`
- [x] 9.2 Set gauge to 0 (CLOSED), 1 (HALF_OPEN), or 2 (OPEN) on every `_transition_state()` call
- [x] 9.3 Labels include `provider` and `resource_type` derived from the monitor's attributes
