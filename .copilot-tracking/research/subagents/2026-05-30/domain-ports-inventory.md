# Domain and Ports Layer Inventory
**Date:** 2026-05-30
**Status:** Complete
**Researcher:** Subagent

---

## Research Questions

1. What classes, functions, and models exist in `domain/` and `ports/`?
2. What are their exact signatures, fields, and behaviors?
3. Are any spec-required features missing or incomplete?

---

## Ports Layer (`src/sre_agent/ports/`)

### `ports/cloud_operator.py`
**Purpose:** Provider-agnostic remediation interface.

**Class: `CloudOperatorPort` (ABC)**
| Method | Signature | Notes |
|---|---|---|
| `provider_name` (property) | `-> str` | Abstract |
| `supported_mechanisms` (property) | `-> list[ComputeMechanism]` | Abstract |
| `restart_compute_unit` | `async (resource_id: str, metadata: dict | None) -> dict` | Abstract |
| `scale_capacity` | `async (resource_id: str, desired_count: int, metadata: dict | None) -> dict` | Abstract |
| `is_action_supported` | `(action: str, compute_mechanism: ComputeMechanism) -> bool` | Concrete; checks supported_mechanisms |
| `health_check` | `async () -> bool` | Abstract |

**Spec alignment:** ✅ Full Phase 1.5 interface present with `ComputeMechanism` support.

---

### `ports/telemetry.py`
**Purpose:** Provider-agnostic telemetry query interfaces.

**Class: `BaselineQuery` (ABC)**
| Method | Signature |
|---|---|
| `get_baseline` | `(service: str, metric: str, timestamp: datetime | None) -> Any` |
| `compute_deviation` | `(service, metric, value: float, timestamp) -> tuple[float, Any]` |
| `ingest` | `async (service, metric, value: float, timestamp: datetime) -> Any` |

**Class: `MetricsQuery` (ABC)**
| Method | Signature |
|---|---|
| `query` | `async (service, metric, start_time, end_time, labels, step_seconds) -> list[CanonicalMetric]` |
| `query_instant` | `async (service, metric, timestamp, labels) -> CanonicalMetric | None` |
| `list_metrics` | `async (service: str) -> list[str]` |

**Class: `TraceQuery` (ABC)**
| Method | Signature |
|---|---|
| `get_trace` | `async (trace_id: str) -> CanonicalTrace | None` |
| `query_traces` | `async (service, start_time, end_time, limit, min_duration_ms, status_code) -> list[CanonicalTrace]` |

**Class: `LogQuery` (ABC)**
| Method | Signature |
|---|---|
| `query_logs` | `async (service, start_time, end_time, severity, trace_id, search_text, limit) -> list[CanonicalLogEntry]` |
| `query_by_trace_id` | `async (trace_id, start_time, end_time) -> list[CanonicalLogEntry]` |

**Class: `DependencyGraphQuery` (ABC)**
| Method | Signature |
|---|---|
| `get_graph` | `async () -> ServiceGraph` |
| `get_service_dependencies` | `async (service, include_transitive) -> ServiceGraph` |
| `get_service_health` | `async (service) -> dict[str, Any]` |

**Class: `eBPFQuery` (ABC)**
| Method | Signature |
|---|---|
| `get_syscall_activity` | `async (pod, namespace, start_time, end_time, syscall_types) -> list[Any]` |
| `get_network_flows` | `async (service, namespace, start_time, end_time) -> list[Any]` |
| `get_process_activity` | `async (pod, namespace, start_time, end_time) -> list[Any]` |
| `health_check` | `async () -> bool` |
| `get_node_status` | `async () -> list[dict[str, Any]]` |
| `is_supported` | `(compute_mechanism: ComputeMechanism) -> bool` — **CONCRETE** (returns True for KUBERNETES, VIRTUAL_MACHINE; False for SERVERLESS, CONTAINER_INSTANCE) |

**Class: `TelemetryProvider` (ABC)**
| Property | Type |
|---|---|
| `name` | `str` |
| `metrics` | `MetricsQuery` |
| `traces` | `TraceQuery` |
| `logs` | `LogQuery` |
| `dependency_graph` | `DependencyGraphQuery` |

**Spec alignment:** ✅ `eBPFQuery.is_supported(compute_mechanism)` is implemented and correctly returns True only for KUBERNETES and VIRTUAL_MACHINE.

---

### `ports/llm.py`
**Purpose:** Provider-agnostic LLM reasoning interface.

**Enums/Dataclasses:**
- `LLMProvider`: `OPENAI`, `ANTHROPIC`
- `LLMConfig`: `provider`, `model_name`, `max_tokens`, `temperature`, `context_budget`, `timeout_seconds`
- `EvidenceContext`: `content`, `source`, `relevance_score`
- `HypothesisRequest`: `alert_description`, `service_name`, `timeline`, `evidence`, `system_context`, `priority`
- `Hypothesis`: `root_cause`, `confidence`, `reasoning`, `evidence_citations`, `suggested_remediation`
- `ValidationRequest`: `hypothesis`, `original_evidence`, `alert_description`
- `ValidationResult`: `agrees`, `confidence`, `reasoning`, `contradictions`, `corrected_root_cause`, `corrected_remediation`
- `TokenUsage`: `prompt_tokens`, `completion_tokens`, `total_tokens` (property), `add()`

**Class: `LLMReasoningPort` (ABC)**
| Method | Signature |
|---|---|
| `generate_hypothesis` | `async (request: HypothesisRequest) -> Hypothesis` |
| `validate_hypothesis` | `async (request: ValidationRequest) -> ValidationResult` |
| `count_tokens` | `(text: str) -> int` |
| `get_token_usage` | `() -> TokenUsage` |
| `health_check` | `async () -> bool` |

---

### `ports/embedding.py`
**Purpose:** Provider-agnostic text embedding interface.

**Dataclass:** `EmbeddingConfig`: `model_name`, `dimensions`, `batch_size`, `normalize`

**Class: `EmbeddingPort` (ABC)**
| Method | Signature |
|---|---|
| `embed_text` | `async (text: str) -> list[float]` |
| `embed_batch` | `async (texts: list[str]) -> list[list[float]]` |
| `get_dimensions` | `() -> int` |
| `health_check` | `async () -> bool` |

---

### `ports/vector_store.py`
**Purpose:** Provider-agnostic vector database interface.

**Enum:** `DistanceMetric`: `COSINE`, `EUCLIDEAN`, `DOT_PRODUCT`
**Dataclass:** `SearchQuery`: `embedding`, `top_k`, `min_score`, `metadata_filter`
**Re-exports:** `VectorDocument`, `SearchResult` (from `domain.models.vector`)

**Class: `VectorStorePort` (ABC)**
| Method | Signature |
|---|---|
| `store` | `async (document: VectorDocument) -> None` |
| `store_batch` | `async (documents: list[VectorDocument]) -> int` |
| `search` | `async (query: SearchQuery) -> list[SearchResult]` |
| `delete` | `async (doc_id: str) -> bool` |
| `delete_stale` | `async (older_than: datetime) -> int` |
| `count` | `async () -> int` |
| `health_check` | `async () -> bool` |

