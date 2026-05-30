# Targeted Verification Research
**Date:** 2026-05-30  
**Status:** Complete  

## Research Topics
Verification of 14 specific implementation checks in the SREAgent codebase.

---

## Findings

### Check 1: Persistence Port File (T013 / Phase 4.0)
- **Finding:** All three ABCs are fully defined with complete abstract method signatures.
  - `IncidentStorePort` (lines ~220-310): save_event, get_events_by_incident, get_incident, update_projection
  - `OutboxPort` (lines ~315-380): enqueue, mark_sent, mark_dlq, mark_failed, is_event_processed, mark_event_processed
  - `CoordinationAuditPort` (lines ~110-185): record_lock_event, record_cooldown_event, record_override_event, get_audit_trail
- **Evidence:** `src/sre_agent/ports/persistence.py` lines 110, 220, ~315 — all three classes defined as `class XxxPort(ABC)` with `@abstractmethod` decorators.
- **Status:** CONFIRMED

---

### Check 2: Prometheus Alert Rules
- **Finding:** 1 recording rule + 8 alert rules = 9 total rules.
  - Recording rule: `sre_agent:diagnosis_latency:p99`
  - Alert rules:
    1. `DiagnosisLatencySLOBreach`
    2. `LLMAPIErrors`
    3. `LLMParseFailureSpike`
    4. `ThrottleQueueSaturation`
    5. `EvidenceQualityDrop`
    6. `LLMTokenRateTooHigh`
    7. `EmbeddingColdStartHigh`
    8. `CircuitBreakerOpen`
- **Evidence:** `infra/prometheus/rules/sre_agent_slo.yaml` — two groups: `sre_agent_recording_rules` (1 recording rule) and `sre_agent_slo_alerts` (8 alert rules).
- **Status:** CONFIRMED

---

### Check 3: Azure Restart Verification
- **Finding:** Both `app_service_operator.py` and `functions_operator.py` are FIRE-AND-FORGET. There is NO polling for completion. The restart call is synchronous on the Azure SDK side (`self._web.web_apps.restart(...)`) but no status polling loop follows it.
- **Evidence (AppServiceOperator):**
  ```python
  async def _do_restart() -> dict[str, Any]:
      logger.info("app_service_restart", app=app_name, rg=resource_group)
      try:
          self._web.web_apps.restart(resource_group, app_name)
      except _AZURE_ERRORS as exc:
          raise map_azure_error(exc) from exc
      return {"action": "restart", "app": app_name, "resource_group": resource_group}
  ```
  (src/sre_agent/adapters/cloud/azure/app_service_operator.py, lines ~69-77)
- **Evidence (FunctionsOperator):**
  ```python
  async def _do_restart() -> dict[str, Any]:
      logger.info("functions_restart", app=app_name, rg=resource_group)
      try:
          self._web.web_apps.restart(resource_group, app_name)
      except _AZURE_ERRORS as exc:
          raise map_azure_error(exc) from exc
      return {"action": "restart", "function_app": app_name}
  ```
  (src/sre_agent/adapters/cloud/azure/functions_operator.py, lines ~69-76)
- **Status:** CONFIRMED — fire-and-forget (no completion polling)

---

### Check 4: Cooldown Implementation
- **Finding:** Cooldown state is stored IN-MEMORY only (a Python dict `self._cooldowns: dict[str, float]`). It is NOT backed by Redis or etcd.
- **Evidence:**
  ```python
  class CooldownEnforcer:
      def __init__(self, audit: CoordinationAuditPort | None = None) -> None:
          self._cooldowns: dict[str, float] = {}
          self._audit = audit
  ```
  And in `record_action()`:
  ```python
  self._cooldowns[key] = time.time() + ttl_seconds
  ```
  (src/sre_agent/domain/safety/cooldown.py, lines 19-22 and line 39)
- **Note:** The audit events ARE written durably via `CoordinationAuditPort`, but the cooldown gate itself is volatile (in-process memory). A process restart clears all active cooldowns.
- **Status:** CONFIRMED — in-memory only

---

### Check 5: Helm Chart Directory
- **Finding:** The `charts/` directory does NOT exist in the workspace.
- **Evidence:** `file_search` for `charts/` returned no results.
- **Status:** NOT FOUND

---

### Check 6: Datadog Adapter Directory
- **Finding:** The `src/sre_agent/adapters/telemetry/datadog/` directory does NOT exist.
- **Evidence:** `file_search` returned no results; `tests/unit/adapters/telemetry/` contains only `kubernetes/`, `newrelic/`, and `test_fallback_log_adapter.py`.
- **Status:** NOT FOUND

---

### Check 7: GCP Support
- **Finding:** The `src/sre_agent/adapters/cloud/gcp/` directory does NOT exist.
- **Evidence:** `file_search` for `src/sre_agent/adapters/cloud/gcp/` returned no results.
- **Status:** NOT FOUND

---

