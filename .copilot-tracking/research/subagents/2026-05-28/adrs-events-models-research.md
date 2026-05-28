# Research: SREAgent ADRs, Events Adapter, Domain Models, and Quality Gaps

**Date:** 2026-05-28  
**Status:** Complete  
**Scope:** ADRs, events adapter, domain models, persistence models, Redis Streams tests, multi-agent coordination persistence, engineering standards

---

## Research Questions and Status

| Question | Status |
|---|---|
| ADR files — list all, focus on persistence | Complete |
| Events adapter — class names, stream keys, methods | Complete |
| EventBusPort interface from ports/events.py | Complete |
| Domain model fields for persistence-related models | Complete |
| Domain-level persistence logic (not adapter) | Complete |
| Redis Streams test names and scenarios | Complete |
| Multi-agent coordination doc — persistence angle | Complete |
| Engineering standards — persistence-related | Complete |
| VectorDocument location and structure | Complete |

---

## 1. ADR Files

**Location:** `docs/project/ADRs/` (NOT `docs/architecture/ADRs/` — that path does not exist)

**Files present:**
- `docs/project/ADRs/001-hexagonal-architecture.md`
- `docs/project/ADRs/002-pydantic-over-dataclasses.md`
- `docs/project/ADRs/003-coordination-backend-selection.md`
- `docs/project/ADRs/004-remediation-safety-boundaries.md`
- `docs/project/ADRs/005-multi-agent-priority-preemption.md`
- `docs/project/ADRs/006-persistence-authority-reconciliation.md`
- `docs/project/ADRs/_template.md`

### ADR-001: Hexagonal Architecture (Ports & Adapters)

- **Status:** ACCEPTED  
- **Date:** 2024-12-01  
- **Decision:** Adopt hexagonal architecture: domain/, ports/, adapters/ with strict inward-only dependency direction. Domain depends on ports (ABCs), adapters implement ports, bootstrap.py is sole composition root.
- **Persistence relevance:** Establishes that persistence adapters (PostgresIncidentStore, etc.) must implement port ABCs from `ports/`. Domain layer must never import from `adapters/`.

### ADR-002: Pydantic BaseModel Over Python Dataclasses

- **Status:** ACCEPTED  
- **Date:** 2024-12-15  
- **Decision:** Use Pydantic `BaseModel` for all canonical domain models to enforce runtime type validation, serialization, and JSON schema generation.
- **Persistence relevance:** All canonical domain models should be Pydantic BaseModel. **QUALITY GAP:** `canonical.py`, `diagnosis.py`, `persistence.py`, and `detection_config.py` all use `@dataclass` / frozen dataclasses — not Pydantic BaseModel. This is a direct contradiction of the accepted ADR.

### ADR-003: Coordination Backend Selection

- **Status:** ACCEPTED  
- **Date:** 2026-03-19  
- **Decision:** Redis-compatible lock management (current), with etcd-backed environments as a compatibility target. Supports TTL-based locks, pub/sub revocation signaling, monotonic fencing token semantics.
- **Persistence relevance:** Redis is the coordination state backend. Defines lock key schema governance as mandatory. Delivery semantics left as "reliable delivery" (ambiguous until ADR-006).

### ADR-004: Remediation Safety Boundaries

- **Status:** ACCEPTED  
- **Date:** 2026-03-19  
- **Decision:** Blast-radius constraints, policy checks before execution, kill-switch backoff, post-action verification and rollback requirements.
- **Persistence relevance:** Kill-switch and override state must be persisted (ADR-006 closes this — safety state is in migration wave 1).

### ADR-005: Multi-Agent Priority and Preemption

- **Status:** ACCEPTED  
- **Date:** 2026-03-19  
- **Decision:** SecOps priority 1 (override), SRE priority 2, FinOps priority 3. Lock manager enforces preemption, emits revocation events, preempted agent queues retry.
- **Persistence relevance:** Preemption events and cooldown keys must be durably recorded. `CoordinationAuditPort` and `coordination_audit` PostgreSQL table are the implementation surface.

### ADR-006: Persistence Architecture Authority Reconciliation (PRIMARY PERSISTENCE ADR)

- **Status:** ACCEPTED  
- **Date:** 2026-04-09  
- **Decision summary:** Resolves six clarification gates (C-01 through C-06) blocking persistence implementation:

| Gate | Decision |
|---|---|
| C-01 Document authority | `docs/architecture/persistence_architecture.md` is the canonical implementation authority |
| C-02 Vector backend | pgvector for production, ChromaDB for local/dev only |
| C-03 Event bus | Redis Streams now; Kafka/NATS only if stream lag > 60s for 10+ consecutive minutes |
| C-04 Delivery semantics | At-least-once with idempotent consumer (idempotency_key + processed_events dedup) |
| C-05 Safety state scope | Cooldown, kill-switch, and human override state included in migration wave 1 |
| C-06 Split gate thresholds | Six quantitative thresholds (see table below) |

**Quantitative split gates from ADR-006:**