---

### `ports/events.py`
**Purpose:** Domain event publishing and subscription interface.

**Type alias:** `EventHandler = Callable[[DomainEvent], Awaitable[None]]`

**Class: `EventBus` (ABC)**
| Method | Signature |
|---|---|
| `publish` | `async (event: DomainEvent) -> None` |
| `subscribe` | `async (event_type: str, handler: EventHandler) -> None` |
| `unsubscribe` | `async (event_type: str, handler: EventHandler) -> None` |
| `start` | `async (task_group: anyio.abc.TaskGroup) -> None` — concrete no-op hook |

**Class: `EventStore` (ABC)**
| Method | Signature |
|---|---|
| `append` | `async (event: DomainEvent) -> None` |
| `get_events` | `async (aggregate_id: str, event_types: list[str] | None) -> list[DomainEvent]` |

---

### `ports/diagnostics.py`
**Purpose:** Provider-agnostic incident diagnosis interface.

**Dataclasses:**
- `DiagnosisRequest`: `alert`, `correlated_signals`, `service_tier`, `max_evidence_items`
- `DiagnosisResult`: `root_cause`, `confidence`, `severity`, `reasoning`, `evidence_citations`, `suggested_remediation`, `is_novel`, `requires_human_approval`, `diagnosed_at`, `audit_trail`

**Class: `DiagnosticPort` (ABC)**
| Method | Signature |
|---|---|
| `diagnose` | `async (request: DiagnosisRequest) -> DiagnosisResult` |
| `health_check` | `async () -> bool` |

---

### `ports/lock_manager.py`
**Purpose:** Distributed lock manager for multi-agent coordination.

**Dataclasses:**
- `LockRequest`: `agent_id`, `resource_type`, `resource_name`, `namespace`, `compute_mechanism`, `resource_id`, `provider`, `priority_level`, `ttl_seconds`
- `LockResult`: `granted`, `lock_key`, `fencing_token`, `holder_agent_id`, `preempted`, `reason`

**Class: `DistributedLockManagerPort` (ABC)**
| Method | Signature |
|---|---|
| `acquire_lock` | `async (request: LockRequest) -> LockResult` |
| `release_lock` | `async (lock_key, agent_id, fencing_token) -> bool` |
| `is_lock_valid` | `async (lock_key, agent_id, fencing_token: int) -> bool` |

---

### `ports/persistence.py`
**Purpose:** Persistence abstraction for incident, diagnosis, remediation, outbox, coordination audit, and reasoning traces.

**Exceptions:** `DuplicateEventError`, `StaleProjectionError`

**Dataclasses (DTOs):**
- `LockAuditEntry`: `actor_type`, `actor_id`, `action`, `provider`, `compute_mechanism`, `resource_id`, `lock_priority`, `fencing_token`, `details`
- `CooldownAuditEntry`: `actor_type`, `actor_id`, `action`, `provider`, `compute_mechanism`, `resource_id`, `details`
- `OverrideAuditEntry`: `actor_type`, `actor_id`, `action`, `provider`, `compute_mechanism`, `resource_id`, `audit_required`, `details`
- `CoordinationAuditRecord`: `audit_id`, `actor_type`, `actor_id`, `action`, `provider`, `compute_mechanism`, `resource_id`, `lock_priority`, `fencing_token`, `created_at`, `details_json`
- `IncidentEventRecord`: `event_id`, `incident_id`, `event_type`, `occurred_at`, `provider`, `compute_mechanism`, `resource_id`, `payload_json`, `idempotency_key`, `correlation_key`
- `IncidentRecord`: `incident_id`, `service`, `severity`, `status`, `opened_at`, `updated_at`, `closed_at`, `latest_event_id`, `provider`, `compute_mechanism`, `resource_id`
- `DiagnosisResultRecord`: `diagnosis_id`, `incident_id`, `diagnosis_summary`, `confidence_score`, `evidence_refs`, `generated_at`, `model_name`
- `ReasoningRunRecord`: `run_id`, `incident_id`, `agent_id`, `started_at`, `ended_at`, `outcome`, `metadata_json`
- `ToolCallTraceRecord`: `call_id`, `run_id`, `tool_name`, `input_json`, `output_json`, `latency_ms`, `status`, `called_at`
- `RetrievedContextRecord`: `context_id`, `run_id`, `doc_id`, `similarity_score`, `content_snippet`, `source`, `retrieved_at`
- `RemediationActionRecord`: `action_id`, `incident_id`, `action_type`, `action_status`, `approval_mode`, `requested_at`, `started_at`, `completed_at`, `rollback_action_id`, `execution_result`

**Constant:** `REMEDIATION_DB_STATUSES` (frozenset of allowed DB status strings)

**Abstract Port Classes:**
- `CoordinationAuditPort`: `record_lock_event`, `record_cooldown_event`, `record_override_event`, `get_audit_trail`
- `IncidentStorePort`: `save_event`, `get_events_by_incident`, `get_incident`, `update_projection`
- `OutboxPort`: `enqueue`, `mark_sent`, `mark_dlq`, `mark_failed`, `is_event_processed`, `mark_event_processed`, `get_pending`, `claim_pending`, `release_claim`, `increment_retry`
- `DiagnosisStorePort`: `save_diagnosis`
- `ReasoningTracePort`: `start_run`, `end_run`, `log_tool_call`, `log_retrieved_context`, `get_run`, `list_runs_by_incident`, `list_tool_calls`, `list_retrieved_contexts`
- `RemediationStorePort`: `save_action`, `update_status`, `get_by_incident`

---

### `ports/reranker.py`
**Purpose:** Cross-encoder reranking of vector search results.

**Dataclass:** `RankedDocument`: `content`, `source`, `original_score`, `rerank_score`, `doc_id`

**Class: `RerankerPort` (ABC)**
| Method | Signature |
|---|---|
| `rerank` | `(query: str, documents: list[dict], top_k: int) -> list[RankedDocument]` |

---

### `ports/compressor.py`
**Purpose:** Text compression to reduce LLM token usage.

**Dataclass:** `CompressionResult`: `original_text`, `compressed_text`, `original_tokens`, `compressed_tokens`, `compression_ratio`

**Class: `CompressorPort` (ABC)**
| Method | Signature |
|---|---|
| `compress` | `(text: str, target_ratio: float, instruction: str) -> CompressionResult` |
| `compress_batch` | `(texts: list[str], target_ratio: float) -> list[CompressionResult]` |

---

### `ports/remediation.py`
**Purpose:** Provider-agnostic remediation workflow interface.