### Check 8: Slow Response Detection
- **Finding:** Neither `SLOW_RESPONSE` nor `TIMEOUT_PROXIMITY` are defined in the codebase. The `AnomalyType` enum in `canonical.py` defines 9 values, none of which match those names.
- **Evidence — AnomalyType enum (canonical.py lines 56-69):**
  ```python
  class AnomalyType(Enum):
      LATENCY_SPIKE = "latency_spike"
      ERROR_RATE_SURGE = "error_rate_surge"
      MEMORY_PRESSURE = "memory_pressure"
      DISK_EXHAUSTION = "disk_exhaustion"
      CERTIFICATE_EXPIRY = "certificate_expiry"
      MULTI_DIMENSIONAL = "multi_dimensional"
      DEPLOYMENT_INDUCED = "deployment_induced"
      INVOCATION_ERROR_SURGE = "invocation_error_surge"
      TRAFFIC_ANOMALY = "traffic_anomaly"
  ```
- **Detection directory** (`src/sre_agent/domain/detection/`) contains: alert_correlation.py, anomaly_detector.py, baseline.py, cloud_operator_registry.py, dependency_graph.py, health_monitor.py, late_data_handler.py, pipeline_monitor.py, polling_agent.py, provider_health.py, provider_registry.py, signal_correlator.py — no `slow_response` or `timeout_proximity` module.
- **Status:** MISSING — these AnomalyTypes are not implemented

---

### Check 9: Notification Adapters
- **Finding:** The `src/sre_agent/adapters/notifications/` directory does NOT exist. No Slack or PagerDuty integration code was found in the codebase.
- **Evidence:** `file_search` returned no results; grep for "slack|pagerduty" returned no matches.
- **Status:** NOT FOUND

---

### Check 10: Persistence Domain Models
- **Finding:** The file EXISTS and is fully implemented with Pydantic v2 models.
  - Defines `IncidentStatus` StrEnum (5 states: open, investigating, mitigating, resolved, closed)
  - Defines `RemediationStatus` StrEnum (6 states: planned, approved, running, completed, failed, rolled_back)
  - Defines `OutboxStatus` StrEnum (3 states: pending, sent, failed)
  - Defines state machine transition maps for each enum
  - Docstring: "Implements: Phase 4.0 Persistence Architecture Reconciliation"
- **Evidence:** `src/sre_agent/domain/models/persistence.py` lines 1-100+ fully implemented.
- **Status:** CONFIRMED

---

### Check 11: ADR-006
- **Finding:** The file EXISTS at `docs/project/ADRs/006-persistence-authority-reconciliation.md`.
- **Evidence:** `file_search` returned exactly 1 result matching this path.
- **Status:** CONFIRMED

---

### Check 12: Observability Metrics Count
- **Finding:** 19 metric instances defined (18 exported + 1 internal context var). The `__all__` list contains 20 symbols total (19 metrics + `_current_alert_id`).
- **Metric names:**
  1. `sre_agent_diagnosis_duration_seconds` (DIAGNOSIS_DURATION — Histogram)
  2. `sre_agent_diagnosis_errors_total` (DIAGNOSIS_ERRORS — Counter)
  3. `sre_agent_severity_assigned_total` (SEVERITY_ASSIGNED — Counter)
  4. `sre_agent_evidence_relevance_score` (EVIDENCE_RELEVANCE — Histogram)
  5. `sre_agent_llm_call_duration_seconds` (LLM_CALL_DURATION — Histogram)
  6. `sre_agent_llm_tokens_total` (LLM_TOKENS_USED — Counter)
  7. `sre_agent_llm_parse_failures_total` (LLM_PARSE_FAILURES — Counter)
  8. `sre_agent_llm_queue_depth` (LLM_QUEUE_DEPTH — Gauge)
  9. `sre_agent_llm_queue_wait_seconds` (LLM_QUEUE_WAIT — Histogram)
  10. `sre_agent_vector_fallback_truncated_total` (VECTOR_FALLBACK_TRUNCATED — Counter)
  11. `sre_agent_outbox_pending_rows` (OUTBOX_PENDING_ROWS — Gauge)
  12. `sre_agent_outbox_dlq_rows` (OUTBOX_DLQ_ROWS — Gauge)
  13. `sre_agent_db_query_duration_seconds` (DB_QUERY_DURATION — Histogram)
  14. `sre_agent_db_pool_active_connections` (DB_POOL_ACTIVE_CONNECTIONS — Gauge)
  15. `sre_agent_redis_stream_lag` (REDIS_STREAM_LAG — Gauge)
  16. `sre_agent_vector_mode` (VECTOR_MODE — Gauge)
  17. `sre_agent_embedding_duration_seconds` (EMBEDDING_DURATION — Histogram)
  18. `sre_agent_embedding_cold_start_seconds` (EMBEDDING_COLD_START — Gauge)
  19. `sre_agent_circuit_breaker_state` (CIRCUIT_BREAKER_STATE — Gauge)
- **Evidence:** `src/sre_agent/observability/metrics.py` — full file read.
- **Status:** CONFIRMED — 19 metrics total

---

### Check 13: Kill Switch
- **Finding:** Kill-switch state is stored IN-MEMORY ONLY. It is NOT Redis-backed or durable. A process restart resets `_active = False`.
- **Evidence:**
  ```python
  class KillSwitch:
      """In-memory kill switch state for autonomous action gating."""

      def __init__(
          self, event_bus: EventBus | None = None, event_store: EventStore | None = None
      ) -> None:
          self._active = False
          ...
  ```
  (src/sre_agent/domain/safety/kill_switch.py, lines 8-17)