| Gate | Threshold | Duration | Trigger |
|---|---|---|---|
| DB write latency | p95 incident_events insert > 120ms | 15 min consecutive | Evaluate dedicated event store |
| Outbox backlog | pending rows > 100,000 | 10 min consecutive | Evaluate stream infra upgrade |
| Stream lag | any critical consumer lag > 60s | 10 min consecutive | Evaluate Kafka/NATS migration |
| DB contention | PG CPU > 75% AND IO wait > 20% | 30 min steady load | Evaluate read replica |
| Vector scale | rows > 1M AND p95 similarity > 250ms | 7 days consecutive | Evaluate dedicated vector DB |
| Metrics ingest | > 10M events/day AND refresh lag > 5 min | 3 days consecutive | Evaluate dedicated TSDB |

---

## 2. Events Adapter

**File:** `src/sre_agent/adapters/events/redis_streams_event_bus.py`  
**Files in directory:** `__init__.py`, `redis_streams_event_bus.py`

### Class: RedisStreamsEventBus

Implements `EventBus` port. Phase 4.0.

**Constructor signature:**
```python
def __init__(
    self,
    redis_client: object,
    stream_prefix: str = "sre-agent:events",
    consumer_group: str = "sre-agent-consumers",
    consumer_name: str = "sre-agent-worker-1",
    block_ms: int = 1000,
    batch_size: int = 10,
    claim_idle_ms: int = 30_000,
) -> None:
```

**Stream key pattern:** `{stream_prefix}:{event_type}` (e.g., `sre-agent:events:anomaly.detected`)

**Internal state:**
- `_handlers: dict[str, list[EventHandler]]` — event_type → list of handlers
- `_reader_scopes: dict[str, anyio.CancelScope]` — event_type → cancel scope for reader task
- `_pending_readers: list[tuple[anyio.CancelScope, str, str]]` — deferred before `start()` is called
- `_task_group: anyio.abc.TaskGroup | None` — stored after `start()` for late subscriber spawning

**Public method signatures:**
```python
async def publish(self, event: DomainEvent) -> None
async def subscribe(self, event_type: str, handler: EventHandler) -> None
async def unsubscribe(self, event_type: str, handler: EventHandler) -> None
async def start(self, task_group: anyio.abc.TaskGroup) -> None
async def run_readers(self) -> None  # backward compat wrapper
```

**Private method signatures:**
```python
async def _ensure_consumer_group(self, stream_key: str) -> None
async def _start_reader(self, event_type: str, stream_key: str) -> anyio.CancelScope
async def _read_loop(self, event_type: str, stream_key: str) -> None
async def _drain_pending(self, event_type: str, stream_key: str) -> None
@staticmethod def _extract_pending_count(xpending_result: object) -> float
async def _observe_stream_lag(self, stream_key: str) -> None
async def _dispatch(self, event_type: str, msg_id: object, fields: dict, stream_key: str) -> None
async def _ack(self, stream_key: str, msg_id: object) -> None
```

**Key behavioral properties:**
- `XADD` on publish with JSON payload including `event_id`, `event_type`, `aggregate_id`, `timestamp`, `payload`
- `XGROUP CREATE ... $ MKSTREAM` on first subscribe
- Drains PEL (Pending Entry List) on restart using `XREADGROUP` with ID `"0"` before switching to `">"`
- ACK (`XACK`) sent only after ALL handlers succeed; message stays in PEL if any handler raises
- Handler exceptions are caught and logged — other handlers continue (error isolation)
- Late subscriptions after `start()` immediately spawn readers into the stored task group (F4 fix)
- Wildcard `"*"` subscription sentinel for global handlers
- Stream lag Prometheus metric updated via `REDIS_STREAM_LAG.labels(stream, group).set(count)`
- Malformed messages (JSON decode failure) are ACKed immediately to unblock the consumer group
- Wildcard sentinel: `_WILDCARD = "*"` — handlers registered to `"*"` receive all events

---

## 3. EventBusPort Interface

**File:** `src/sre_agent/ports/events.py` (lines 1–100+)

```python
EventHandler = Callable[[DomainEvent], Awaitable[None]]

class EventBus(ABC):
    @abstractmethod
    async def publish(self, event: DomainEvent) -> None: ...

    @abstractmethod
    async def subscribe(self, event_type: str, handler: EventHandler) -> None: ...

    @abstractmethod
    async def unsubscribe(self, event_type: str, handler: EventHandler) -> None: ...

    async def start(self, task_group: anyio.abc.TaskGroup) -> None:
        # Non-abstract hook — default is no-op
        # Must be called during lifespan startup for I/O buses (Redis Streams)
        ...

class EventStore(ABC):
    @abstractmethod
    async def append(self, event: DomainEvent) -> None: ...

    @abstractmethod
    async def get_events(
        self,
        aggregate_id: str,
        event_types: list[str] | None = None,
    ) -> list[DomainEvent]: ...
```

**QUALITY GAP:** `EventStore` ABC is defined in `ports/events.py` but no concrete adapter implementation for it was found. The Redis Streams adapter only implements `EventBus`, not `EventStore`. The PostgresIncidentStore writes to `incident_events` but implements `IncidentStorePort`, not `EventStore`. The `EventStore` port has no implementor.

---

## 4. Domain Model Files — Complete Field Inventory