**Class: `RemediationPort` (ABC)**
| Method | Signature |
|---|---|
| `create_plan` | `async (diagnosis: Diagnosis, alert: AnomalyAlert) -> RemediationPlan` |
| `execute_action` | `async (action: RemediationAction) -> RemediationResult` |
| `verify_outcome` | `async (action: RemediationAction) -> VerificationStatus` |
| `rollback_action` | `async (action: RemediationAction) -> RemediationResult` |

---

## Domain Models Layer (`src/sre_agent/domain/models/`)

### `domain/models/canonical.py`
**Purpose:** Provider-independent canonical data types.

**Enums:**
- `SignalType`: `METRIC`, `TRACE`, `LOG`, `EBPF_EVENT`
- `DataQuality`: `HIGH`, `LOW`, `INCOMPLETE`, `LATE`
- `Severity`: `SEV1=1`, `SEV2=2`, `SEV3=3`, `SEV4=4`
- `AnomalyType`: `LATENCY_SPIKE`, `ERROR_RATE_SURGE`, `MEMORY_PRESSURE`, `DISK_EXHAUSTION`, `CERTIFICATE_EXPIRY`, `MULTI_DIMENSIONAL`, `DEPLOYMENT_INDUCED`, `INVOCATION_ERROR_SURGE`, `TRAFFIC_ANOMALY`
- `IncidentPhase`: `DETECTED`, `CLASSIFIED`, `DIAGNOSING`, `DIAGNOSED`, `VALIDATING`, `AUTHORIZING`, `REMEDIATING`, `VERIFYING`, `RESOLVED`, `ESCALATED`, `FAILED`
- `OperationalPhase`: `OBSERVE`, `ASSIST`, `AUTONOMOUS`, `PREDICTIVE`
- `ComputeMechanism`: `KUBERNETES`, `SERVERLESS`, `VIRTUAL_MACHINE`, `CONTAINER_INSTANCE`

**Pydantic Models:**

`ServiceLabels` (frozen):
- `service: str`
- `namespace: str = ""`
- `compute_mechanism: ComputeMechanism = KUBERNETES`
- `resource_id: str = ""`
- `pod: str = ""`
- `node: str = ""`
- `platform_metadata: dict[str, Any] = {}`
- `extra: dict[str, str] = {}`

`CanonicalMetric`:
- `name`, `value`, `timestamp`, `labels: ServiceLabels`, `unit`, `quality`, `provider_source`, `ingestion_timestamp`
- Property: `is_low_quality`

`TraceSpan`:
- `span_id`, `parent_span_id`, `service`, `operation`, `duration_ms`, `status_code`, `error`, `attributes`, `start_time`, `end_time`

`CanonicalTrace`:
- `trace_id`, `spans`, `is_complete`, `missing_services`, `quality`, `provider_source`, `ingestion_timestamp`
- Properties: `root_span`, `duration_ms`, `services_involved`

`CanonicalLogEntry`:
- `timestamp`, `message`, `severity`, `labels`, `trace_id`, `span_id`, `attributes`, `quality`, `provider_source`, `ingestion_timestamp`

`CanonicalEvent`:
- `event_type`, `source`, `timestamp`, `metadata`, `labels`, `quality`, `provider_source`, `ingestion_timestamp`

`ServiceNode` (frozen):
- `service`, `version`, `namespace`, **`compute_mechanism: ComputeMechanism = KUBERNETES`**, `tier: int = 3`, `is_healthy: bool = True`

`ServiceEdge` (frozen):
- `source`, `target`, `protocol`, `avg_latency_ms`, `error_rate`

`ServiceGraph`:
- `nodes: dict[str, ServiceNode]`, `edges: list[ServiceEdge]`, `last_updated`
- Methods: `get_upstream`, `get_downstream`, `get_transitive_downstream`

`CorrelatedSignals`:
- `service`, `namespace`, `time_window_start`, `time_window_end`
- **`compute_mechanism: ComputeMechanism = KUBERNETES`** ✅
- `metrics`, `traces`, `logs`, `events`
- **`has_degraded_observability: bool = False`** ✅
- `degradation_reason: str | None`

`AnomalyAlert`:
- `alert_id`, `anomaly_type`, `service`, `namespace`
- `resource_id: str = ""`
- **`compute_mechanism: ComputeMechanism = KUBERNETES`** ✅
- `severity`, `timestamp`, `metric_name`, `current_value`, `baseline_value`, `deviation_sigma`, `description`, `blast_radius_ratio`
- `correlated_incident_id`, `is_deployment_induced`, `deployment_details`
- `correlated_signals`, `related_alerts`
- `detected_at`, `alert_generated_at`

`DomainEvent`:
- `event_id`, `timestamp`, `event_type`, `aggregate_id`, `payload`
- Property: `is_valid`

`EventTypes` (class with constants):
- Phase 1: `ANOMALY_DETECTED`, `ANOMALY_CORRELATED`, `ALERT_SUPPRESSED`, `OBSERVABILITY_DEGRADED`, `PROVIDER_HEALTH_CHANGED`, `DEPENDENCY_GRAPH_UPDATED`, `BASELINE_UPDATED`, `INCIDENT_CREATED`
- Phase 2: `INCIDENT_DETECTED`, `DIAGNOSIS_GENERATED`, `SECOND_OPINION_COMPLETED`, `SEVERITY_ASSIGNED`, `REMEDIATION_PLANNED`, `REMEDIATION_APPROVED`, `REMEDIATION_STARTED`, `REMEDIATION_COMPLETED`, `REMEDIATION_FAILED`, `REMEDIATION_ROLLED_BACK`
- Safety: `KILL_SWITCH_ACTIVATED`, `KILL_SWITCH_DEACTIVATED`, `BLAST_RADIUS_EXCEEDED`, `COOLDOWN_ENFORCED`, `PHASE_GATE_EVALUATED`

---

### `domain/models/diagnosis.py`
**Purpose:** Intelligence layer data types for diagnosis.

**Enums/Classes:**
- `ServiceTier (IntEnum)`: `TIER_1=1` through `TIER_4=4`
- `DiagnosticState (IntEnum)`: `PENDING=0` through `ROOT_CAUSE_UNRESOLVED=10`

`ConfidenceLevel` (frozen Pydantic):
- `BLOCK_THRESHOLD: float = 0.70`
- `PROPOSE_THRESHOLD: float = 0.85`
- Static method: `from_score(score: float) -> str` → `"BLOCK" | "PROPOSE" | "AUTONOMOUS"`

`EvidenceCitation` (frozen Pydantic):
- `source`, `content_snippet`, `relevance_score`, `doc_id`
- Validates: `0 <= relevance_score <= 1`

`ImpactDimensions` (Pydantic):
- `user_impact`, `service_tier_score`, `blast_radius`, `financial_impact`, `reversibility`
- `compute_severity_score() -> float` — weighted formula
- `to_severity() -> Severity` — thresholds at 0.75, 0.50, 0.25