- **Note:** Activate/deactivate events ARE published to the EventBus and EventStore, but the boolean gate itself is in-memory. After restart, the agent does NOT re-hydrate kill-switch state from the event store.
- **Status:** CONFIRMED — in-memory only (no Redis)

---

### Check 14: Tests Coverage
**Unit tests** (`tests/unit/`):
- `__init__.py`, `conftest.py`
- `adapters/`: coordination/, events/, persistence/, telemetry/, vectordb/ + individual files: test_anthropic_llm_adapter.py, test_aws_error_mapper.py, test_aws_operators.py, test_azure_error_mapper.py, test_azure_operators.py, test_bootstrap.py, test_cloud_operator_registry.py, test_cloudwatch_log_group_resolver.py, test_cloudwatch_logs_adapter.py, test_cloudwatch_metrics_adapter.py, test_cloudwatch_provider.py, test_ebpf_adapter.py, test_enrichment.py, test_events_router.py, test_intelligence_bootstrap.py, test_kubernetes_operator.py, test_metrics.py, test_newrelic_adapter.py, test_openai_llm_adapter.py, test_otel_adapters.py, test_prometheus_rules.py, test_resilience.py, test_resource_metadata.py, test_sentence_transformers_adapter.py, test_throttled_llm_adapter.py, test_xray_adapter.py
  - `coordination/`: test_etcd_fencing_token.py
  - `events/`: test_redis_streams_event_bus.py
  - `persistence/`: test_coordination_store.py, test_event_store.py, test_incident_store.py, test_outbox_relay.py, test_postgres_outbox.py, test_reasoning_trace_store.py, test_remediation_store.py, test_retention_executor.py
  - `telemetry/`: test_fallback_log_adapter.py + kubernetes/, newrelic/
  - `vectordb/`: test_pgvector_adapter.py
- `api/`, `config/`
- `domain/`: test_canonical.py, test_confidence_scorer.py, test_dependency_graph.py, test_detection.py, test_detection_config.py, test_diagnosis_models.py, test_distributed_lock_manager.py, test_ebpf_degradation.py, test_health_monitor.py, test_hexagonal_boundaries.py, test_ingestion.py, test_integration.py, test_persistence_models.py, test_pipeline_observability.py, test_polling_agent.py, test_provider_health.py, test_provider_registry.py, test_rag_pipeline.py, test_rag_pipeline_events.py, test_rag_pipeline_hardening.py, test_rag_pipeline_reasoning_trace.py, test_remediation_engine.py, test_remediation_logic.py, test_remediation_models.py, test_remediation_planner.py, test_safety_cooldown.py, test_safety_guardrails.py, test_serverless_detection.py, test_severity_classifier.py, test_signal_correlator.py, test_timeline_constructor.py, test_token_optimization.py, test_validator.py
- `events/`: test_in_memory_event_bus.py
- `ports/`: test_port_abstract_methods.py

**Integration tests** (`tests/integration/`):
- test_aws_operators_integration.py, test_chaos_specs.py, test_chroma_integration.py, test_cloudwatch_bootstrap.py, test_cloudwatch_integration.py, test_cloudwatch_live_integration.py, test_etcd_lock_manager_integration.py, test_event_sourcing_integration.py, test_iam_specs.py, test_incident_store_integration.py, test_lock_contention_stress.py, test_otel_adapters_integration.py, test_pod_specs.py, test_rag_pipeline_integration.py, test_redis_lock_manager_integration.py, test_schema_migration_008_009_integration.py
- **Status:** CONFIRMED — extensive coverage in both unit and integration

---

## Unexpected Findings

1. **Cooldown + Kill Switch are both in-memory**: Neither `CooldownEnforcer` nor `KillSwitch` survives a process restart. This is a significant operational gap — a pod restart clears all active cooldowns and resets the kill-switch state. The audit trail is durable but the enforcement gate is not.

2. **Azure restart is truly fire-and-forget**: Both Azure adapters call `self._web.web_apps.restart()` synchronously via the mgmt SDK but do not poll for the app to return to Running state. No health-check loop after restart.

3. **No Helm charts**: No Kubernetes deployment manifests via Helm are present. Only raw k8s YAML under `infra/k8s/`.

4. **No Datadog, no GCP, no notifications**: Three commonly expected extension points are absent from the codebase. No Slack/PagerDuty alerting integrations exist.

5. **SLOW_RESPONSE / TIMEOUT_PROXIMITY missing**: The AnomalyType enum has 9 types but neither slow-response nor timeout-proximity detection exists. Latency is covered by `LATENCY_SPIKE` only.

6. **Persistence models file is separate from port**: `domain/models/persistence.py` (Pydantic value objects + StrEnums) is distinct from `ports/persistence.py` (ABCs). This is architecturally clean — domain models don't reference ports.

---

## Clarifying Questions
None — all 14 verification tasks have definitive answers from code inspection.
