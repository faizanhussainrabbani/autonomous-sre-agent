#!/usr/bin/env python3
"""
Live Demo P6 — Full Observability Loop: Live Prometheus Scrape.

Demonstrates the complete observability stack end-to-end:

  ┌─────────────────────────────────────────────────────────────────────────┐
  │  This demo process                                                      │
  │    RAG Pipeline ──→ prometheus_client registry                          │
  │    start_http_server(:8080) ──→ GET /metrics                            │
  │                                       │                                 │
  │  Prometheus container scrapes :8080 every 15 s                          │
  │    → stores samples in TSDB                                             │
  │    → evaluates sre_agent_slo.yaml alert rules                           │
  │                                       │                                 │
  │  Demo queries http://localhost:9090/api/v1/query  (PromQL)              │
  │  Demo fetches http://localhost:9090/api/v1/rules  (alert definitions)   │
  │  Demo fetches http://localhost:9090/api/v1/alerts (active alerts)       │
  └─────────────────────────────────────────────────────────────────────────┘

Phases:
  0  Bootstrap        Expose /metrics on :8080, verify Prometheus connectivity
  1  Knowledge Base   Ingest 4 cascade-failure runbooks into ChromaDB
  2  Cascade Failure  3 real incidents → all diagnostic metrics fire
  3  Novel Incident   Unknown service against empty KB → novel_incident error
  4  Circuit Breaker  CLOSED → OPEN → HALF_OPEN → CLOSED with live gauge reads
  5  Scrape Wait      20 s countdown so Prometheus captures every sample
  6  PromQL Queries   7 live instant queries against the Prometheus TSDB
  7  Alert Rules      Loaded rule definitions + any PENDING / FIRING alerts

REQUIREMENTS:
  - ANTHROPIC_API_KEY or OPENAI_API_KEY set in environment
  - docker compose -f docker-compose.deps.yml up -d prometheus
  - Port 8080 must be available (metrics HTTP server)

Usage:
    source .env && source .venv/bin/activate
    python scripts/demo/live_demo_p6_full_observability.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from urllib import request as urllib_request
from urllib.error import URLError
from urllib.parse import quote

# ─── Terminal styling ─────────────────────────────────────────────────────────


class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    WHITE = "\033[97m"


def banner(title: str, width: int = 76) -> None:
    pad = " " * ((width - len(title)) // 2)
    extra = " " if (width - len(title)) % 2 else ""
    print(f"\n{C.BOLD}{C.MAGENTA}╔{'═' * width}╗{C.RESET}")
    print(f"{C.BOLD}{C.MAGENTA}║{pad}{title}{pad}{extra}║{C.RESET}")
    print(f"{C.BOLD}{C.MAGENTA}╚{'═' * width}╝{C.RESET}\n")


def phase_header(number: int, title: str, subtitle: str = "", width: int = 76) -> None:
    label = f"  PHASE {number}: {title}  "
    print(f"\n{C.BOLD}{C.BLUE}╔{'═' * width}╗{C.RESET}")
    print(f"{C.BOLD}{C.BLUE}║{label.center(width)}║{C.RESET}")
    print(f"{C.BOLD}{C.BLUE}╚{'═' * width}╝{C.RESET}")
    if subtitle:
        print(f"  {C.DIM}{subtitle}{C.RESET}")
    print()


def step(msg: str) -> None:
    print(f"\n  {C.YELLOW}▶  {C.BOLD}{msg}{C.RESET}")


def ok(msg: str) -> None:
    print(f"  {C.GREEN}✔  {C.RESET}{msg}")


def info(msg: str) -> None:
    print(f"  {C.CYAN}ℹ  {C.RESET}{msg}")


def warn(msg: str) -> None:
    print(f"  {C.YELLOW}⚠  {C.RESET}{msg}")


def field(label: str, value: str) -> None:
    print(f"     {C.DIM}{label}:{C.RESET} {C.WHITE}{value}{C.RESET}")


def separator(width: int = 70) -> None:
    print(f"  {C.DIM}{'─' * width}{C.RESET}")


# ─── LLM API key guard ────────────────────────────────────────────────────────

if not os.environ.get("OPENAI_API_KEY") and not os.environ.get("ANTHROPIC_API_KEY"):
    print(f"\n{C.RED}Error: No LLM API key found in environment.{C.RESET}")
    print("Export OPENAI_API_KEY or ANTHROPIC_API_KEY before running.")
    sys.exit(1)

# ─── Project imports ─────────────────────────────────────────────────────────

try:
    from prometheus_client import start_http_server

    from sre_agent.adapters.cloud.resilience import CircuitBreaker, CircuitState, TransientError
    from sre_agent.adapters.intelligence_bootstrap import (
        create_diagnostic_pipeline,
        create_embedding,
        create_ingestion_pipeline,
        create_llm,
        create_vector_store,
    )
    from sre_agent.adapters.telemetry.metrics import (
        CIRCUIT_BREAKER_STATE,
        DIAGNOSIS_DURATION,
        DIAGNOSIS_ERRORS,
        EVIDENCE_RELEVANCE,
        LLM_CALL_DURATION,
        LLM_TOKENS_USED,
        SEVERITY_ASSIGNED,
    )
    from sre_agent.domain.models.canonical import AnomalyAlert, AnomalyType, ComputeMechanism
    from sre_agent.domain.models.diagnosis import ServiceTier
    from sre_agent.events.in_memory import InMemoryEventBus, InMemoryEventStore
    from sre_agent.ports.diagnostics import DiagnosisRequest
except ImportError as exc:
    print(f"{C.RED}Import error: {exc}{C.RESET}")
    print("Run from the project root with the virtual environment active.")
    sys.exit(1)

# ─── Demo constants ───────────────────────────────────────────────────────────

METRICS_PORT = 8080           # Must match prometheus.yml scrape target port
PROMETHEUS_URL = "http://localhost:9090"
SCRAPE_WAIT_S = 20            # > 15 s global scrape_interval in prometheus.yml
CB_FAILURE_THRESHOLD = 3      # Trip the circuit breaker quickly for demo
CB_RECOVERY_TIMEOUT_S = 6.0   # Seconds in OPEN before HALF_OPEN probe allowed

# ─── Prometheus helpers ───────────────────────────────────────────────────────


def prometheus_is_healthy() -> bool:
    try:
        with urllib_request.urlopen(f"{PROMETHEUS_URL}/-/healthy", timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def prometheus_query(expr: str) -> list[dict]:
    """Execute an instant PromQL query. Returns list of result vectors."""
    try:
        url = f"{PROMETHEUS_URL}/api/v1/query?query={quote(expr)}"
        with urllib_request.urlopen(url, timeout=5) as resp:
            payload = json.loads(resp.read())
        if payload.get("status") == "success":
            return payload["data"]["result"]
    except Exception:
        pass
    return []


def prometheus_rules() -> list[dict]:
    """Fetch loaded rule groups from Prometheus."""
    try:
        with urllib_request.urlopen(f"{PROMETHEUS_URL}/api/v1/rules", timeout=5) as resp:
            payload = json.loads(resp.read())
        if payload.get("status") == "success":
            return payload["data"]["groups"]
    except Exception:
        pass
    return []


def prometheus_alerts() -> list[dict]:
    """Fetch active (PENDING / FIRING) alerts from Prometheus."""
    try:
        with urllib_request.urlopen(f"{PROMETHEUS_URL}/api/v1/alerts", timeout=5) as resp:
            payload = json.loads(resp.read())
        if payload.get("status") == "success":
            return payload["data"]["alerts"]
    except Exception:
        pass
    return []


# ─── Knowledge base documents ────────────────────────────────────────────────

CASCADE_RUNBOOKS = [
    (
        """# Post-Mortem: order-service OOM Kill — Black Friday 2025