**Directory:** `src/sre_agent/domain/models/`  
**Files:** `__init__.py`, `canonical.py`, `detection_config.py`, `diagnosis.py`, `persistence.py`

---

### 4.1 canonical.py (lines 1–450+)

**Note:** Uses `@dataclass` / `frozen=True` — NOT Pydantic BaseModel (contradicts ADR-002).

**Enums:**
- `SignalType`: METRIC, TRACE, LOG, EBPF_EVENT
- `DataQuality`: HIGH, LOW, INCOMPLETE, LATE
- `Severity`: SEV1=1, SEV2=2, SEV3=3, SEV4=4
- `AnomalyType`: LATENCY_SPIKE, ERROR_RATE_SURGE, MEMORY_PRESSURE, DISK_EXHAUSTION, CERTIFICATE_EXPIRY, MULTI_DIMENSIONAL, DEPLOYMENT_INDUCED, INVOCATION_ERROR_SURGE, TRAFFIC_ANOMALY
- `IncidentPhase`: DETECTED, CLASSIFIED, DIAGNOSING, DIAGNOSED, VALIDATING, AUTHORIZING, REMEDIATING, VERIFYING, RESOLVED, ESCALATED, FAILED
- `OperationalPhase`: OBSERVE, ASSIST, AUTONOMOUS, PREDICTIVE
- `ComputeMechanism`: KUBERNETES, SERVERLESS, VIRTUAL_MACHINE, CONTAINER_INSTANCE

**Value objects (frozen dataclasses):**

`ServiceLabels`:
```python
service: str
namespace: str = ""
compute_mechanism: ComputeMechanism = ComputeMechanism.KUBERNETES
resource_id: str = ""
pod: str = ""
node: str = ""
platform_metadata: dict[str, Any] = field(default_factory=dict)
extra: dict[str, str] = field(default_factory=dict)
```

`CanonicalMetric`:
```python
name: str
value: float
timestamp: datetime
labels: ServiceLabels
unit: str = ""
quality: DataQuality = DataQuality.HIGH
provider_source: str = ""
ingestion_timestamp: datetime | None = None
# property: is_low_quality -> bool
```

`TraceSpan`:
```python
span_id: str
parent_span_id: str | None
service: str
operation: str
duration_ms: float
status_code: int = 200
error: str | None = None
attributes: dict[str, Any] = field(default_factory=dict)
start_time: datetime | None = None
end_time: datetime | None = None
```

`CanonicalTrace`:
```python
trace_id: str
spans: list[TraceSpan] = field(default_factory=list)
is_complete: bool = True
missing_services: list[str] = field(default_factory=list)
quality: DataQuality = DataQuality.HIGH
provider_source: str = ""
ingestion_timestamp: datetime | None = None
# properties: root_span, duration_ms, services_involved
```

`CanonicalLogEntry`:
```python
timestamp: datetime
message: str
severity: str
labels: ServiceLabels
trace_id: str | None = None
span_id: str | None = None
attributes: dict[str, Any] = field(default_factory=dict)
quality: DataQuality = DataQuality.HIGH
provider_source: str = ""
ingestion_timestamp: datetime | None = None
```

`CanonicalEvent`:
```python
event_type: str
source: str
timestamp: datetime
metadata: dict[str, Any] = field(default_factory=dict)
labels: ServiceLabels | None = None
quality: DataQuality = DataQuality.HIGH
provider_source: str = ""
ingestion_timestamp: datetime | None = None
```

`ServiceNode` (frozen):
```python
service: str
version: str = ""
namespace: str = ""
compute_mechanism: ComputeMechanism = ComputeMechanism.KUBERNETES
tier: int = 3
is_healthy: bool = True
```

`ServiceEdge` (frozen):
```python
source: str
target: str
protocol: str = "http"
avg_latency_ms: float = 0.0
error_rate: float = 0.0
```

`ServiceGraph`:
```python
nodes: dict[str, ServiceNode] = field(default_factory=dict)
edges: list[ServiceEdge] = field(default_factory=list)
last_updated: datetime | None = None
# methods: get_upstream, get_downstream, get_transitive_downstream
```

`CorrelatedSignals`:
```python
service: str
namespace: str = ""
time_window_start: datetime
time_window_end: datetime
compute_mechanism: ComputeMechanism = ComputeMechanism.KUBERNETES
metrics: list[CanonicalMetric] = field(default_factory=list)
traces: list[CanonicalTrace] = field(default_factory=list)
logs: list[CanonicalLogEntry] = field(default_factory=list)
events: list[CanonicalEvent] = field(default_factory=list)
has_degraded_observability: bool = False
degradation_reason: str | None = None
```

`AnomalyAlert`:
```python
alert_id: UUID = field(default_factory=uuid4)
anomaly_type: AnomalyType = AnomalyType.LATENCY_SPIKE
service: str = ""
namespace: str = ""
resource_id: str = ""
compute_mechanism: ComputeMechanism = ComputeMechanism.KUBERNETES
severity: Severity | None = None
timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
metric_name: str = ""
current_value: float = 0.0
baseline_value: float = 0.0
deviation_sigma: float = 0.0
description: str = ""
blast_radius_ratio: float = 0.0
correlated_incident_id: UUID | None = None
is_deployment_induced: bool = False
deployment_details: dict[str, Any] | None = None
correlated_signals: CorrelatedSignals | None = None
related_alerts: list[UUID] = field(default_factory=list)
detected_at: datetime | None = None
alert_generated_at: datetime | None = None
```