`Diagnosis` (Pydantic):
- `diagnosis_id`, `alert_id`, `service`, `root_cause`, `confidence`, `severity`, `reasoning`, `evidence_citations`, `impact`, `suggested_remediation`, `is_novel`, `state`, `diagnosed_at`, `audit_entries`
- Properties: `confidence_level`, `requires_human_approval` (SEV1/2 always require approval; below AUTONOMOUS threshold requires approval)

`AuditEntry` (frozen Pydantic):
- `stage`, `action`, `timestamp`, `details`

---

### `domain/models/detection_config.py`
**Purpose:** Domain-owned detection configuration value object.

**Class: `DetectionConfig` (Pydantic BaseModel)**
| Field | Default | Notes |
|---|---|---|
| `latency_sigma_threshold` | `3.0` | |
| `latency_duration_minutes` | `2` | |
| `error_rate_surge_percent` | `200.0` | |
| `memory_pressure_percent` | `85.0` | |
| `memory_pressure_duration_minutes` | `5` | |
| `disk_exhaustion_percent` | `80.0` | |
| `disk_projection_hours` | `24` | |
| `cert_expiry_warning_days` | `14` | |
| `cert_expiry_critical_days` | `3` | |
| `deployment_correlation_window_minutes` | `60` | |
| `suppression_window_seconds` | `30` | |
| **`cold_start_suppression_window_seconds`** | **`15`** | **Phase 1.5 AC-1.5.3** |
| `multi_dim_latency_percent` | `50.0` | |
| `multi_dim_error_percent` | `80.0` | |
| `multi_dim_window_minutes` | `5` | |

---

### `domain/models/persistence.py`
**Purpose:** Domain models for persistence state machines.

**Enums (StrEnum):**
- `IncidentStatus`: `OPEN`, `INVESTIGATING`, `MITIGATING`, `RESOLVED`, `CLOSED`
- `RemediationStatus`: `PLANNED`, `APPROVED`, `RUNNING`, `COMPLETED`, `FAILED`, `ROLLED_BACK`
- `OutboxStatus`: `PENDING`, `SENT`, `FAILED`
- `ComputeMechanismToken`: `KUBERNETES`, `SERVERLESS`, `VIRTUAL_MACHINE`, `CONTAINER_INSTANCE`
- `ProviderToken`: `KUBERNETES`, `AWS`, `AZURE`
- Transition maps: `INCIDENT_STATUS_TRANSITIONS`, `REMEDIATION_STATUS_TRANSITIONS`, `OUTBOX_STATUS_TRANSITIONS`

**Pydantic Models:**
- `IncidentEvent` (frozen): `event_id`, `incident_id`, `event_type`, `occurred_at`, `provider`, `compute_mechanism`, `resource_id`, `payload_json`, `idempotency_key`, `correlation_key` — validated against `ComputeMechanismToken` and `ProviderToken`
- `Incident` (mutable): full projection model with `previous_status` → validates transition via `INCIDENT_STATUS_TRANSITIONS`
- `DiagnosisResult` (frozen): `diagnosis_id`, `incident_id`, `diagnosis_summary` (truncated — more fields continue past read window)

---

### `domain/models/vector.py`
**Purpose:** Domain models for vector store.

**Pydantic Models:**
- `VectorDocument` (frozen): `doc_id`, `content`, `embedding: list[float]`, `metadata`, `source`, `created_at`
- `SearchResult` (frozen): `doc_id`, `content`, `score`, `metadata`, `source`

---

## Domain Detection Layer (`src/sre_agent/domain/detection/`)

### `domain/detection/anomaly_detector.py`
**Purpose:** ML-based anomaly detection with multi-type support.

**Dataclasses:**
- `DeploymentRecord`: `service`, `timestamp`, `commit_sha`, `deployer`, `metadata`
- `DetectionResult`: `alerts`, `suppressed_count`, `checked_count`

**Class: `AnomalyDetector`**
Constructor: `(baseline_service: BaselineQuery, config: DetectionConfig, event_bus: EventBus | None)`

Key state: `_active_conditions`, `_recent_deployments`, `_suppression_windows`, `_sub_threshold_shifts`, `_service_overrides`, `_metric_overrides`, `_cold_start_init_times`

| Method | Notes |
|---|---|
| `detect(service, metrics, namespace, compute_mechanism)` | Main detection entry point; dispatches to sub-detectors |
| `_evaluate_metric(service, metric, namespace, compute_mechanism)` | Routes to specific detector |
| `_detect_latency_spike(...)` | AC-3.1.2 — Phase 1.5: cold-start suppression for SERVERLESS |
| `_detect_error_surge(...)` | AC-3.1.3 — >200% increase |
| `_detect_memory_pressure(...)` | AC-3.1.4 — exempt for SERVERLESS |
| `_detect_invocation_error_surge(...)` | Phase 1.5 — INVOCATION_ERROR_SURGE for serverless |
| `_detect_disk_exhaustion(...)` | AC-3.1.5 |
| `_detect_cert_expiry(...)` | AC-3.1.6 |
| `_detect_sigma_deviation(...)` | General sigma-based |
| `_check_multi_dimensional(service, namespace)` | AC-3.2.3 |
| `register_deployment(service, timestamp, commit_sha, deployer)` | AC-3.3.1/3.3.2 |
| `_should_suppress(service, timestamp)` | AC-3.4.1/3.4.2 |
| `_get_effective_sigma(service, metric_name)` | AC-3.5.1/3.5.2 — per-service/metric overrides |
| `set_service_override(service, sigma)` | AC-3.5.1 |
| `set_metric_override(pattern, sigma)` | AC-3.5.2 |

**Phase 1.5 specifics:**
- **Cold-start suppression (15s window):** ✅ Implemented in `_detect_latency_spike` via `_cold_start_init_times`. Uses `config.cold_start_suppression_window_seconds = 15`.
- **SERVERLESS memory-pressure exemption:** ✅ Implemented in `_evaluate_metric` — skips `_detect_memory_pressure` when `compute_mechanism == SERVERLESS`.
- **InvocationError surge monitoring:** ✅ Implemented as `_detect_invocation_error_surge` (AnomalyType.INVOCATION_ERROR_SURGE), routed via `"invocation" in metric.name and "error" in metric.name` check before generic error check.

---

### `domain/detection/signal_correlator.py`
**Purpose:** Joins metrics, logs, traces, and eBPF events into unified per-service views.

**Class: `SignalCorrelator`**
Constructor: `(metrics_query, trace_query, log_query, ebpf_query, alignment_tolerance_ms)`

| Method | Notes |
|---|---|
| `correlate(service, namespace, start_time, end_time, ...)` | Main corr. entry. Checks `ebpf_query.is_supported(compute_mechanism)`. Sets `has_degraded_observability=True` if eBPF unsupported. Populates `CorrelatedSignals` with `compute_mechanism` field. |
| `correlate_by_trace_id(trace_id, service)` | Trace-anchored correlation |
| `_fetch_metrics`, `_fetch_traces`, `_fetch_logs`, `_fetch_ebpf_events` | Internal helpers |
| `_safe_query(fn, *args, **kwargs)` | Error isolation |