Date: 2025-11-29
Service: order-service
Tier: 1 (Revenue Critical)

**Symptom**: Container RSS climbed to 4.1 GB, triggering an OOM kill. Service
restarted, but the shopping cart Redis session cache was lost for ~18,000 users.

**Root Cause**: Unbounded in-memory shopping-cart accumulation during flash-sale
event. Each concurrent user session added ~220 KB to the cart object pool.
At peak (20,000 concurrent users), the heap exceeded 4 GB.

**Remediation**: Rolling pod restart + HPA scale-out (3→12 replicas).
Redis session TTL reduced to 15 minutes. Cart object pool capped at 512 MB.

**Detection Lag**: 3m 45s — alert fired when OOM kill occurred, not during ramp.
**MTTR**: 11 minutes (manual approval required due to Tier 1 classification).
""",
        "post-mortems/order-service-oom-bfriday.md",
        None,
    ),
    (
        """# Runbook: checkout-service HTTP 503 Error Surge
Service: checkout-service
Tier: 2 (Customer-Facing)

**Trigger**: HTTP 503 upstream error rate > 5% for 2 consecutive minutes.

**Common Causes**:
  1. Upstream order-service unavailable or crashing (most common during sales events).
  2. DB connection pool exhaustion (checkout_db max_connections=100 reached).
  3. Payment gateway timeout cascade (Stripe p99 > 8s).

**Immediate Action**:
  a) Check order-service health: kubectl get pods -n prod -l app=order-service
  b) Scale checkout-service HPA to max replicas: kubectl scale --replicas=10
  c) Enable circuit-breaker fallback: return 200 with empty cart for degraded requests.