`DomainEvent` (Event Sourcing base — Engineering Standards §1.5):
```python
event_id: UUID = field(default_factory=uuid4)
timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
event_type: str = ""
aggregate_id: UUID | None = None
payload: dict[str, Any] = field(default_factory=dict)
# property: is_valid -> bool
```

`EventTypes` (class with string constants):
```python
# Detection
ANOMALY_DETECTED = "anomaly.detected"
ANOMALY_CORRELATED = "anomaly.correlated"
ALERT_SUPPRESSED = "alert.suppressed"
OBSERVABILITY_DEGRADED = "observability.degraded"
PROVIDER_HEALTH_CHANGED = "provider.health_changed"
DEPENDENCY_GRAPH_UPDATED = "dependency_graph.updated"
BASELINE_UPDATED = "baseline.updated"
INCIDENT_CREATED = "incident.created"
# Intelligence
INCIDENT_DETECTED = "incident.detected"
DIAGNOSIS_GENERATED = "diagnosis.generated"
SECOND_OPINION_COMPLETED = "second_opinion.completed"
SEVERITY_ASSIGNED = "severity.assigned"
# Remediation
REMEDIATION_PLANNED = "remediation.planned"
REMEDIATION_APPROVED = "remediation.approved"
REMEDIATION_STARTED = "remediation.started"
REMEDIATION_COMPLETED = "remediation.completed"
REMEDIATION_FAILED = "remediation.failed"
REMEDIATION_ROLLED_BACK = "remediation.rolled_back"
# Safety
KILL_SWITCH_ACTIVATED = "kill_switch.activated"
KILL_SWITCH_DEACTIVATED = "kill_switch.deactivated"
BLAST_RADIUS_EXCEEDED = "blast_radius.exceeded"
COOLDOWN_ENFORCED = "cooldown.enforced"
PHASE_GATE_EVALUATED = "phase_gate.evaluated"
```

---

### 4.2 diagnosis.py

**Note:** Uses `@dataclass` — NOT Pydantic BaseModel.

`ServiceTier` (IntEnum): TIER_1=1, TIER_2=2, TIER_3=3, TIER_4=4

`DiagnosticState` (IntEnum): PENDING=0, RETRIEVING=1, REASONING=2, VALIDATING=3, CLASSIFYING=4, COMPLETE=5, FAILED=6, ESCALATED=7, RETRIEVAL_MISS=8, FALLBACK_REASONING=9, ROOT_CAUSE_UNRESOLVED=10

`ConfidenceLevel` (frozen dataclass):
```python
BLOCK_THRESHOLD: float = 0.70
PROPOSE_THRESHOLD: float = 0.85
@staticmethod def from_score(score: float) -> str  # "BLOCK" | "PROPOSE" | "AUTONOMOUS"
# Thresholds: < 0.70 BLOCK, 0.70-0.85 PROPOSE, >= 0.85 AUTONOMOUS
```

`EvidenceCitation` (frozen dataclass):
```python
source: str
content_snippet: str
relevance_score: float  # validated: must be in [0.0, 1.0]
doc_id: str = ""
# __post_init__: raises ValueError if relevance_score not in [0, 1]
```

`ImpactDimensions`:
```python
user_impact: float = 0.0
service_tier_score: float = 0.0
blast_radius: float = 0.0
financial_impact: float = 0.0
reversibility: float = 1.0  # 1.0 = fully reversible
# method: compute_severity_score() -> float
#   formula: 0.30*user_impact + 0.25*service_tier_score + 0.20*blast_radius + 0.15*financial_impact + 0.10*(1-reversibility)
# method: to_severity() -> Severity
#   >= 0.75 -> SEV1, >= 0.50 -> SEV2, >= 0.25 -> SEV3, < 0.25 -> SEV4
```

`Diagnosis`:
```python
diagnosis_id: UUID = field(default_factory=uuid4)
alert_id: UUID | None = None
service: str = ""
root_cause: str = ""
confidence: float = 0.0
severity: Severity = Severity.SEV4
reasoning: str = ""
evidence_citations: list[EvidenceCitation] = field(default_factory=list)
impact: ImpactDimensions | None = None
suggested_remediation: str = ""
is_novel: bool = False
state: DiagnosticState = DiagnosticState.PENDING
diagnosed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
audit_entries: list[AuditEntry] = field(default_factory=list)
# property: confidence_level -> str (delegates to ConfidenceLevel.from_score)
# property: requires_human_approval -> bool (SEV1/SEV2 always True; or confidence_level != "AUTONOMOUS")
```

`AuditEntry` (frozen dataclass):
```python
stage: str
action: str
timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
details: dict[str, Any] = field(default_factory=dict)
```

---

### 4.3 persistence.py (PERSISTENCE-CRITICAL)

**Note:** Uses `@dataclass` and StrEnum — NOT Pydantic BaseModel.