**Phase 1.5 specifics:** ✅ Correctly uses `eBPFQuery.is_supported()` and sets `has_degraded_observability` and `degradation_reason` when eBPF is unavailable on the target compute mechanism.

---

### `domain/detection/alert_correlation.py`
**Purpose:** Groups related anomalies into incidents.

**Dataclass:** `CorrelatedIncident`: `incident_id`, `alerts`, `services_affected`, `root_service`, `created_at`, `updated_at`, `is_cascade`

**Class: `AlertCorrelationEngine`**
Constructor: `(dep_graph_query, service_graph, event_bus, correlation_window_seconds, max_incident_age_seconds)`

| Method | Notes |
|---|---|
| `process_alert(alert)` | Correlates or creates incident; emits INCIDENT_CREATED event |
| `_should_correlate(alert, incident)` | Same service, time window, or dep graph relationship |
| `_update_root_cause(incident)` | Heuristic: earliest in cascade or most downstream |
| `_expire_old_incidents()` | Removes stale incidents |

---

### `domain/detection/baseline.py`
**Purpose:** Rolling baseline computation and management.

**Dataclasses:** `BaselineWindow` (service, metric, hour_of_day, day_of_week, mean, std_dev, count, min/max, `is_established` property, `update()`, `compute_deviation()`), `BaselineKey`

**Class: `BaselineService(BaselineQuery)`**
Constructor: `(event_bus)`
| Method | Notes |
|---|---|
| `get_baseline(service, metric, timestamp)` | Hour/day-of-week segmented lookup |
| `compute_deviation(service, metric, value, timestamp)` | Returns `(sigma, baseline)` |
| `ingest(service, metric, value, timestamp)` | Async; adds data point; emits BASELINE_UPDATED event when established |
| `baseline_count` (property) | Number of baseline windows |

**Baseline established:** requires 30+ data points.

---

### `domain/detection/cloud_operator_registry.py`
**Purpose:** Registry for routing remediation to correct CloudOperatorPort adapter.

**Class: `CloudOperatorRegistry`**
| Method | Notes |
|---|---|
| `register(operator)` | Indexes by `(provider, mechanism)` and by `provider` |
| `get_operator(provider, compute_mechanism)` | Returns matching operator or None |
| `list_operators(provider)` | List all or filtered |
| `health_check_all()` | Runs health checks on all |

---

### `domain/detection/dependency_graph.py`
**Purpose:** Maintains live service dependency graph.

**Class: `DependencyGraphService`**
Constructor: `(dep_graph_query, trace_query, event_bus, refresh_interval_seconds=300)`
| Method | Notes |
|---|---|
| `refresh()` | Fetches from provider; emits DEPENDENCY_GRAPH_UPDATED |
| `get_upstream/downstream/blast_radius` | Async; refreshes if stale |
| `is_stale` (property) | True if older than refresh_interval |

---

### `domain/detection/health_monitor.py`
**Purpose:** AWS Health API polling for infrastructure events.

**Class: `AWSHealthMonitor`**
Constructor: `(health_client, poll_interval_seconds=300, regions=None)`
Lifecycle: `start()`, `stop()`; polls `DescribeEvents`. Handles `SubscriptionRequiredException` gracefully.

---

### `domain/detection/late_data_handler.py`
**Purpose:** Handles late-arriving telemetry (>60s).

**Class: `LateDataHandler`**
- AC-2.5.4: Ingests late data into baselines flagged as `DataQuality.LATE`
- AC-2.5.5: Checks and applies retroactive updates to recent incidents

---

### `domain/detection/pipeline_monitor.py`
**Purpose:** Monitors health of the telemetry pipeline.

**Class: `PipelineHealthMonitor`**
- Tracks OTel collector heartbeats, eBPF status, data freshness
- Manages `PipelineComponentStatus` (HEALTHY, DEGRADED, DOWN)

---

### `domain/detection/polling_agent.py`
**Purpose:** Proactive CloudWatch metric polling background task.

**Class: `MetricPollingAgent`**
Constructor: `(metrics_adapter, baseline_service, anomaly_detector, event_bus, poll_interval_seconds, watchlist)`
Lifecycle: `start()`, `stop()`; `poll_count` property

---

### `domain/detection/provider_health.py`
**Purpose:** Circuit breaker health monitoring for telemetry providers.

**Class: `ProviderHealthMonitor`**
Constructor: `(event_bus, failure_threshold=3, recovery_probe_interval_seconds=30)`
Circuit states: `CLOSED`, `OPEN`, `HALF_OPEN`
Threshold: 3 consecutive failures → OPEN

---

### `domain/detection/provider_registry.py`
**Purpose:** Runtime-configurable telemetry provider management.

**Class: `ProviderRegistry`**
Constructor: `(event_bus)`
Key methods: `register(provider)`, `activate(provider_name)` (validates connectivity), `check_health()` (circuit breaker)

---

## Domain Diagnostics Layer (`src/sre_agent/domain/diagnostics/`)

### `domain/diagnostics/rag_pipeline.py`
**Purpose:** Full 10-stage RAG diagnostic pipeline.

**Class: `RAGDiagnosticPipeline(DiagnosticPort)`**
Constructor: `(vector_store, embedding, llm, severity_classifier, reasoning_trace_store, validator, confidence_scorer, timeline_constructor, context_budget, event_bus, event_store, compressor, reranker, cache)`

Pipeline stages in `diagnose()`:
1. Stage 0.5: Check semantic cache (DiagnosticCache)
2. Stage 0: Emit INCIDENT_DETECTED event
3. Stage 1: Embed alert description
4. Stage 2: Vector store search (with freshness penalty)
5. Stage 2.5: Cross-encoder reranking (if reranker present)
6. Stage 3: Timeline construction (anomaly-type-aware filtering)
7. Stage 4: Compress evidence (if compressor present)
8. Stage 5: Generate LLM hypothesis
9. Stage 6: Second-opinion validation
10. Stage 7: Composite confidence scoring
11. Stage 8: Severity classification
12. Stage 9: Cache result; emit DIAGNOSIS_GENERATED event

Additional: Novel incident fallback reasoning, reasoning trace persistence (opt-in via `SRE_AGENT_REASONING_TRACE_ENABLED` env var), retrieval-miss fallback.

---

### `domain/diagnostics/confidence.py`
**Purpose:** Evidence-weighted composite confidence scoring.

**Class: `ConfidenceScorer`**
Weights: `llm=0.35`, `validation=0.25`, `retrieval=0.25`, `volume=0.15`
Validation disagreement penalty: `0.30`
Method: `score(llm_confidence, validation_agrees, retrieval_scores, evidence_count, max_evidence) -> float`

---

### `domain/diagnostics/severity.py`
**Purpose:** Deterministic severity classification.