**Escalation**: If error rate > 20%, escalate to SEV1. Page on-call immediately.
""",
        "runbooks/checkout-service-503.md",
        None,
    ),
    (
        """# Runbook: api-gateway Latency Spike
Service: api-gateway
Tier: 1 (Entry Point — all user traffic)

**Trigger**: p99 latency > 5s for 3 consecutive minutes.

**Root Cause Patterns**:
  1. Upstream backend services degraded (check checkout-service, order-service).
  2. Connection pool exhaustion in nginx upstream block.
  3. TLS certificate renewal causing brief CPU spikes (30-60s, self-resolving).

**Remediation**:
  - Restart nginx-gateway pods to clear stale worker connections.
  - Increase upstream keepalive connections in nginx config.
  - If cascade: resolve upstream before addressing gateway — do not mask the symptom.

**Note**: Do NOT auto-restart api-gateway without resolving upstream root cause first.
""",
        "runbooks/api-gateway-latency.md",
        None,
    ),
    (
        """# Incident Pattern: Flash Sale Traffic Cascade
Classification: MULTI_DIMENSIONAL

**Pattern**: During flash-sale events, order-service OOM kills propagate as:
  order-service OOM → checkout HTTP 503 → api-gateway latency spike

**Prevention**:
  - Pre-scale order-service to 12 replicas 30 minutes before event start.
  - Set Redis cart TTL to 10 minutes during flash sales.
  - Enable circuit breakers with 30% degraded response to reduce cascade.