**State machine enums with transition tables:**

`IncidentStatus` (StrEnum): OPEN, INVESTIGATING, MITIGATING, RESOLVED, CLOSED  
`INCIDENT_STATUS_TRANSITIONS: dict[IncidentStatus, set[IncidentStatus]]`
- OPEN → {INVESTIGATING}
- INVESTIGATING → {MITIGATING}
- MITIGATING → {RESOLVED, INVESTIGATING}  ← rollback/failed mitigation
- RESOLVED → {CLOSED}
- CLOSED → {} (terminal)

`RemediationStatus` (StrEnum): PLANNED, APPROVED, RUNNING, COMPLETED, FAILED, ROLLED_BACK  
`REMEDIATION_STATUS_TRANSITIONS: dict[RemediationStatus, set[RemediationStatus]]`
- PLANNED → {APPROVED}
- APPROVED → {RUNNING}
- RUNNING → {COMPLETED, FAILED}
- FAILED → {ROLLED_BACK}
- COMPLETED → {} (terminal)
- ROLLED_BACK → {} (terminal)

`OutboxStatus` (StrEnum): PENDING, SENT, FAILED

`ComputeMechanismToken` (StrEnum — uppercase, matches AGENTS.md lock schema):
- KUBERNETES = "KUBERNETES", SERVERLESS = "SERVERLESS"
- VIRTUAL_MACHINE = "VIRTUAL_MACHINE", CONTAINER_INSTANCE = "CONTAINER_INSTANCE"

`ProviderToken` (StrEnum — lowercase, matches AGENTS.md):
- KUBERNETES = "kubernetes", AWS = "aws", AZURE = "azure"

**Domain entities:**

`IncidentEvent` (frozen dataclass — immutable event, source of truth):
```python
event_id: UUID
incident_id: UUID
event_type: str           # validated: must not be empty
occurred_at: datetime
provider: str             # validated: must be in ProviderToken values
compute_mechanism: str    # validated: must be in ComputeMechanismToken members
resource_id: str
payload_json: dict[str, Any]
idempotency_key: str
correlation_key: str | None = None
# __post_init__ raises ValueError for empty event_type, invalid compute_mechanism, invalid provider
```

`Incident` (mutable dataclass — projection for API/dashboard):
```python
incident_id: UUID
service: str
severity: str
status: IncidentStatus
opened_at: datetime
updated_at: datetime
latest_event_id: UUID
provider: str
compute_mechanism: str
resource_id: str
closed_at: datetime | None = None
```

`DiagnosisResult` (frozen dataclass — durable diagnosis outcome):
```python
diagnosis_id: UUID
incident_id: UUID
diagnosis_summary: str
confidence_score: float   # validated: must be in [0, 1]
evidence_refs: dict[str, Any]
generated_at: datetime
model_name: str
# __post_init__ raises ValueError if confidence_score not in [0, 1]
```

`RemediationAction` (frozen dataclass — planned/executed record with rollback traceability):
```python
action_id: UUID
incident_id: UUID
action_type: str
action_status: RemediationStatus
approval_mode: str
requested_at: datetime
started_at: datetime | None = None
completed_at: datetime | None = None
rollback_action_id: UUID | None = None
execution_result: dict[str, Any] | None = None
```

`OutboxEntry` (dataclass — transactional outbox):
```python
outbox_id: UUID
event_id: UUID
topic: str
payload_json: dict[str, Any]
status: OutboxStatus
created_at: datetime
sent_at: datetime | None = None
retry_count: int = 0
```

`CoordinationAuditEntry` (frozen dataclass — durable lock/cooldown/override audit):
```python
audit_id: UUID
actor_type: str
actor_id: str
action: str
provider: str             # validated: must be in ProviderToken values
compute_mechanism: str    # validated: must be in ComputeMechanismToken members
resource_id: str
created_at: datetime
lock_priority: int | None = None
fencing_token: int | None = None
details_json: dict[str, Any] | None = None
# __post_init__ raises ValueError for invalid compute_mechanism or provider
```

---

### 4.4 detection_config.py

`DetectionConfig` (dataclass — domain-owned configuration):
```python
latency_sigma_threshold: float = 3.0
latency_duration_minutes: int = 2
error_rate_surge_percent: float = 200.0
memory_pressure_percent: float = 85.0
memory_pressure_duration_minutes: int = 5
disk_exhaustion_percent: float = 80.0
disk_projection_hours: int = 24
cert_expiry_warning_days: int = 14
cert_expiry_critical_days: int = 3
deployment_correlation_window_minutes: int = 60
suppression_window_seconds: int = 30
cold_start_suppression_window_seconds: int = 15  # Phase 1.5 serverless
multi_dim_latency_percent: float = 50.0
multi_dim_error_percent: float = 80.0
multi_dim_window_minutes: int = 5
```

---

## 5. Domain-Level Persistence Logic (Domain Invariants — Not Adapter)

**No top-level domain files** for persistence (`domain/persistence.py`, `domain/events.py`, `domain/incident.py` do not exist). All are under `domain/models/`.

**Domain invariants enforced via `__post_init__` in domain models:**