**Class: `SeverityClassifier`**
Constructor: `(service_tiers: dict[str, ServiceTier] | None, default_tier: ServiceTier = TIER_1)`
Method: `classify(alert, llm_confidence, blast_radius_ratio, user_count_affected, max_user_count, is_data_loss, is_security_incident) -> tuple[Severity, ImpactDimensions]`
Rules: Hard rules (data loss/security → SEV1), critical keywords, tier-based scoring, deployment elevation (+1 level), certificate expiry floor.

---

### `domain/diagnostics/timeline.py`
**Purpose:** Chronological signal assembly for LLM context.

**Class: `TimelineConstructor`**
Constructor: `(max_events: int = 50)`
Method: `build(signals: CorrelatedSignals, anomaly_type: str | None) -> str`
Features: `SIGNAL_RELEVANCE` map for anomaly-type-aware filtering, prompt injection sanitization via `sanitize_prompt_text()`.

---

### `domain/diagnostics/validator.py`
**Purpose:** Second-opinion hypothesis validation.

**Enum:** `ValidationStrategy`: `RULE_BASED`, `CROSS_CHECK`, `BOTH`

**Class: `SecondOpinionValidator`**
Constructor: `(llm: LLMReasoningPort | None, strategy: ValidationStrategy = RULE_BASED)`
Method: `validate(hypothesis, evidence_count, alert_description, evidence) -> ValidationResult`
Rule-based checks: citations present, confidence > 0, root cause non-empty.

---

### `domain/diagnostics/cache.py`
**Purpose:** Semantic caching of diagnosis results.

**Class: `DiagnosticCache`**
Default TTL: 4 hours
Fingerprint: SHA-256 of `service:anomaly_type:metric` (16-char hex prefix)
Methods: `get`, `put`, `invalidate`, `clear`, `size` (property)

---

### `domain/diagnostics/ingestion.py`
**Purpose:** Document ingestion pipeline for runbooks/post-mortems.

**Class: `DocumentIngestionPipeline`**
Constructor: `(vector_store, embedding, chunk_min_length=50)`
Methods: `ingest(content, source, metadata) -> int`, `ingest_batch(documents) -> int`, `purge_stale(older_than) -> int`
Chunking: Splits on Markdown headers (`# ` through `###### `)

---

## Domain Remediation Layer (`src/sre_agent/domain/remediation/`)

### `domain/remediation/models.py`
**Purpose:** Remediation domain models.

**Enums:**
- `RemediationStrategy`: `RESTART`, `SCALE_UP`, `SCALE_DOWN`, `GITOPS_REVERT`, `CONFIG_CHANGE`, `CERTIFICATE_ROTATION`, `LOG_TRUNCATION`
- `ApprovalState`: `PENDING`, `APPROVED`, `REJECTED`, `EXPIRED`
- `ActionStatus`: `PROPOSED`, `APPROVED`, `EXECUTING`, `VERIFYING`, `COMPLETED`, `FAILED`, `ROLLED_BACK`, `CANCELLED`
- `VerificationStatus`: `PENDING`, `METRICS_NORMALIZED`, `METRICS_DEGRADED`, `VERIFICATION_TIMEOUT`, `SKIPPED`

**Dataclasses:**
- `SafetyConstraints` (frozen): `max_blast_radius_percentage=20.0`, `canary_percentage=5.0`, `canary_validation_window_seconds=60`, `max_replicas`, `cooldown_ttl_seconds=900`, `requires_human_approval=True`
- `BlastRadiusEstimate` (frozen): `affected_pods_count`, `affected_pods_percentage`, `dependent_services`, `estimated_user_impact`
- `RemediationAction`: `id`, `action_type`, `status`, `target_resource`, `compute_mechanism`, `provider`, `rollback_path`, `blast_radius_estimate`, `batch_index`, `total_targets`, `desired_count`, `metadata`, `executed_at`, `verified_at`, `rollback_executed_at`, `execution_duration_ms`, `lock_fencing_token`
- `RemediationPlan`: `plan_id`, `diagnosis_id`, `incident_id`, `strategy`, `target_resource`, `compute_mechanism`, `provider`, `approval_state`, `safety_constraints`, `blast_radius_estimate`, `actions`, `created_at`, `approved_at`, `approved_by`
- `RemediationResult` (frozen): `success`, `metrics_before`, `metrics_after`, `verification_status`, `rollback_triggered`, `error_message`, `execution_duration_ms`

---

### `domain/remediation/strategies.py`
**Purpose:** Strategy selection mapping.

`ANOMALY_STRATEGY_MAP`:
- `MEMORY_PRESSURE` → `RESTART`
- `LATENCY_SPIKE` → `SCALE_UP`
- `TRAFFIC_ANOMALY` → `SCALE_UP`
- `DEPLOYMENT_INDUCED` → `GITOPS_REVERT`
- `ERROR_RATE_SURGE` → `GITOPS_REVERT`
- `CERTIFICATE_EXPIRY` → `CERTIFICATE_ROTATION`
- `DISK_EXHAUSTION` → `LOG_TRUNCATION`
- **`INVOCATION_ERROR_SURGE` → `SCALE_DOWN`** ✅

`select_strategy(anomaly_type, root_cause) -> RemediationStrategy | None`
Root-cause keyword overrides: OOM→RESTART, cert/tls→CERTIFICATE_ROTATION, deployment/regression→GITOPS_REVERT, traffic/saturation→SCALE_UP, disk/log growth→LOG_TRUNCATION.

---

### `domain/remediation/planner.py`
**Purpose:** Creates deterministic remediation plans from diagnosis context.

**Class: `RemediationPlanner`**
Constructor: `(event_bus, event_store)`
Method: `create_plan(diagnosis, alert, service_graph, current_replicas, max_replicas) -> RemediationPlan`
- Derives `compute_mechanism` and `provider` from alert
- Calculates blast radius from service graph
- Derives `requires_human_approval` from diagnosis
- Emits `REMEDIATION_PLANNED` event

---

### `domain/remediation/engine.py`
**Purpose:** Executes validated remediation plans.

**Class: `RemediationEngine`**
Constructor: `(cloud_operator_registry, guardrails, kill_switch, cooldown, lock_manager, agent_id, priority_level, verifier, event_bus, event_store, remediation_store)`
Method: `execute(plan: RemediationPlan) -> RemediationResult`

Execution flow:
1. Guardrail validation
2. Operator lookup from registry
3. Lock acquisition (if lock_manager present)
4. Execute actions per canary batch size
5. Kill-switch check per action
6. Metric verification post-action
7. Record cooldown
8. Emit events throughout
9. Release lock in `finally` block

Persistence helpers: `_persist_planned_actions`, `_persist_status`, `_persist_failure` (all best-effort)

---

### `domain/remediation/verification.py`
**Purpose:** Post-remediation metric verification.

**Class: `RemediationVerifier`**
Method: `verify_metrics(metrics_after, baseline, sigma_tolerance=1.0) -> VerificationStatus`
Checks: `latency`, `error_rate`, `throughput` keys; returns `METRICS_DEGRADED` if delta > tolerance.