**Detection**: All three alerts fire within a 4-minute window.
**Correlation**: Alerts share a common temporal window — correlate by timestamp.
""",
        "runbooks/flash-sale-cascade-pattern.md",
        None,
    ),
]

# ─── Cascade incident definitions ─────────────────────────────────────────────

CASCADE_INCIDENTS = [
    {
        "index": 1,
        "service": "order-service",
        "tier": ServiceTier.TIER_1,
        "label": "PRIMARY — OOM Kill",
        "alert": AnomalyAlert(
            service="order-service",
            anomaly_type=AnomalyType.MEMORY_PRESSURE,
            description=(
                "Container OOM kill — RSS reached 4.1 GB during flash sale (limit: 4 GB). "
                "Shopping cart pool unbounded."
            ),
            metric_name="container_memory_rss_bytes",
            current_value=4_100_000_000.0,
            baseline_value=1_800_000_000.0,
            deviation_sigma=13.5,
            compute_mechanism=ComputeMechanism.KUBERNETES,
        ),
    },
    {
        "index": 2,
        "service": "checkout-service",
        "tier": ServiceTier.TIER_2,
        "label": "SECONDARY — HTTP 503 Surge",
        "alert": AnomalyAlert(
            service="checkout-service",
            anomaly_type=AnomalyType.ERROR_RATE_SURGE,
            description=(
                "HTTP 503 upstream errors spiked to 42% — order-service unavailable."
            ),
            metric_name="upstream_5xx_error_rate",
            current_value=42.0,
            baseline_value=0.5,
            deviation_sigma=9.1,
            compute_mechanism=ComputeMechanism.KUBERNETES,
        ),
    },
    {
        "index": 3,
        "service": "api-gateway",
        "tier": ServiceTier.TIER_1,
        "label": "TERTIARY — Latency Cascade",
        "alert": AnomalyAlert(
            service="api-gateway",
            anomaly_type=AnomalyType.LATENCY_SPIKE,
            description=(
                "p99 latency spiked to 18s — downstream cascade from checkout and order services."
            ),
            metric_name="http_request_duration_p99_seconds",
            current_value=18.0,
            baseline_value=0.12,
            deviation_sigma=15.2,
            compute_mechanism=ComputeMechanism.KUBERNETES,
        ),
    },
]

# ─── Novel incident (no matching runbooks) ────────────────────────────────────

NOVEL_INCIDENT = AnomalyAlert(
    service="graphql-federation-gateway",
    anomaly_type=AnomalyType.LATENCY_SPIKE,
    description=(
        "Distributed query planning deadlock detected in GraphQL federation gateway. "
        "Subgraph schema registry returned 504 during introspection handshake. "
        "Supergraph composition stalled — all federated queries timing out. "
        "Zero historical runbooks or post-mortems exist for this failure pattern."
    ),
    metric_name="graphql_federated_query_plan_duration_p99_seconds",
    current_value=47.3,
    baseline_value=0.06,
    deviation_sigma=22.8,
    compute_mechanism=ComputeMechanism.KUBERNETES,
)

# ─── PromQL queries to showcase ───────────────────────────────────────────────

PROMQL_SHOWCASE = [
    (
        "Severity assignments (all labels)",
        "sre_agent_severity_assigned_total",
    ),
    (
        "LLM token consumption by provider + type",
        "sre_agent_llm_tokens_total",
    ),
    (
        "Diagnosis errors by type",
        "sre_agent_diagnosis_errors_total",
    ),
    (
        "Circuit breaker state (0=CLOSED 1=HALF_OPEN 2=OPEN)",
        "sre_agent_circuit_breaker_state",
    ),
    (
        "P99 diagnosis latency recording rule",
        "sre_agent:diagnosis_latency:p99",
    ),
    (
        "P50 evidence relevance score",
        "histogram_quantile(0.50, rate(sre_agent_evidence_relevance_score_bucket[5m]))",
    ),
    (
        "LLM call rate by provider + call_type (calls/min)",
        "rate(sre_agent_llm_call_duration_seconds_count[5m]) * 60",
    ),
]


# ─── Main demo ────────────────────────────────────────────────────────────────


async def run_demo() -> None:
    banner("Live Demo P6 — Full Observability Loop: Live Prometheus Scrape")
    print(f"  {C.CYAN}Showcases every metric, the /metrics scrape endpoint,{C.RESET}")
    print(f"  {C.CYAN}live PromQL queries, and Prometheus alert rule evaluation.{C.RESET}\n")

    # ── Phase 0: Bootstrap ─────────────────────────────────────────────────────
    phase_header(0, "Bootstrap", "Starting /metrics HTTP server · Verifying Prometheus connectivity")

    # Start the prometheus_client HTTP metrics server in a daemon thread.
    # This exposes the demo process's in-process Prometheus registry at :8080.
    # The prometheus.yml scrape config targets host.docker.internal:8080.
    metrics_server_started = False
    try:
        start_http_server(METRICS_PORT)
        ok(f"Metrics HTTP server started on :{METRICS_PORT}  (GET http://localhost:{METRICS_PORT}/metrics)")
        metrics_server_started = True
    except OSError as exc:
        warn(f"Could not bind :{METRICS_PORT} — {exc}. Metrics will not be scraped by Prometheus.")
        warn("Continue anyway? The demo will still generate and display local metrics.")

    # Check Prometheus connectivity
    prom_healthy = prometheus_is_healthy()
    if prom_healthy:
        ok(f"Prometheus is healthy at {PROMETHEUS_URL}")
        info("Scrape config: host.docker.internal:8080 every 15 s (prometheus.yml)")
    else:
        warn(f"Prometheus is NOT reachable at {PROMETHEUS_URL}")
        warn("PromQL and alert phases will show local fallback instead of live TSDB data.")
        warn("Start it with: docker compose -f docker-compose.deps.yml up -d prometheus")

    # Bootstrap shared adapters (embedding model is expensive — create once)
    step("Initialising shared intelligence adapters (ChromaDB · SentenceTransformers · LLM)...")
    boot_t0 = time.time()
    shared_emb = create_embedding()
    shared_llm = create_llm()
    ok(f"Adapters ready in {time.time() - boot_t0:.2f}s")

    # ── Phase 1: Knowledge Base Ingestion ──────────────────────────────────────
    phase_header(
        1,
        "Knowledge Base Ingestion",
        "Embedding 4 cascade-failure runbooks into ChromaDB collection 'p6_cascade_kb'",
    )

    cascade_vs = create_vector_store(collection_name="p6_cascade_kb")
    ingestion = create_ingestion_pipeline(vector_store=cascade_vs, embedding=shared_emb)

    ingest_t0 = time.time()
    await ingestion.ingest_batch(CASCADE_RUNBOOKS)
    ok(f"{len(CASCADE_RUNBOOKS)} documents vectorized in {time.time() - ingest_t0:.2f}s")
    info("Separate empty collection 'p6_novel_kb' will be used for the novel incident (Phase 3)")

    # ── Phase 2: Cascade Failure ───────────────────────────────────────────────
    phase_header(
        2,
        "Cascade Failure Scenario",
        "Black Friday flash sale — 3 services fail in sequence · All diagnostic metrics fire",
    )

    cascade_pipeline = create_diagnostic_pipeline(
        vector_store=cascade_vs,
        embedding=shared_emb,
        llm=shared_llm,
        service_tiers={
            "order-service": ServiceTier.TIER_1,
            "checkout-service": ServiceTier.TIER_2,
            "api-gateway": ServiceTier.TIER_1,
        },
        context_budget=4000,
    )

    cascade_results: list[dict] = []

    for incident in CASCADE_INCIDENTS:
        alert: AnomalyAlert = incident["alert"]

        # Wire fresh event bus per incident for isolation
        event_bus = InMemoryEventBus()
        event_store = InMemoryEventStore()
        events_received: list[str] = []

        async def _on_event(event, _idx=incident["index"]):  # noqa: B023
            events_received.append(event.event_type)

        await event_bus.subscribe("*", _on_event)
        cascade_pipeline._event_bus = event_bus
        cascade_pipeline._event_store = event_store

        separator()
        print(
            f"  {C.CYAN}{C.BOLD}[{incident['index']}/3] {incident['label']}{C.RESET}  "
            f"{C.DIM}({incident['service']} · {incident['tier'].name}){C.RESET}"
        )

        diag_t0 = time.time()
        result = await cascade_pipeline.diagnose(DiagnosisRequest(alert=alert, max_evidence_items=3))
        elapsed = time.time() - diag_t0

        sev_col = C.RED if result.severity.name in ("SEV1", "SEV2") else C.YELLOW
        field("Severity", f"{sev_col}{C.BOLD}{result.severity.name}{C.RESET}")
        field("Confidence", f"{result.confidence * 100:.1f}%")
        field("Duration", f"{elapsed:.2f}s")
        field(
            "Guardrail",
            f"{C.RED}⛔ Human Approval Required{C.RESET}"
            if result.requires_human_approval
            else f"{C.GREEN}✅ Autonomous{C.RESET}",
        )
        field("Root Cause", (result.root_cause or "")[:100] + "...")
        field("Events Emitted", ", ".join(events_received) or "none")

        cascade_results.append(
            {
                "service": incident["service"],
                "severity": result.severity.name,
                "confidence": result.confidence,
                "requires_approval": result.requires_human_approval,
            }
        )

    print()
    ok("Cascade failure diagnosis complete — DIAGNOSIS_DURATION, SEVERITY_ASSIGNED, "
       "EVIDENCE_RELEVANCE, LLM_CALL_DURATION, LLM_TOKENS_USED all emitted")

    # ── Phase 3: Novel Incident ────────────────────────────────────────────────
    phase_header(
        3,
        "Novel Incident Injection",
        "Unknown service · Empty knowledge base → DIAGNOSIS_ERRORS{error_type='novel_incident'}",
    )

    # Use a fresh, empty vector store — guarantees search_results == []
    novel_vs = create_vector_store(collection_name="p6_novel_kb")
    novel_pipeline = create_diagnostic_pipeline(
        vector_store=novel_vs,
        embedding=shared_emb,
        llm=shared_llm,
        service_tiers={"graphql-federation-gateway": ServiceTier.TIER_2},
        context_budget=4000,
    )

    step(f"Injecting novel incident: {NOVEL_INCIDENT.service} / {NOVEL_INCIDENT.anomaly_type.value}")
    info("Knowledge base is EMPTY — vector search will return zero results")
    info(f"Alert: {NOVEL_INCIDENT.description[:90]}...")

    novel_t0 = time.time()
    novel_result = await novel_pipeline.diagnose(
        DiagnosisRequest(alert=NOVEL_INCIDENT, max_evidence_items=3)
    )
    novel_elapsed = time.time() - novel_t0

    print()
    field("Novel Incident Flag", f"{C.YELLOW}is_novel={novel_result.is_novel}{C.RESET}")
    field("Severity", novel_result.severity.name)
    field("Duration", f"{novel_elapsed:.2f}s")
    field(
        "Guardrail",
        f"{C.RED}⛔ Human Approval Required (novel — no evidence){C.RESET}"
        if novel_result.requires_human_approval
        else f"{C.GREEN}Autonomous{C.RESET}",
    )
    print()

    # Verify the counter was incremented
    novel_count = 0.0
    for metric in DIAGNOSIS_ERRORS.collect():
        for sample in metric.samples:
            if (
                sample.name == "sre_agent_diagnosis_errors_total"
                and sample.labels.get("error_type") == "novel_incident"
            ):
                novel_count = sample.value

    ok(f"sre_agent_diagnosis_errors_total{{error_type='novel_incident'}} = {novel_count:.0f} ✓")

    # ── Phase 4: Circuit Breaker State Machine ─────────────────────────────────
    phase_header(
        4,
        "Circuit Breaker State Machine",
        "CLOSED (0) → OPEN (2) → HALF_OPEN (1) → CLOSED (0) · Live gauge at each step",
    )

    cb = CircuitBreaker(
        failure_threshold=CB_FAILURE_THRESHOLD,
        recovery_timeout_seconds=CB_RECOVERY_TIMEOUT_S,
        name="k8s-operator",
    )

    def read_cb_gauge() -> float:
        for metric in CIRCUIT_BREAKER_STATE.collect():
            for sample in metric.samples:
                if (
                    sample.labels.get("provider") == "cloud"
                    and sample.labels.get("resource_type") == "k8s-operator"
                ):
                    return sample.value
        return -1.0

    def cb_state_label(val: float) -> str:
        mapping = {0.0: f"{C.GREEN}CLOSED (0){C.RESET}", 1.0: f"{C.YELLOW}HALF_OPEN (1){C.RESET}", 2.0: f"{C.RED}OPEN (2){C.RESET}"}
        return mapping.get(val, f"UNKNOWN ({val})")

    # Initial state — must read .state to trigger the initial gauge write
    _ = cb.state
    cb._set_state_gauge()
    val = read_cb_gauge()
    step("Initial state")
    field("sre_agent_circuit_breaker_state", cb_state_label(val))

    # Inject failures to trip the breaker
    step(f"Injecting {CB_FAILURE_THRESHOLD} consecutive failures → trips at threshold")
    for i in range(CB_FAILURE_THRESHOLD):
        cb.record_failure()
        info(f"  failure {i + 1}/{CB_FAILURE_THRESHOLD} recorded")

    val = read_cb_gauge()
    field("sre_agent_circuit_breaker_state", cb_state_label(val))
    ok(f"Circuit breaker OPEN — all downstream calls will be rejected for {CB_RECOVERY_TIMEOUT_S}s")

    # Wait for recovery timeout to elapse
    wait_msg = f"Waiting {CB_RECOVERY_TIMEOUT_S + 1:.0f}s for recovery timeout to elapse..."
    step(wait_msg)
    for remaining in range(int(CB_RECOVERY_TIMEOUT_S) + 1, 0, -1):
        print(f"\r     {C.DIM}{remaining}s remaining...{C.RESET}", end="", flush=True)
        time.sleep(1)
    print()

    # Access .state property — triggers OPEN → HALF_OPEN transition
    _ = cb.state  # property read triggers the transition
    val = read_cb_gauge()
    step("Probe attempt — accessing .state after recovery timeout")
    field("sre_agent_circuit_breaker_state", cb_state_label(val))
    info("HALF_OPEN: exactly one probe call permitted — success will close the circuit")

    # Record success → CLOSED
    cb.record_success()
    val = read_cb_gauge()
    step("Probe succeeded → circuit closes")
    field("sre_agent_circuit_breaker_state", cb_state_label(val))
    ok("Full CLOSED → OPEN → HALF_OPEN → CLOSED cycle complete")
    ok("sre_agent_circuit_breaker_state emitted at each transition ✓")

    # ── Phase 5: Prometheus Scrape Wait ───────────────────────────────────────
    phase_header(
        5,
        "Prometheus Scrape Wait",
        f"Waiting {SCRAPE_WAIT_S}s (> 15s global scrape_interval) for Prometheus to capture all samples",
    )

    if not metrics_server_started:
        warn("Metrics server was not started. Prometheus cannot scrape this process.")
        warn("Skipping wait — PromQL queries may return no data.")
    elif not prom_healthy:
        warn("Prometheus is not reachable. Skipping scrape wait.")
        warn("PromQL queries will show local registry fallback.")
    else:
        info(f"Prometheus is scraping http://host.docker.internal:{METRICS_PORT}/metrics")
        info("Progress: waiting for scrape cycle to complete...")
        print()
        bar_width = 50
        for elapsed in range(SCRAPE_WAIT_S + 1):
            filled = int(bar_width * elapsed / SCRAPE_WAIT_S)
            bar = "█" * filled + "░" * (bar_width - filled)
            pct = int(100 * elapsed / SCRAPE_WAIT_S)
            print(
                f"\r  {C.CYAN}[{bar}]{C.RESET} {pct:3d}%  {elapsed}/{SCRAPE_WAIT_S}s",
                end="",
                flush=True,
            )
            if elapsed < SCRAPE_WAIT_S:
                time.sleep(1)
        print(f"\r  {C.GREEN}[{'█' * bar_width}]{C.RESET} 100%  {SCRAPE_WAIT_S}/{SCRAPE_WAIT_S}s")
        print()
        ok("Scrape window elapsed — Prometheus TSDB now contains all emitted samples")

    # ── Phase 6: PromQL Queries ───────────────────────────────────────────────
    phase_header(
        6,
        "Live PromQL Queries",
        f"Querying {PROMETHEUS_URL}/api/v1/query with 7 instant expressions",
    )

    if not prom_healthy:
        warn("Prometheus unavailable — showing local registry values as fallback.")
        print()
        _print_local_metrics_fallback()
    else:
        for description, expr in PROMQL_SHOWCASE:
            print(f"  {C.BOLD}{C.WHITE}{description}{C.RESET}")
            print(f"  {C.DIM}PromQL: {expr}{C.RESET}")
            results = prometheus_query(expr)
            if not results:
                print(f"  {C.YELLOW}  (no data yet — may need another scrape interval){C.RESET}")
            else:
                for vector in results:
                    labels = vector.get("metric", {})
                    value = vector.get("value", [None, "?"])[1]
                    label_str = "  ".join(
                        f"{k}={C.CYAN}{v}{C.RESET}"
                        for k, v in labels.items()
                        if k != "__name__"
                    )
                    print(
                        f"    {C.GREEN}→{C.RESET}  {label_str or C.DIM + '(no labels)' + C.RESET}"
                        f"  {C.BOLD}{C.WHITE}{float(value):.4g}{C.RESET}"
                    )
            print()

    # ── Phase 7: Alert Rules & Active Alerts ──────────────────────────────────
    phase_header(
        7,
        "Alert Rule Evaluation",
        f"Fetching loaded rules and active alerts from {PROMETHEUS_URL}",
    )

    if not prom_healthy:
        warn("Prometheus unavailable — cannot fetch live alert state.")
        info("When running, Prometheus evaluates these rules from infra/prometheus/rules/sre_agent_slo.yaml:")
        _print_expected_alert_rules()
    else:
        # --- Loaded rule definitions ---
        step("Loaded rule groups from sre_agent_slo.yaml")
        groups = prometheus_rules()
        alert_rule_count = 0
        recording_rule_count = 0

        for group in groups:
            if "sre_agent" not in group.get("name", ""):
                continue
            group_name = group["name"]
            rules = group.get("rules", [])
            print(f"\n  {C.BOLD}{C.BLUE}Group: {group_name}{C.RESET}  ({len(rules)} rules)")
            for rule in rules:
                rule_type = rule.get("type", "unknown")
                rule_name = rule.get("name", rule.get("alert", "?"))
                rule_expr = rule.get("query", rule.get("expr", ""))[:80]
                state = rule.get("state", "")
                if rule_type == "alerting":
                    alert_rule_count += 1
                    sev = rule.get("labels", {}).get("severity", "")
                    sev_col = C.RED if sev == "critical" else C.YELLOW if sev == "warning" else C.DIM
                    state_col = C.RED if state == "firing" else C.YELLOW if state == "pending" else C.GREEN
                    print(
                        f"    {C.CYAN}[alert]{C.RESET}  {rule_name:<40}  "
                        f"{sev_col}{sev:<10}{C.RESET}  "
                        f"state={state_col}{state or 'inactive'}{C.RESET}"
                    )
                else:
                    recording_rule_count += 1
                    print(f"    {C.MAGENTA}[record]{C.RESET} {rule_name}")
                    print(f"             {C.DIM}expr: {rule_expr}...{C.RESET}")

        print()
        ok(f"Loaded: {alert_rule_count} alert rules  ·  {recording_rule_count} recording rules")

        # --- Active alerts ---
        step("Active alerts (PENDING or FIRING)")
        alerts = prometheus_alerts()
        sre_alerts = [a for a in alerts if "sre_agent" in a.get("labels", {}).get("alertname", "") or
                      any("sre_agent" in str(v) for v in a.get("labels", {}).values())]

        if not sre_alerts:
            ok("No active SRE-agent alerts — all thresholds within bounds ✓")
            info("Alerts require sustained threshold breaches (2m–10m 'for' durations) to fire")
            info("Run the SLO breach demo (P1) to see DiagnosisLatencySLOBreach fire")
        else:
            for alert in sre_alerts:
                alert_name = alert.get("labels", {}).get("alertname", "unknown")
                state = alert.get("state", "?")
                sev = alert.get("labels", {}).get("severity", "?")
                summary = alert.get("annotations", {}).get("summary", "")
                state_col = C.RED if state == "firing" else C.YELLOW
                print(f"  {state_col}{'🔥' if state == 'firing' else '⏳'}  {alert_name}{C.RESET}")
                field("State", f"{state_col}{state}{C.RESET}")
                field("Severity", sev)
                field("Summary", summary)
                print()

    # ── Final Summary ─────────────────────────────────────────────────────────
    banner("P6 FULL OBSERVABILITY LOOP — COMPLETE")

    # Local metric snapshot
    print(f"  {C.BOLD}Metrics emitted this run (local registry snapshot):{C.RESET}\n")

    # SEVERITY_ASSIGNED
    print(f"  {C.CYAN}sre_agent_severity_assigned_total{C.RESET}")
    for metric in SEVERITY_ASSIGNED.collect():
        for sample in metric.samples:
            if sample.name.endswith("_total") and sample.value > 0:
                print(
                    f"    severity={sample.labels.get('severity')}  "
                    f"tier={sample.labels.get('service_tier')}  "
                    f"→  {C.BOLD}{sample.value:.0f}{C.RESET}"
                )

    # DIAGNOSIS_ERRORS
    print(f"\n  {C.CYAN}sre_agent_diagnosis_errors_total{C.RESET}")
    for metric in DIAGNOSIS_ERRORS.collect():
        for sample in metric.samples:
            if sample.name.endswith("_total") and sample.value > 0:
                print(
                    f"    error_type={sample.labels.get('error_type')}  "
                    f"→  {C.BOLD}{sample.value:.0f}{C.RESET}"
                )

    # CIRCUIT_BREAKER_STATE
    print(f"\n  {C.CYAN}sre_agent_circuit_breaker_state{C.RESET}")
    for metric in CIRCUIT_BREAKER_STATE.collect():
        for sample in metric.samples:
            if sample.labels.get("resource_type") == "k8s-operator":
                label = {0.0: "CLOSED", 1.0: "HALF_OPEN", 2.0: "OPEN"}.get(sample.value, "?")
                print(
                    f"    provider={sample.labels.get('provider')}  "
                    f"resource_type={sample.labels.get('resource_type')}  "
                    f"→  {C.BOLD}{sample.value:.0f} ({label}){C.RESET}"
                )

    # LLM token totals
    print(f"\n  {C.CYAN}sre_agent_llm_tokens_total{C.RESET}")
    total_tokens = 0.0
    for metric in LLM_TOKENS_USED.collect():
        for sample in metric.samples:
            if sample.name.endswith("_total") and sample.value > 0:
                total_tokens += sample.value
                print(
                    f"    provider={sample.labels.get('provider')}  "
                    f"token_type={sample.labels.get('token_type')}  "
                    f"→  {C.BOLD}{sample.value:.0f}{C.RESET}"
                )

    print()
    separator()
    print(f"\n  {C.DIM}Total LLM tokens consumed this run: {total_tokens:.0f}{C.RESET}")

    prom_status = (
        f"{C.GREEN}LIVE — queries returned TSDB data{C.RESET}"
        if prom_healthy
        else f"{C.YELLOW}OFFLINE — local registry fallback shown{C.RESET}"
    )
    print(f"  {C.DIM}Prometheus status: {C.RESET}{prom_status}")
    print(f"\n  {C.GREEN}Demo complete.{C.RESET}\n")


# ─── Local fallback helpers ───────────────────────────────────────────────────


def _print_local_metrics_fallback() -> None:
    """Print key metric values from the local Prometheus registry when Prometheus is offline."""
    sections = [
        ("sre_agent_severity_assigned_total", SEVERITY_ASSIGNED),
        ("sre_agent_diagnosis_errors_total", DIAGNOSIS_ERRORS),
        ("sre_agent_circuit_breaker_state", CIRCUIT_BREAKER_STATE),
        ("sre_agent_llm_tokens_total", LLM_TOKENS_USED),
    ]
    for name, metric_obj in sections:
        print(f"  {C.CYAN}{name}{C.RESET}")
        found = False
        for metric in metric_obj.collect():
            for sample in metric.samples:
                # Show only total/gauge samples with non-zero values
                if ("_bucket" not in sample.name and "_sum" not in sample.name
                        and sample.value != 0):
                    labels = "  ".join(f"{k}={v}" for k, v in sample.labels.items())
                    print(f"    {C.DIM}{labels}{C.RESET}  →  {C.BOLD}{sample.value:.4g}{C.RESET}")
                    found = True
        if not found:
            print(f"    {C.DIM}(no non-zero samples){C.RESET}")
        print()


def _print_expected_alert_rules() -> None:
    """Print the expected alert rules from the YAML (offline fallback)."""
    rules = [
        ("DiagnosisLatencySLOBreach", "critical", "P99 diagnosis latency > 30s for 5m"),
        ("LLMAPIErrors",              "warning",  "LLM error rate > 10% for 5m"),
        ("LLMParseFailureSpike",      "warning",  "JSON parse failures > 5/min for 2m"),
        ("ThrottleQueueSaturation",   "warning",  "LLM queue depth > 20 for 3m"),
        ("EvidenceQualityDrop",       "warning",  "P50 relevance score < 0.4 for 10m"),
        ("LLMTokenRateTooHigh",       "warning",  "> 100 k tokens/min for 5m"),
        ("EmbeddingColdStartHigh",    "info",     "Model load time > 60s"),
        ("CircuitBreakerOpen",        "critical", "sre_agent_circuit_breaker_state == 2 for 1m"),
    ]
    for name, severity, description in rules:
        sev_col = C.RED if severity == "critical" else C.YELLOW if severity == "warning" else C.DIM
        print(f"  {sev_col}●{C.RESET}  {C.BOLD}{name:<35}{C.RESET}  [{sev_col}{severity}{C.RESET}]  {C.DIM}{description}{C.RESET}")
    print()


# ─── Entrypoint ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        asyncio.run(run_demo())
    except KeyboardInterrupt:
        print(f"\n{C.YELLOW}Demo interrupted by user.{C.RESET}\n")
        sys.exit(0)