`IncidentEvent.__post_init__` (`persistence.py`, ~line 148):
- `event_type` must not be empty → `ValueError`
- `compute_mechanism` must be a valid `ComputeMechanismToken` member → `ValueError`
- `provider` must be a valid `ProviderToken` value → `ValueError`

`DiagnosisResult.__post_init__` (`persistence.py`, ~line 168):
- `confidence_score` must be in [0, 1] → `ValueError`

`CoordinationAuditEntry.__post_init__` (`persistence.py`, ~line 215):
- `compute_mechanism` must be a valid `ComputeMechanismToken` member → `ValueError`
- `provider` must be a valid `ProviderToken` value → `ValueError`

`EvidenceCitation.__post_init__` (`diagnosis.py`, ~line 120):
- `relevance_score` must be in [0.0, 1.0] → `ValueError`

**State machine transition tables** (defined in `persistence.py`, lines ~40–80):
- `INCIDENT_STATUS_TRANSITIONS` — but NOT enforced in the `Incident` dataclass itself (no transition validation method). The tables exist as documentation; enforcement must happen in a domain service.
- `REMEDIATION_STATUS_TRANSITIONS` — same pattern: tables defined but no `Remediation` aggregate method enforcing them.

**QUALITY GAP:** Transition tables are defined but no domain service enforces them. The `Incident` mutable projection does not validate `status` transitions. A domain service or the `IncidentStorePort.update_projection()` should enforce `INCIDENT_STATUS_TRANSITIONS[current_status]` before accepting a new status.

---

## 6. Redis Streams Tests

**File:** `tests/unit/adapters/events/test_redis_streams_event_bus.py`  
**Test library:** `fakeredis.aioredis` (no real Redis — skips if `fakeredis` not installed)  
**Acceptance criteria covered:** AC-4.1 through AC-4.7, AC-F3.2, AC-F3.5, AC-F4.1, AC-F4.2, AC-F9.5, AC-F9.7

### Test List (32 total):

**Contract (AC-4.6):**
- `test_implements_event_bus_port` — RedisStreamsEventBus isinstance(EventBus)

**publish (AC-4.1, AC-4.7):**
- `test_publish_writes_to_stream` — XADD to correct stream, entry count = 1
- `test_publish_uses_correct_stream_key_format` — key is `{prefix}:{event_type}`
- `test_publish_multiple_events_distinct_streams` — different event types → separate streams

**subscribe (AC-4.2):**
- `test_subscribe_creates_consumer_group` — XGROUP CREATE MKSTREAM, handler registered

**start() (AC-F3.2, AC-F3.5):**
- `test_start_clears_pending_readers_and_stores_task_group` — pending_readers cleared, task_group stored, one reader spawned per subscription

**Late subscription (AC-F4.1, AC-F4.2):**
- `test_late_subscribe_spawns_reader_immediately` — subscribe() after start() spawns immediately, does NOT go to _pending_readers

**unsubscribe (AC-4.4):**
- `test_unsubscribe_removes_handler` — handler removed from _handlers

**Handler error isolation (AC-4.5):**
- `test_handler_exception_does_not_crash_dispatch` — failing handler logged, good handler still runs
- `test_dispatch_does_not_ack_on_handler_failure` — _ack NOT called when handler raises
- `test_dispatch_acks_when_all_handlers_succeed` — _ack called once when all succeed
- `test_dispatch_does_not_ack_when_one_of_many_handlers_fails` — any handler failure → no ACK

**Event identity preservation (AC-F9.5, AC-F9.7):**
- `test_dispatch_preserves_event_id_from_stream` — original UUID from stream payload preserved
- `test_dispatch_preserves_timestamp_from_stream` — original ISO timestamp from stream preserved

**Stream lag observability:**
- `test_extract_pending_count_supports_multiple_xpending_shapes` — handles dict, tuple, int, invalid formats
- `test_observe_stream_lag_sets_metric` — REDIS_STREAM_LAG.labels(stream, group).set(count) called with correct values

**QUALITY GAPS in test coverage:**
- No test for `_drain_pending()` behavior on restart (PEL drain before reading new messages)
- No test for `claim_idle_ms` / XAUTOCLAIM dead-letter recovery path
- No test for wildcard `"*"` subscription routing
- No test for `run_readers()` backward-compatibility method
- No test for malformed message ACK behavior (JSON decode failure path)
- No integration test for actual at-least-once redelivery across simulated crash/restart

---

## 7. Multi-Agent Coordination — Persistence Angle

**File:** `docs/architecture/multi-agent-coordination.md`

This document is the operational mapping of `AGENTS.md` policy to implementation. Key persistence-relevant findings:

**Lock state persistence:** Each lock request writes structured JSON to Redis. TTL expiration invalidates ownership without relying on process liveness — meaning Redis IS the lock state store. Locks are ephemeral (TTL-backed), not durably persisted to PostgreSQL. The durable audit trail is separate via `CoordinationAuditPort`.

**Cooldown state persistence:** After action completion, agent writes a cooldown key to Redis. Cooldown blocks repeated action on same resource. Key formats:
- Kubernetes: `cooldown:{namespace}:{resource_type}:{resource_name}`
- Non-K8s (Phase 1.5): `cooldown:{provider}:{compute_mechanism}:{resource_id}`