---

## Domain Safety Layer (`src/sre_agent/domain/safety/`)

### `domain/safety/guardrails.py`
**Purpose:** Deterministic safety-gate evaluation.

**Dataclass:** `GuardrailResult` (frozen): `allowed: bool`, `reason: str = ""`

**Class: `GuardrailOrchestrator`**
Constructor: `(kill_switch, blast_radius, cooldown, event_bus, event_store)`
Method: `validate(plan: RemediationPlan, requester_priority: int = 2) -> GuardrailResult`

Gates (in order):
1. Kill switch active → deny
2. Human approval required but not approved → deny
3. Blast radius exceeded → deny, emit BLAST_RADIUS_EXCEEDED
4. Cooldown active → deny, emit COOLDOWN_ENFORCED

---

### `domain/safety/blast_radius.py`
**Purpose:** Blast radius guardrail evaluation.

**Class: `BlastRadiusCalculator`**
Method: `validate(plan, current_replicas=1) -> tuple[bool, str | None]`
Rules: `affected_pods_percentage > max_blast_radius_percentage` → fail; scale_up exceeds 2x replicas → fail.

---

### `domain/safety/cooldown.py`
**Purpose:** Cooldown protocol enforcement to prevent oscillation.

**Class: `CooldownEnforcer`**
Constructor: `(audit: CoordinationAuditPort | None)`
Key methods:
- `record_action(resource_id, compute_mechanism, provider, namespace, ttl_seconds, actor_id)` — sets cooldown + audits
- `is_in_cooldown(resource_id, compute_mechanism, provider, namespace, requester_priority)` — Priority 1 (SecOps) bypasses cooldown
- `build_key(resource_id, compute_mechanism, provider, namespace)` — K8s: `cooldown:{namespace}:{type}:{name}`; Non-K8s: `cooldown:{provider}:{mechanism}:{resource_id}`

---

### `domain/safety/kill_switch.py`
**Purpose:** Global kill switch for autonomous remediation.

**Class: `KillSwitch`**
Constructor: `(event_bus, event_store)`
Properties: `is_active`
Methods: `activate(operator_id, reason)`, `deactivate(operator_id)` — emit KILL_SWITCH_ACTIVATED/DEACTIVATED events

---

### `domain/safety/phase_gate.py`
**Purpose:** Graduation criteria evaluation.

**Dataclass:** `PhaseMetrics`: `diagnostic_accuracy`, `destructive_false_positives`, `sev34_autonomous_resolution_rate`, `remediation_integration_coverage`, `soak_test_clean_days`

**Class: `PhaseGate`**
Method: `evaluate_graduation(metrics) -> tuple[bool, list[str]]`
Thresholds: accuracy ≥ 0.90, destructive FP = 0, Sev3-4 resolution ≥ 0.95, coverage ≥ 0.30, soak days ≥ 7.

---

## Spec Alignment Checklist

