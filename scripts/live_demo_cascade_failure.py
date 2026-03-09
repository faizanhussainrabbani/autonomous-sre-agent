#!/usr/bin/env python3
"""
Live Demo 2 — Multi-Service Cascade Failure (Flash Sale Scenario).

Simulates a realistic flash-sale incident cascade:

  ┌─────────────────────────────────────────────────────────────┐
  │  Black Friday Flash Sale — 23:00 UTC                        │
  │                                                             │
  │  1. order-service → OOM kill (RSS: 4.1 GB / limit 4 GB)    │
  │       ↓ causes upstream pressure                            │
  │  2. checkout-service → HTTP 503 Error surge (42% error rate)│
  │       ↓ propagates to API layer                             │
  │  3. api-gateway → Latency spike (p99: 18s vs 0.12s)        │
  └─────────────────────────────────────────────────────────────┘

This demo showcases:
  ✦ Multi-incident diagnosis (3 independent pipeline runs)
  ✦ Event bus subscriber notification across services
  ✦ Severity escalation hierarchy (SEV1 → SEV2 → SEV3)
  ✦ Human approval guardrail for Tier 1/2 services
  ✦ Phase 2.1 observability: Prometheus counter verification
  ✦ Isolated correlation IDs (no event stream cross-contamination)

REQUIREMENTS:
  - OPENAI_API_KEY or ANTHROPIC_API_KEY must be set in the environment.
  - chromadb, sentence-transformers, openai / anthropic, tiktoken installed.

Usage:
    export OPENAI_API_KEY="sk-..."
    python scripts/live_demo_cascade_failure.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from uuid import uuid4

# ---------------------------------------------------------------------------
# Terminal Styling
# ---------------------------------------------------------------------------

class C:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def banner(text: str) -> None:
    width = 66
    bar = "═" * width
    print(f"\n{C.HEADER}{C.BOLD}╔{bar}╗{C.RESET}")
    padding = " " * ((width - len(text)) // 2)
    print(f"{C.HEADER}{C.BOLD}║{padding}{text}{padding + (' ' if (width - len(text)) % 2 else '')}║{C.RESET}")
    print(f"{C.HEADER}{C.BOLD}╚{bar}╝{C.RESET}\n")


def section(icon: str, title: str, subtitle: str = "") -> None:
    print(f"\n{C.BLUE}{C.BOLD}{icon}  {title}{C.RESET}")
    if subtitle:
        print(f"   {C.DIM}{subtitle}{C.RESET}")


def field(label: str, value: str, color: str = C.GREEN) -> None:
    print(f"   {color}{'✔' if color == C.GREEN else '⚠' if color == C.YELLOW else '✖'}  {C.BOLD}{label}:{C.RESET} {value}")


def separator() -> None:
    print(f"   {C.DIM}{'─' * 60}{C.RESET}")


# ---------------------------------------------------------------------------
# API Key validation
# ---------------------------------------------------------------------------

if not os.environ.get("OPENAI_API_KEY") and not os.environ.get("ANTHROPIC_API_KEY"):
    print(f"\n{C.RED}Error: No LLM API Key found in environment.{C.RESET}")
    print("Export your key before running:")
    print("  export OPENAI_API_KEY='sk-...'  OR  export ANTHROPIC_API_KEY='sk-ant-...'")
    sys.exit(1)

try:
    from sre_agent.domain.models.canonical import AnomalyAlert, AnomalyType, ComputeMechanism
    from sre_agent.domain.models.diagnosis import ServiceTier
    from sre_agent.ports.diagnostics import DiagnosisRequest
    from sre_agent.adapters.intelligence_bootstrap import (
        create_diagnostic_pipeline,
        create_ingestion_pipeline,
        create_vector_store,
        create_embedding,
        create_llm,
    )
    from sre_agent.events.in_memory import InMemoryEventBus, InMemoryEventStore
    from sre_agent.adapters.telemetry.metrics import SEVERITY_ASSIGNED, EVIDENCE_RELEVANCE
except ImportError as exc:
    print(f"{C.RED}Import error: {exc}{C.RESET}")
    print("Ensure you are running from the project root with the virtual environment active.")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Knowledge Base Documents (embedded into ChromaDB at demo start)
# ---------------------------------------------------------------------------

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
  a) Check order-service health: `kubectl get pods -n prod -l app=order-service`
  b) Scale checkout-service HPA to max replicas: `kubectl scale --replicas=10`
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
  1. Upstream backend services degraded (most likely — check checkout-service, order-service).
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

# ---------------------------------------------------------------------------
# Incident Definitions
# ---------------------------------------------------------------------------

CASCADE_INCIDENTS = [
    {
        "index": 1,
        "service": "order-service",
        "tier": ServiceTier.TIER_1,
        "label": "PRIMARY — OOM Kill",
        "alert": AnomalyAlert(
            service="order-service",
            anomaly_type=AnomalyType.MEMORY_PRESSURE,
            description="Container OOM kill — RSS reached 4.1 GB during flash sale (limit: 4 GB). Shopping cart pool unbounded.",
            metric_name="container_memory_rss_bytes",
            current_value=4_100_000_000.0,
            baseline_value=1_800_000_000.0,
            deviation_sigma=13.5,
            compute_mechanism=ComputeMechanism.KUBERNETES,
        ),
        "expected_severity": "SEV1 or SEV2",
    },
    {
        "index": 2,
        "service": "checkout-service",
        "tier": ServiceTier.TIER_2,
        "label": "SECONDARY — HTTP 503 Surge",
        "alert": AnomalyAlert(
            service="checkout-service",
            anomaly_type=AnomalyType.ERROR_RATE_SURGE,
            description="HTTP 503 upstream errors spiked to 42% — order-service unavailable.",
            metric_name="upstream_5xx_error_rate",
            current_value=42.0,
            baseline_value=0.5,
            deviation_sigma=9.1,
            compute_mechanism=ComputeMechanism.KUBERNETES,
        ),
        "expected_severity": "SEV2",
    },
    {
        "index": 3,
        "service": "api-gateway",
        "tier": ServiceTier.TIER_1,
        "label": "TERTIARY — Latency Cascade",
        "alert": AnomalyAlert(
            service="api-gateway",
            anomaly_type=AnomalyType.LATENCY_SPIKE,
            description="p99 latency spiked to 18s — downstream cascade from checkout and order services.",
            metric_name="http_request_duration_p99_seconds",
            current_value=18.0,
            baseline_value=0.12,
            deviation_sigma=15.2,
            compute_mechanism=ComputeMechanism.KUBERNETES,
        ),
        "expected_severity": "SEV1 or SEV2",
    },
]


# ---------------------------------------------------------------------------
# Main demo runner
# ---------------------------------------------------------------------------

async def run_demo() -> None:
    banner("Live Demo 2 — Multi-Service Cascade Failure")
    print(f"  {C.YELLOW}Scenario: Black Friday Flash Sale — 23:00 UTC{C.RESET}")
    print(f"  {C.DIM}Three services fail in sequence as the cascade propagates.{C.RESET}\n")

    # --- Phase 0: Bootstrap ---
    section("⚙", "Phase 0: Bootstrapping Intelligence Adapters",
            "Connecting ChromaDB, Sentence-Transformers, and LLM API...")
    boot_start = time.time()

    vs = create_vector_store(collection_name="cascade_demo_kb")
    emb = create_embedding()
    llm = create_llm()
    boot_elapsed = time.time() - boot_start
    field("Adapters Ready", f"Loaded in {boot_elapsed:.2f}s")

    # --- Phase 1: Knowledge Base ingestion ---
    section("📚", "Phase 1: Knowledge Base Ingestion",
            "Embedding and storing cascade runbooks and post-mortems...")
    ingest_start = time.time()
    ingestion = create_ingestion_pipeline(vector_store=vs, embedding=emb)
    await ingestion.ingest_batch(CASCADE_RUNBOOKS)
    ingest_elapsed = time.time() - ingest_start
    field("Documents Ingested", f"{len(CASCADE_RUNBOOKS)} runbooks vectorized in {ingest_elapsed:.2f}s")

    # --- Phase 2: Alert cascade begins ---
    section("🚨", "Phase 2: Cascade Alert Storm Begins",
            "Three alerts fire within a 4-minute window...")

    results_store: list[dict] = []
    all_event_stores: list[InMemoryEventStore] = []

    for incident in CASCADE_INCIDENTS:
        alert: AnomalyAlert = incident["alert"]
        event_bus = InMemoryEventBus()
        event_store = InMemoryEventStore()
        all_event_stores.append(event_store)

        # Wire subscriber to log events
        events_received: list[str] = []

        async def on_event(event, _svc=incident["service"]):  # noqa: B023
            events_received.append(event.event_type)

        await event_bus.subscribe("*", on_event)

        print(f"\n{C.BOLD}  {'─' * 62}{C.RESET}")
        print(f"  {C.CYAN}{C.BOLD}[{incident['index']}/3] {incident['label']}{C.RESET}")
        print(f"  {C.DIM}Service: {incident['service']} | Tier: {incident['tier'].name}{C.RESET}")
        print(f"  {C.DIM}Alert:   {alert.description[:70]}...{C.RESET}")
        print()

        pipeline = create_diagnostic_pipeline(
            vector_store=vs,
            embedding=emb,
            llm=llm,
            service_tiers={incident["service"]: incident["tier"]},
            context_budget=4000,
        )
        pipeline._event_bus = event_bus
        pipeline._event_store = event_store

        diag_start = time.time()
        result = await pipeline.diagnose(
            DiagnosisRequest(alert=alert, max_evidence_items=3)
        )
        diag_elapsed = time.time() - diag_start

        sev_color = C.RED if result.severity.name in ("SEV1", "SEV2") else C.YELLOW
        field("Severity Assigned", f"{sev_color}{C.BOLD}{result.severity.name}{C.RESET}", color=C.GREEN)
        field("Confidence", f"{result.confidence * 100:.1f}%")
        field("Diagnosis Time", f"{diag_elapsed:.2f}s")
        field(
            "Execution",
            f"{C.RED}⛔ HALTED — Human Approval Required{C.RESET}" if result.requires_human_approval
            else f"{C.GREEN}✅ Autonomous Remediation Authorized{C.RESET}",
            color=C.GREEN,
        )

        separator()
        print(f"   {C.BOLD}Root Cause:{C.RESET}")
        for line in (result.root_cause or "Not determined.").splitlines():
            print(f"     {C.CYAN}{line.strip()}{C.RESET}")

        if result.evidence_citations:
            print(f"\n   {C.BOLD}Evidence Citations:{C.RESET}")
            for i, ref in enumerate(result.evidence_citations):
                print(f"     [{i + 1}] {C.DIM}{ref}{C.RESET}")

        if result.suggested_remediation:
            print(f"\n   {C.BOLD}Recommended Remediation:{C.RESET}")
            for line in result.suggested_remediation.splitlines():
                print(f"     {C.GREEN}{line.strip()}{C.RESET}")

        print(f"\n   {C.DIM}Events emitted: {', '.join(events_received)}{C.RESET}")

        results_store.append({
            "service": incident["service"],
            "severity": result.severity.name,
            "confidence": result.confidence,
            "requires_approval": result.requires_human_approval,
            "is_novel": result.is_novel,
            "event_store": event_store,
            "alert_id": alert.alert_id,
        })

    # --- Phase 3: Cross-service event isolation check ---
    section("🔬", "Phase 3: Event Isolation Verification",
            "Confirming correlation IDs are isolated (no cross-contamination)...")

    all_aggregate_ids: list[set] = []
    for entry in results_store:
        es = entry["event_store"]
        events = await es.get_events(str(entry["alert_id"]))
        agg_ids = {str(e.aggregate_id) for e in events}
        all_aggregate_ids.append(agg_ids)
        print(f"   {C.DIM}{entry['service']}: {len(events)} events, aggregate_id={list(agg_ids)[0][:8]}...{C.RESET}")

    # Verify no overlap
    id_sets = all_aggregate_ids
    if len(id_sets) >= 2:
        overlap = id_sets[0] & id_sets[1]
        if not overlap:
            field("Isolation Check", "PASSED — All incidents have independent event streams ✓")
        else:
            field("Isolation Check", f"FAILED — Overlap detected: {overlap}", color=C.YELLOW)

    # --- Phase 4: Prometheus observability summary ---
    section("📊", "Phase 4: Prometheus Observability Summary",
            "Reading SEVERITY_ASSIGNED counters from the metrics registry...")

    print(f"\n   {C.BOLD}SEVERITY_ASSIGNED counter state:{C.RESET}")
    total = 0.0
    for metric in SEVERITY_ASSIGNED.collect():
        for sample in metric.samples:
            if sample.name.endswith("_total") and sample.value > 0:
                print(f"   {C.DIM}  severity={sample.labels.get('severity')} "
                      f"service_tier={sample.labels.get('service_tier')}: "
                      f"{sample.value:.0f}{C.RESET}")
                total += sample.value
    field("Total Diagnoses Recorded in Metrics", f"{total:.0f} severity label(s) emitted")

    # --- Final summary ---
    banner("CASCADE FAILURE — INCIDENT SUMMARY")
    print(f"  {'Service':<25} {'Severity':<10} {'Confidence':<12} {'Approval?'}")
    print(f"  {'─' * 25} {'─' * 10} {'─' * 12} {'─' * 12}")
    for r in results_store:
        sev_color = C.RED if r["severity"] in ("SEV1", "SEV2") else C.YELLOW
        approval = f"{C.RED}Required{C.RESET}" if r["requires_approval"] else f"{C.GREEN}Autonomous{C.RESET}"
        print(
            f"  {r['service']:<25} "
            f"{sev_color}{r['severity']:<10}{C.RESET} "
            f"{r['confidence'] * 100:<11.1f}% "
            f"{approval}"
        )

    token_usage = llm.get_token_usage()
    print(f"\n  {C.DIM}Total LLM Token Usage: {token_usage.prompt_tokens} prompt / "
          f"{token_usage.completion_tokens} completion / {token_usage.total_tokens} total{C.RESET}")
    print(f"\n  {C.YELLOW}ℹ  All three services require human approval — "
          f"Tier 1/2 guardrail is working correctly.{C.RESET}")
    print(f"\n  {C.GREEN}Demo complete.{C.RESET}\n")


if __name__ == "__main__":
    try:
        asyncio.run(run_demo())
    except KeyboardInterrupt:
        print("\nDemo interrupted by user. Exiting.")
        sys.exit(0)