**Fencing tokens:** Monotonic, carried in lock payload and action execution context. Stale token operations rejected by lock-aware executors. TTL expiry invalidates the lock.

**Human supremacy:** When human intervention detected on a resource, all autonomous agents back off. This must be persisted via `OverrideAuditEntry` (ADR-006 wave 1 scope).

**What is NOT explicitly addressed in this doc:** The document does not specify how revocation events are published or persisted (they are Redis pub/sub in the lock manager but there is no explicit mention of durable revocation audit records).

**QUALITY GAP:** The multi-agent coordination doc mentions revocation events (via pub/sub) but the `CoordinationAuditPort` has `record_lock_event(action="revoke")` — it is unclear if preemption/revocation is wired to call `CoordinationAuditPort` in the current implementation or only lives in the lock manager's Redis key lifecycle.

---

## 8. Engineering Standards — Persistence-Related

**File:** `docs/project/standards/engineering_standards.md`

### §2.2 Domain-Driven Design

- Value objects must be immutable (`frozen=True`) — applies to IncidentEvent, CoordinationAuditEntry, DiagnosisResult, EvidenceCitation (all correctly frozen).
- Domain events are fire-and-forget — producer must not depend on consumers.
- DomainEvent defined as frozen dataclass — the EventBus port decouples producers from consumers.

### §2.4 Event Sourcing & CQRS

- Every state transition is recorded as an immutable `DomainEvent` via `EventStore` port.
- The event log is the single source of truth for incident lifecycle reconstruction.
- **CQRS:** Commands (write-side) emit events; queries (read-side) read from state projection.
- **QUALITY GAP:** `EventStore` port is defined but has no concrete adapter implementation; the engineering standard mandates it as the primary audit mechanism.

### §2.5 Twelve-Factor App (Factor VI — Processes)

- "The agent runs as a stateless process; state is externalized to Redis (locks), PostgreSQL (phase state), and event stores."
- This directly mandates persistence: agent is not permitted to hold state in memory across restarts.

### §3 Cloud Design Patterns (Table)

| Pattern | Status |
|---|---|
| Event Sourcing | Implemented (via EventStore port) |
| CQRS | Implemented (write/read separation) |
| Saga | Planned (Phase 3 — remediation with compensating transactions) |
| Leader Election | Planned (Phase 3 — distributed lock manager) |
| Throttling | Planned (Phase 3 — cooling-off periods) |
| Compensating Transaction | Planned (Phase 3 — auto-rollback) |

### §7.4 Coverage Requirements

| Scope | Minimum Coverage |
|---|---|
| domain/ package | 100% line coverage |
| adapters/ package | 90% line coverage |
| api/ package | 85% line coverage |
| Global | 90% line coverage |

---

## 9. VectorDocument

**Location:** `src/sre_agent/ports/vector_store.py` (lines 27–37) — NOT in `domain/models/`

**QUALITY GAP:** `VectorDocument` lives in `ports/`. Per engineering standards §2.3 (hexagonal), ports should contain only ABCs and type definitions. Having a concrete data type in ports is borderline — but it is a frozen dataclass (value object), not business logic. The ADR-002 question applies: should this be Pydantic?

```python
@dataclass(frozen=True)
class VectorDocument:
    doc_id: str
    content: str
    embedding: list[float]
    metadata: dict[str, str] = field(default_factory=dict)
    source: str = ""
    created_at: datetime | None = None
```

**Used by:**
- `src/sre_agent/adapters/vectordb/pgvector/adapter.py` (lines 58, 343, 390)
- `src/sre_agent/adapters/vectordb/chroma/adapter.py` (lines 21, 70, 84)
- `src/sre_agent/domain/diagnostics/ingestion.py` (lines 18, 66, 68) ← domain imports from ports ✓ (correct direction)

---

## 10. Persistence Ports Summary

**File:** `src/sre_agent/ports/persistence.py`

Ports defined (all ABCs):

| Port | Description |
|---|---|
| `CoordinationAuditPort` | Lock, cooldown, override durable audit trail |
| `IncidentStorePort` | Incident event sourcing + mutable projection |
| `OutboxPort` | Transactional outbox for reliable stream publication |
| `DiagnosisStorePort` | Durable diagnosis result persistence |
| `ReasoningTracePort` | Phase 3 reasoning trace (run, tool call, retrieved context) |

**Exceptions defined:**
- `DuplicateEventError` — idempotency key already exists (treat as safe no-op)
- `StaleProjectionError` — optimistic concurrency failure on projection update