| Requirement | File | Status |
|---|---|---|
| `ComputeMechanism` enum with KUBERNETES, SERVERLESS, VIRTUAL_MACHINE, CONTAINER_INSTANCE | domain/models/canonical.py | ✅ Implemented |
| `CorrelatedSignals.has_degraded_observability: bool` field | domain/models/canonical.py | ✅ Implemented |
| `CorrelatedSignals.compute_mechanism` field | domain/models/canonical.py | ✅ Implemented |
| `ServiceLabels.compute_mechanism` field | domain/models/canonical.py | ✅ Implemented |
| `ServiceNode.compute_mechanism` field | domain/models/canonical.py | ✅ Implemented |
| `AnomalyAlert.compute_mechanism` field | domain/models/canonical.py | ✅ Implemented |
| `AnomalyAlert.resource_id` field | domain/models/canonical.py | ✅ Implemented |
| `AnomalyType.INVOCATION_ERROR_SURGE` enum value | domain/models/canonical.py | ✅ Implemented |
| `CloudOperatorPort` interface in ports/ | ports/cloud_operator.py | ✅ Implemented (full Phase 1.5) |
| `CloudOperatorPort.restart_compute_unit()` | ports/cloud_operator.py | ✅ Implemented |
| `CloudOperatorPort.scale_capacity()` | ports/cloud_operator.py | ✅ Implemented |
| `CloudOperatorPort.is_action_supported()` | ports/cloud_operator.py | ✅ Implemented (concrete method) |
| `CloudOperatorRegistry` | domain/detection/cloud_operator_registry.py | ✅ Implemented |
| `eBPFQuery.is_supported(compute_mechanism)` method | ports/telemetry.py | ✅ Implemented (concrete, returns True for K8s+VM only) |
| Cold-start suppression (15s window) for SERVERLESS | domain/detection/anomaly_detector.py + domain/models/detection_config.py | ✅ Implemented |
| Memory-pressure exemption for SERVERLESS | domain/detection/anomaly_detector.py | ✅ Implemented |
| InvocationError surge monitoring for serverless | domain/detection/anomaly_detector.py | ✅ Implemented |
| `INVOCATION_ERROR_SURGE` → `SCALE_DOWN` strategy | domain/remediation/strategies.py | ✅ Implemented |
| Signal correlator uses `eBPFQuery.is_supported()` | domain/detection/signal_correlator.py | ✅ Implemented |
| Signal correlator sets `has_degraded_observability` when eBPF unsupported | domain/detection/signal_correlator.py | ✅ Implemented |
| RAG diagnostic pipeline (10 stages) | domain/diagnostics/rag_pipeline.py | ✅ Implemented |
| Semantic diagnostic cache (4h TTL) | domain/diagnostics/cache.py | ✅ Implemented |
| Cross-encoder reranking (Phase 2.2) | ports/reranker.py + rag_pipeline.py | ✅ Implemented |
| Timeline construction with anomaly-type filtering | domain/diagnostics/timeline.py | ✅ Implemented |
| Prompt injection sanitization in timeline | domain/diagnostics/timeline.py | ✅ Implemented |
| Text compression for token budget (Phase 2.2) | ports/compressor.py + rag_pipeline.py | ✅ Implemented |
| Composite confidence scoring (4 components) | domain/diagnostics/confidence.py | ✅ Implemented |
| Severity classification (deterministic rules) | domain/diagnostics/severity.py | ✅ Implemented |
| Second-opinion validation (rule-based + LLM cross-check) | domain/diagnostics/validator.py | ✅ Implemented |
| Document ingestion (Markdown chunking) | domain/diagnostics/ingestion.py | ✅ Implemented |
| Guardrail orchestration (kill-switch, approval, blast-radius, cooldown) | domain/safety/guardrails.py | ✅ Implemented |
| Blast radius guardrail (20% limit, 2x replica limit) | domain/safety/blast_radius.py | ✅ Implemented |
| Cooldown enforcer with compute-mechanism-aware key | domain/safety/cooldown.py | ✅ Implemented |
| Cooldown: Priority 1 (SecOps) bypasses cooldown | domain/safety/cooldown.py | ✅ Implemented |
| Kill switch with event emission | domain/safety/kill_switch.py | ✅ Implemented |
| Phase gate graduation criteria evaluator | domain/safety/phase_gate.py | ✅ Implemented |
| `RemediationPlanner` (diagnosis → plan) | domain/remediation/planner.py | ✅ Implemented |
| `RemediationEngine` (execute with lock, canary, cooldown) | domain/remediation/engine.py | ✅ Implemented |
| `RemediationVerifier` (metric normalization check) | domain/remediation/verification.py | ✅ Implemented |
| `RemediationPort` interface | ports/remediation.py | ✅ Implemented |
| `DistributedLockManagerPort` with fencing token | ports/lock_manager.py | ✅ Implemented |
| Lock key schema per AGENTS.md (provider, compute_mechanism, resource_id) | ports/lock_manager.py (LockRequest) | ✅ Implemented |
| `LockRequest.compute_mechanism` field | ports/lock_manager.py | ✅ Implemented |
| `CoordinationAuditPort` (lock/cooldown/override audit) | ports/persistence.py | ✅ Implemented |
| `IncidentStorePort` (event sourcing + projection) | ports/persistence.py | ✅ Implemented |
| `OutboxPort` (transactional outbox with claim/release) | ports/persistence.py | ✅ Implemented |
| `DiagnosisStorePort` | ports/persistence.py | ✅ Implemented |
| `ReasoningTracePort` (run/tool_call/retrieved_context) | ports/persistence.py | ✅ Implemented |
| `RemediationStorePort` | ports/persistence.py | ✅ Implemented |
| `DuplicateEventError`, `StaleProjectionError` exceptions | ports/persistence.py | ✅ Implemented |
| `IncidentEvent` validates `compute_mechanism` against allowed tokens | domain/models/persistence.py | ✅ Implemented |
| `Incident` validates status transitions | domain/models/persistence.py | ✅ Implemented |
| Alert correlation engine (dep graph, time window) | domain/detection/alert_correlation.py | ✅ Implemented |
| Rolling baseline with time-of-day/day-of-week segmentation | domain/detection/baseline.py | ✅ Implemented |
| Deployment-aware detection (suppression window, correlation) | domain/detection/anomaly_detector.py | ✅ Implemented |
| Multi-dimensional anomaly correlation (AC-3.2.3) | domain/detection/anomaly_detector.py | ✅ Implemented |
| Per-service/metric sensitivity overrides (AC-3.5.1/3.5.2) | domain/detection/anomaly_detector.py | ✅ Implemented |
| `ProviderRegistry` with runtime provider switching | domain/detection/provider_registry.py | ✅ Implemented |
| `ProviderHealthMonitor` with circuit breaker | domain/detection/provider_health.py | ✅ Implemented |
| `DependencyGraphService` with 5-minute refresh | domain/detection/dependency_graph.py | ✅ Implemented |
| `PipelineHealthMonitor` for meta-observability | domain/detection/pipeline_monitor.py | ✅ Implemented |
| `LateDataHandler` (AC-2.5.4, retroactive updates AC-2.5.5) | domain/detection/late_data_handler.py | ✅ Implemented |
| `AWSHealthMonitor` with SubscriptionRequiredException handling | domain/detection/health_monitor.py | ✅ Implemented |
| `MetricPollingAgent` for CloudWatch proactive polling | domain/detection/polling_agent.py | ✅ Implemented |
| `ConfidenceLevel` thresholds (BLOCK < 0.70, PROPOSE 0.70-0.85, AUTONOMOUS ≥ 0.85) | domain/models/diagnosis.py | ✅ Implemented |
| `Diagnosis.requires_human_approval` — SEV1/2 always require approval | domain/models/diagnosis.py | ✅ Implemented |
| `ImpactDimensions` weighted formula (0.30/0.25/0.20/0.15/0.10) | domain/models/diagnosis.py | ✅ Implemented |
| Severity classifier — certificate expiry floor by hours remaining | domain/diagnostics/severity.py | ✅ Implemented |
| `DetectionConfig.cold_start_suppression_window_seconds = 15` | domain/models/detection_config.py | ✅ Implemented |
| Freshness penalty for stale vector documents | domain/diagnostics/rag_pipeline.py (`_apply_freshness_penalty`) | ✅ Implemented |
| `EmbeddingPort` with `embed_text`, `embed_batch` | ports/embedding.py | ✅ Implemented |
| `VectorStorePort` with upsert, batch, search, delete_stale | ports/vector_store.py | ✅ Implemented |

---

## Critical Missing Items

No critical missing items found. All spec-required features identified across:
- Phase 1.5 non-K8s platform support
- Phase 2 intelligence layer (RAG, confidence, severity, validation)
- Phase 2.2 token optimization (reranker, compressor, cache, timeline filtering)
- Phase 3 reasoning trace persistence
- Phase 4 persistence architecture (incident store, outbox, coordination audit, remediation store)
- Safety layer (guardrails, blast radius, cooldown, kill switch, phase gate)
- Multi-agent coordination (lock manager with fencing tokens, priority preemption)

appear to be implemented at the ports and domain level.

---

## Notes on Partial / Potential Gaps

1. **`RemediationEngine.execute()` metric verification:** The verifier is called with hardcoded mock metrics (`{"latency": 1.0, ...}`), not actual post-remediation metrics from telemetry. The `RemediationVerifier` is sound but not wired to real metrics queries. This is a ⚠️ partial implementation for the verification gate.

2. **`ProviderHealthMonitor` vs `ProviderRegistry`:** Two separate health-tracking classes exist (`ProviderHealthMonitor` with circuit breaker, and `ProviderRegistry.check_health()`). They are not wired together at the domain level — integration responsibility falls on the API/adapter layer.

3. **`BaselineService.compute_deviation`** returns `(0.0, None)` when baseline is not established (fewer than 30 data points), which suppresses all anomaly detection for new services until enough data is accumulated. This is by design but means cold-start detection (Phase 1.5) and sigma-based detection cannot fire until baselines are warm.

4. **Novel incident fallback:** `_attempt_general_inference_fallback` is called in `rag_pipeline.py` when no evidence is retrieved, but its implementation is not visible in the read window. Requires additional verification it handles the fallback correctly and caps confidence at `_FALLBACK_MAX_CONFIDENCE = 0.69`.

---

## Follow-on Research (Within Scope)

- [ ] Read the remainder of `rag_pipeline.py` to confirm `_attempt_general_inference_fallback` implementation and confidence cap
- [ ] Verify `RemediationEngine._execute_action()` correctly dispatches to `CloudOperatorPort.restart_compute_unit()` vs `scale_capacity()` based on action type
- [ ] Confirm `RemediationEngine._calculate_canary_batch_size()` logic
- [ ] Check adapters exist for the Phase 1.5 cloud operators (ECS, Lambda, Azure App Service)