**Key DTOs in ports/persistence.py (frozen dataclasses):**
- `LockAuditEntry` — actor, action, provider, compute_mechanism, resource_id, lock_priority, fencing_token
- `CooldownAuditEntry` — actor, action, provider, compute_mechanism, resource_id
- `OverrideAuditEntry` — actor, action, provider, compute_mechanism, resource_id, `audit_required: bool = True`
- `CoordinationAuditRecord` — persisted form with audit_id, created_at, details_json
- `IncidentEventRecord` — event_id, incident_id, event_type, occurred_at, provider, compute_mechanism, resource_id, payload_json, idempotency_key, correlation_key
- `IncidentRecord` — incident projection (mutable)
- `DiagnosisResultRecord` — diagnosis_id, incident_id, diagnosis_summary, confidence_score, evidence_refs, generated_at, model_name
- `ReasoningRunRecord` — run_id, incident_id, agent_id, started_at, ended_at, outcome, metadata_json
- `ToolCallTraceRecord` — call_id, run_id, tool_name, input_json, output_json, latency_ms, status, called_at
- `RetrievedContextRecord` — context_id, run_id, doc_id, similarity_score, content_snippet, source, retrieved_at

---

## 11. Consolidated Quality Gaps

| Gap ID | Location | Description | Severity |
|---|---|---|---|
| QG-01 | `domain/models/canonical.py`, `diagnosis.py`, `persistence.py`, `detection_config.py` | All domain models use `@dataclass` / StrEnum but ADR-002 mandates Pydantic `BaseModel`. No model has been migrated. | High |
| QG-02 | `ports/events.py` (EventStore ABC) | `EventStore` port defined but no adapter implements it. Engineering Standards §2.4 mandates it as the primary audit mechanism. | High |
| QG-03 | `domain/models/persistence.py` | `INCIDENT_STATUS_TRANSITIONS` and `REMEDIATION_STATUS_TRANSITIONS` tables exist but no domain aggregate or service enforces them. Status transitions are unguarded. | Medium |
| QG-04 | `tests/unit/adapters/events/test_redis_streams_event_bus.py` | No tests for `_drain_pending()` (PEL restart recovery), XAUTOCLAIM dead-letter path, wildcard `"*"` subscriptions, malformed message ACK, or `run_readers()` backward compat. | Medium |
| QG-05 | `ports/vector_store.py` | `VectorDocument` is a concrete data type living in `ports/` rather than `domain/models/`. Minor architectural placement issue. | Low |
| QG-06 | `docs/architecture/multi-agent-coordination.md` | Revocation events mentioned but it is unclear if preemption/revocation records are wired to call `CoordinationAuditPort` or only handled by Redis TTL expiry. | Medium |
| QG-07 | `src/sre_agent/domain/models/persistence.py` | `OutboxPort.refresh_backlog_metrics` is referenced in the `FakeOutbox` test double but is not defined in the `OutboxPort` ABC in `ports/persistence.py`. Interface may be incomplete. | Low |

---

## 12. Key File Path and Line Number Index

| Symbol | File | Lines |
|---|---|---|
| `RedisStreamsEventBus` class | `src/sre_agent/adapters/events/redis_streams_event_bus.py` | 52–523 |
| `EventBus` ABC | `src/sre_agent/ports/events.py` | 23–65 |
| `EventStore` ABC | `src/sre_agent/ports/events.py` | 68–100 |
| `DomainEvent` | `src/sre_agent/domain/models/canonical.py` | ~401–420 |
| `EventTypes` | `src/sre_agent/domain/models/canonical.py` | ~422–450 |
| `AnomalyAlert` | `src/sre_agent/domain/models/canonical.py` | ~352–400 |
| `IncidentEvent` (domain) | `src/sre_agent/domain/models/persistence.py` | ~120–155 |
| `IncidentStatus` + transitions | `src/sre_agent/domain/models/persistence.py` | ~25–50 |
| `RemediationStatus` + transitions | `src/sre_agent/domain/models/persistence.py` | ~55–80 |
| `CoordinationAuditEntry` | `src/sre_agent/domain/models/persistence.py` | ~190–225 |
| `DiagnosisResult` (domain) | `src/sre_agent/domain/models/persistence.py` | ~160–175 |
| `RemediationAction` (domain) | `src/sre_agent/domain/models/persistence.py` | ~178–195 |
| `OutboxEntry` | `src/sre_agent/domain/models/persistence.py` | ~200–215 |
| `Diagnosis` | `src/sre_agent/domain/models/diagnosis.py` | ~195–235 |
| `ImpactDimensions` | `src/sre_agent/domain/models/diagnosis.py` | ~125–175 |
| `VectorDocument` | `src/sre_agent/ports/vector_store.py` | 27–37 |
| `IncidentStorePort` | `src/sre_agent/ports/persistence.py` | ~180–250 |
| `OutboxPort` | `src/sre_agent/ports/persistence.py` | ~255–400 |
| `CoordinationAuditPort` | `src/sre_agent/ports/persistence.py` | ~115–180 |
| `LockAuditEntry` | `src/sre_agent/ports/persistence.py` | ~45–58 |
| `ADR-006` | `docs/project/ADRs/006-persistence-authority-reconciliation.md` | Full file |
| `DetectionConfig` | `src/sre_agent/domain/models/detection_config.py` | 1–50 |
| `ConfidenceLevel` | `src/sre_agent/domain/models/diagnosis.py` | ~65–90 |
| Redis Streams tests | `tests/unit/adapters/events/test_redis_streams_event_bus.py` | 1–550+ |
| Engineering standards (persistence) | `docs/project/standards/engineering_standards.md` | §2.4, §7.4 |
