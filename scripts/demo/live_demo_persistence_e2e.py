"""
Live Demo: End-to-End Persistence Layer Walkthrough
====================================================

Demonstrates every table and adapter in the persistence layer by simulating a
complete SRE incident lifecycle:

  Phase 1  — Incident arrives (IncidentStore + outbox)
  Phase 2  — Diagnosis runs   (DiagnosisStore + ReasoningTraceStore)
  Phase 3  — Remediation      (RemediationStore)
  Phase 4  — Agent lock/coordination (CoordinationAuditStore)
  Phase 5  — Outbox relay mechanics (OutboxStore: claim → send → processed_events)
  Phase 6  — Telemetry & baselines  (EventStore + telemetry_metrics + baseline_snapshots)
  Phase 7  — Full read-back         (every adapter queried, relationships printed)

Requirements
------------
Run against any live PostgreSQL instance (the sre-pg-inspect container works):

    docker run -d --name sre-pg-demo -p 5434:5432 \\
        -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=sre_demo \\
        postgres:16

Then apply all migrations:

    for i in $(seq -w 1 10); do
        f=$(ls src/sre_agent/adapters/persistence/migrations/${i}*.sql 2>/dev/null | head -1)
        [ -n "$f" ] && docker exec -i sre-pg-demo psql -U test -d sre_demo < "$f"
    done

Then run the demo:

    POSTGRES_DSN="postgresql://test:test@localhost:5434/sre_demo" \\
        python scripts/demo/live_demo_persistence_e2e.py

To use the existing sre-pg-inspect container (port 5433) just set POSTGRES_DSN accordingly.
The script TRUNCATES all demo tables at the end so it is safe to run repeatedly.
Set SKIP_CLEANUP=1 to keep data for manual inspection.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import textwrap
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

# ── colour helpers ─────────────────────────────────────────────────────────────
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
MAGENTA = "\033[35m"
RED = "\033[31m"
BLUE = "\033[34m"
WHITE = "\033[97m"


def banner(text: str, colour: str = CYAN) -> None:
    width = 72
    print(f"\n{colour}{BOLD}{'═' * width}{RESET}")
    print(f"{colour}{BOLD}  {text}{RESET}")
    print(f"{colour}{BOLD}{'═' * width}{RESET}")


def section(text: str) -> None:
    print(f"\n{YELLOW}{BOLD}── {text} {'─' * max(0, 66 - len(text))}{RESET}")


def ok(msg: str) -> None:
    print(f"  {GREEN}✔{RESET}  {msg}")


def info(msg: str) -> None:
    print(f"  {BLUE}ℹ{RESET}  {msg}")


def row(label: str, value: Any) -> None:
    label_fmt = f"{DIM}{label:<28}{RESET}"
    print(f"     {label_fmt}{WHITE}{value}{RESET}")


def table_header(cols: list[str]) -> None:
    print(f"  {DIM}{'  '.join(f'{c:<24}' for c in cols)}{RESET}")
    print(f"  {DIM}{'  '.join('─' * 24 for _ in cols)}{RESET}")


def table_row(*cells: Any) -> None:
    print(f"  {'  '.join(f'{str(c):<24}' for c in cells)}")


SKIP_PAUSES = os.getenv("SKIP_PAUSES") == "1"


def pause(msg: str = "Press Enter to continue…") -> None:
    if not SKIP_PAUSES:
        input(f"\n  {DIM}{msg}{RESET}")
    else:
        time.sleep(0.05)


# ── DSN ────────────────────────────────────────────────────────────────────────

def get_dsn() -> str:
    dsn = os.getenv("POSTGRES_DSN", "")
    if not dsn:
        print(
            f"\n{RED}ERROR:{RESET} Set POSTGRES_DSN before running, e.g.:\n"
            "  POSTGRES_DSN=\"postgresql://test:test@localhost:5434/sre_demo\" "
            "python scripts/demo/live_demo_persistence_e2e.py\n"
        )
        sys.exit(1)
    # Normalise SQLAlchemy-style scheme
    return dsn.replace("postgresql+psycopg2://", "postgresql://", 1)


# ── bootstrap adapters ─────────────────────────────────────────────────────────

async def build_adapters(pool: Any) -> dict[str, Any]:
    """Instantiate all 7 persistence adapters against the shared pool."""
    from sre_agent.adapters.persistence.incident_store import PostgresIncidentStore
    from sre_agent.adapters.persistence.diagnosis_store import PostgresDiagnosisStore
    from sre_agent.adapters.persistence.remediation_store import PostgresRemediationStore
    from sre_agent.adapters.persistence.reasoning_trace_store import PostgresReasoningTraceStore
    from sre_agent.adapters.persistence.coordination_store import PostgresCoordinationAuditStore
    from sre_agent.adapters.persistence.postgres_outbox import PostgresOutboxStore
    from sre_agent.adapters.persistence.event_store import PostgresEventStore

    return {
        "incident":     PostgresIncidentStore(pool=pool),
        "diagnosis":    PostgresDiagnosisStore(pool=pool),
        "remediation":  PostgresRemediationStore(pool=pool),
        "trace":        PostgresReasoningTraceStore(pool=pool),
        "coordination": PostgresCoordinationAuditStore(pool=pool),
        "outbox":       PostgresOutboxStore(pool=pool),
        "event_store":  PostgresEventStore(pool=pool),
    }


# ── Phase helpers ──────────────────────────────────────────────────────────────

async def phase1_incident_arrives(adapters: dict, ids: dict) -> None:
    """
    Tables touched:
      incident_events   — immutable append-only source of truth
      event_outbox      — transactional outbox (one row per event, auto-enqueued)
      incidents         — mutable projection (upserted on first event)
    """
    banner("PHASE 1 — Incident Arrives", GREEN)
    section("What happens")
    print(textwrap.dedent("""
      When a new incident is detected, IncidentStore.save_event() opens a
      single DB transaction that:

        1. INSERTs into incident_events  (append-only, idempotent via UNIQUE key)
        2. INSERTs into event_outbox     (pending relay to Redis/Kafka)
        3. UPSERTs into incidents        (mutable projection for quick API reads)

      The same incident_id links all three tables.  The outbox guarantees
      at-least-once delivery to the event stream even if the relay crashes.
    """).strip())

    from sre_agent.ports.persistence import IncidentEventRecord

    incident_id = uuid4()
    ids["incident_id"] = incident_id

    now = datetime.now(UTC)

    # ── Event 1: incident.created ─────────────────────────────────────────────
    pause()
    section("Writing incident.created event")
    ev1 = IncidentEventRecord(
        event_id=uuid4(),
        incident_id=incident_id,
        event_type="incident.created",
        occurred_at=now,
        provider="kubernetes",
        compute_mechanism="KUBERNETES",
        resource_id="deployment/checkout-service",
        payload_json={
            "service": "checkout-service",
            "severity": "SEV2",
            "anomaly": "OOMKill",
            "pod_restart_count": 7,
            "namespace": "production",
        },
        idempotency_key=f"demo-created-{incident_id}",
        correlation_key=f"alert-group-{incident_id}",
    )
    ids["event1_id"] = ev1.event_id

    await adapters["incident"].save_event(ev1)
    ok(f"incident_events ← event_id={ev1.event_id!s:.8}…  type=incident.created")
    ok("event_outbox    ← status=pending  (relay will deliver to stream bus)")

    # Projection must be seeded manually for the first event
    async with adapters["incident"]._pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO incidents
                (incident_id, service, severity, status, opened_at, updated_at,
                 latest_event_id, provider, compute_mechanism, resource_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (incident_id) DO NOTHING
            """,
            incident_id,
            "checkout-service",
            "SEV2",
            "open",
            now,
            now,
            ev1.event_id,
            "kubernetes",
            "KUBERNETES",
            "deployment/checkout-service",
        )
    ok("incidents       ← projection seeded (status=open, severity=SEV2)")

    # ── Event 2: incident.investigating ──────────────────────────────────────
    pause("Enter to write a second event (status transition)…")
    section("Writing incident.investigating event")
    ev2 = IncidentEventRecord(
        event_id=uuid4(),
        incident_id=incident_id,
        event_type="incident.investigating",
        occurred_at=now + timedelta(seconds=5),
        provider="kubernetes",
        compute_mechanism="KUBERNETES",
        resource_id="deployment/checkout-service",
        payload_json={"agent": "sre-agent-prod-01", "triggered_by": "anomaly_detector"},
        idempotency_key=f"demo-investigating-{incident_id}",
        correlation_key=f"alert-group-{incident_id}",
    )
    ids["event2_id"] = ev2.event_id

    await adapters["incident"].save_event(ev2)
    ok(f"incident_events ← event_id={ev2.event_id!s:.8}…  type=incident.investigating")

    # Update projection to investigating
    await adapters["incident"].update_projection(
        incident_id,
        status="investigating",
        latest_event_id=ev2.event_id,
        provider="kubernetes",
        compute_mechanism="KUBERNETES",
        resource_id="deployment/checkout-service",
    )
    ok("incidents       ← projection updated (status=investigating)")

    row("incident_id",  incident_id)
    row("event_count",  2)
    row("outbox_rows",  "2 (pending delivery)")


async def phase2_diagnosis(adapters: dict, ids: dict) -> None:
    """
    Tables touched:
      agent_runs         — one run root record per diagnosis invocation
      tool_calls         — every LLM/tool call within the run
      retrieved_contexts — RAG context docs retrieved per run
      diagnosis_results  — final diagnosis summary + evidence refs
    """
    banner("PHASE 2 — Diagnosis & RAG Reasoning Traces", CYAN)
    section("What happens")
    print(textwrap.dedent("""
      The RAG diagnosis pipeline creates a reasoning trace hierarchy:

        agent_runs           1 root row (run_id links everything below)
          └── tool_calls     N rows — every LLM call, k8s API call, etc.
          └── retrieved_contexts  N rows — runbook/knowledge-base docs ranked by similarity

      After the pipeline completes, a final summary is written to:
        diagnosis_results    linked to incident_id (foreign key)
    """).strip())

    incident_id = ids["incident_id"]

    pause()
    section("Starting agent run (reasoning trace)")
    run_id = await adapters["trace"].start_run(
        incident_id=incident_id,
        agent_id="sre-agent-prod-01",
        metadata={"pipeline": "rag_diagnosis_v2", "model": "gpt-4o"},
    )
    ids["run_id"] = run_id
    ok(f"agent_runs ← run_id={run_id!s:.8}…  agent=sre-agent-prod-01")

    pause("Enter to simulate tool calls…")
    section("Logging tool calls")

    # Simulate a k8s API fetch
    call1_id = await adapters["trace"].log_tool_call(
        run_id=run_id,
        tool_name="kubectl_describe_pod",
        status="success",
        input_payload={"namespace": "production", "pod": "checkout-service-7f8b9-xkz2p"},
        output_payload={"exit_code": 137, "reason": "OOMKilled", "memory_limit": "512Mi"},
        latency_ms=120,
    )
    ok(f"tool_calls ← call_id={call1_id!s:.8}…  tool=kubectl_describe_pod  latency=120ms")

    # Simulate an LLM call
    call2_id = await adapters["trace"].log_tool_call(
        run_id=run_id,
        tool_name="llm_diagnosis",
        status="success",
        input_payload={"prompt_tokens": 1842, "model": "gpt-4o"},
        output_payload={"completion_tokens": 312, "finish_reason": "stop"},
        latency_ms=1850,
    )
    ok(f"tool_calls ← call_id={call2_id!s:.8}…  tool=llm_diagnosis          latency=1850ms")

    pause("Enter to log retrieved RAG context…")
    section("Logging retrieved contexts")

    ctx1_id = await adapters["trace"].log_retrieved_context(
        run_id=run_id,
        doc_id="runbook-oom-kill-kubernetes",
        similarity_score=0.923,
        content_snippet="When a pod is OOMKilled, inspect memory.requests vs memory.limits "
                         "and check for memory leaks via heap profiling…",
        source="knowledge_base",
    )
    ok(f"retrieved_contexts ← ctx_id={ctx1_id!s:.8}…  score=0.923  doc=runbook-oom-kill")

    ctx2_id = await adapters["trace"].log_retrieved_context(
        run_id=run_id,
        doc_id="runbook-memory-limits-tuning",
        similarity_score=0.871,
        content_snippet="Increase memory limit by 2× the current P99 RSS. Add HPA memory target…",
        source="knowledge_base",
    )
    ok(f"retrieved_contexts ← ctx_id={ctx2_id!s:.8}…  score=0.871  doc=runbook-memory-limits")

    pause("Enter to end run and save diagnosis…")
    section("Ending run and persisting diagnosis result")

    await adapters["trace"].end_run(
        run_id=run_id,
        outcome="success",
        metadata={"total_tokens": 2154, "wall_time_ms": 2340},
    )
    ok(f"agent_runs ← ended_at set, outcome=success")

    from sre_agent.ports.persistence import DiagnosisResultRecord

    diag_id = uuid4()
    ids["diag_id"] = diag_id
    diag = DiagnosisResultRecord(
        diagnosis_id=diag_id,
        incident_id=incident_id,
        diagnosis_summary=(
            "checkout-service OOMKilled (7 restarts in 30 min). "
            "Root cause: memory leak in cart serializer introduced in v3.2.1. "
            "Confidence: 0.91. Recommended action: rollback to v3.2.0 and increase "
            "memory limit to 1Gi as an interim guard."
        ),
        confidence_score=0.91,
        evidence_refs=[
            {"doc_id": "runbook-oom-kill-kubernetes", "score": 0.923},
            {"doc_id": "runbook-memory-limits-tuning", "score": 0.871},
            {"source": "kubectl", "resource": "pod/checkout-service-7f8b9-xkz2p", "exit_code": 137},
        ],
        generated_at=datetime.now(UTC),
        model_name="gpt-4o",
    )
    await adapters["diagnosis"].save_diagnosis(diag)
    ok(f"diagnosis_results ← diag_id={diag_id!s:.8}…  confidence=0.91")

    row("run_id",          run_id)
    row("tool_calls",      2)
    row("contexts",        2)
    row("diagnosis_id",    diag_id)


async def phase3_remediation(adapters: dict, ids: dict) -> None:
    """
    Tables touched:
      remediation_actions — lifecycle: planned → approved → running → completed
                            Optional self-ref rollback_action_id FK
      incidents           — projection updated to 'mitigating'
    """
    banner("PHASE 3 — Remediation Planning & Execution", MAGENTA)
    section("What happens")
    print(textwrap.dedent("""
      The remediation planner writes a RemediationActionRecord for each proposed
      action. Status transitions are recorded via update_status():

        planned  →  approved  →  running  →  completed  (happy path)
                                           →  failed     (unhappy path)
                                           →  rolled_back (with rollback_action_id FK)

      A rollback action is a sibling row whose rollback_action_id FK points
      back to the original action, creating a self-referential audit trail.
    """).strip())

    incident_id = ids["incident_id"]

    from sre_agent.ports.persistence import RemediationActionRecord

    pause()
    section("Primary action: rollback to v3.2.0")
    primary_id = uuid4()
    ids["primary_action_id"] = primary_id
    now = datetime.now(UTC)

    primary = RemediationActionRecord(
        action_id=primary_id,
        incident_id=incident_id,
        action_type="deployment_rollback",
        action_status="planned",
        approval_mode="auto",
        requested_at=now,
    )
    await adapters["remediation"].save_action(primary)
    ok(f"remediation_actions ← action_id={primary_id!s:.8}…  type=deployment_rollback  status=planned")

    pause("Enter to approve and execute…")
    await adapters["remediation"].update_status(primary_id, "approved")
    ok("remediation_actions ← status=approved")

    await adapters["remediation"].update_status(
        primary_id, "running", started_at=datetime.now(UTC)
    )
    ok("remediation_actions ← status=running")

    await adapters["remediation"].update_status(
        primary_id,
        "completed",
        completed_at=datetime.now(UTC),
        execution_result={
            "previous_image": "checkout-service:v3.2.1",
            "new_image":      "checkout-service:v3.2.0",
            "rollout_status": "complete",
            "pods_ready":     3,
        },
    )
    ok("remediation_actions ← status=completed  (rollback successful)")

    pause("Enter to write secondary action: scale-up as safety buffer…")
    section("Secondary action: HPA min-replicas bump (safety buffer)")
    secondary_id = uuid4()
    secondary = RemediationActionRecord(
        action_id=secondary_id,
        incident_id=incident_id,
        action_type="hpa_scale_up",
        action_status="planned",
        approval_mode="auto",
        requested_at=datetime.now(UTC),
    )
    await adapters["remediation"].save_action(secondary)
    await adapters["remediation"].update_status(secondary_id, "approved")
    await adapters["remediation"].update_status(secondary_id, "running", started_at=datetime.now(UTC))
    await adapters["remediation"].update_status(
        secondary_id,
        "completed",
        completed_at=datetime.now(UTC),
        execution_result={"min_replicas_before": 2, "min_replicas_after": 4},
    )
    ok(f"remediation_actions ← action_id={secondary_id!s:.8}…  type=hpa_scale_up  status=completed")

    # Update incident projection to mitigating
    await adapters["incident"].update_projection(
        incident_id,
        status="mitigating",
        latest_event_id=ids["event2_id"],
        provider="kubernetes",
        compute_mechanism="KUBERNETES",
        resource_id="deployment/checkout-service",
    )
    ok("incidents ← projection updated (status=mitigating)")

    row("primary_action_id",  primary_id)
    row("secondary_action_id", secondary_id)


async def phase4_coordination(adapters: dict, ids: dict) -> None:
    """
    Tables touched:
      coordination_audit  — lock/cooldown/override events from AGENTS.md
    """
    banner("PHASE 4 — Multi-Agent Coordination Audit Trail", YELLOW)
    section("What happens")
    print(textwrap.dedent("""
      Per AGENTS.md every agent lock lifecycle event is durably written to
      coordination_audit. Three distinct event types are demonstrated:

        acquire   — SRE agent wins the lock
        preempt   — SecOps agent (priority 1) overrides SRE (priority 2)
        override  — Human operator kills the automation

      The table is monthly-partitioned (coordination_audit_YYYYMM child tables).
      Queries on resource_id, actor_id, or action use dedicated B-tree indexes.
    """).strip())

    from sre_agent.ports.persistence import LockAuditEntry, CooldownAuditEntry, OverrideAuditEntry

    pause()
    section("SRE agent acquires lock")
    lock_id = await adapters["coordination"].record_lock_event(
        LockAuditEntry(
            actor_type="sre-agent",
            actor_id="sre-agent-prod-01",
            action="acquire",
            provider="kubernetes",
            compute_mechanism="KUBERNETES",
            resource_id="deployment/checkout-service",
            lock_priority=2,
            fencing_token=948271,
            details={"ttl_seconds": 180, "incident_id": str(ids["incident_id"])},
        )
    )
    ok(f"coordination_audit ← audit_id={lock_id!s:.8}…  action=acquire  priority=2  token=948271")

    pause("Enter to simulate SecOps preemption…")
    section("SecOps agent preempts (priority 1 > 2)")
    preempt_id = await adapters["coordination"].record_lock_event(
        LockAuditEntry(
            actor_type="secops-agent",
            actor_id="secops-agent-sec-01",
            action="preempt",
            provider="kubernetes",
            compute_mechanism="KUBERNETES",
            resource_id="deployment/checkout-service",
            lock_priority=1,
            fencing_token=948272,
            details={"reason": "CVE-2026-1234 active exploitation detected", "revoked_token": 948271},
        )
    )
    ok(f"coordination_audit ← audit_id={preempt_id!s:.8}…  action=preempt  priority=1  token=948272")
    info("SRE agent backs off — SecOps has higher priority per AGENTS.md §2")

    pause("Enter to simulate cooldown being set…")
    section("Cooldown set (15-min cooling-off window)")
    cooldown_id = await adapters["coordination"].record_cooldown_event(
        CooldownAuditEntry(
            actor_type="sre-agent",
            actor_id="sre-agent-prod-01",
            action="set",
            provider="kubernetes",
            compute_mechanism="KUBERNETES",
            resource_id="deployment/checkout-service",
            details={"ttl_seconds": 900, "key": "cooldown:kubernetes:KUBERNETES:deployment/checkout-service"},
        )
    )
    ok(f"coordination_audit ← audit_id={cooldown_id!s:.8}…  action=set (cooldown)  ttl=900s")

    pause("Enter to simulate human override…")
    section("Human operator activates global kill-switch")
    override_id = await adapters["coordination"].record_override_event(
        OverrideAuditEntry(
            actor_type="human",
            actor_id="ops-lead@example.com",
            action="kill_switch_activate",
            provider="kubernetes",
            compute_mechanism="KUBERNETES",
            resource_id="deployment/checkout-service",
            audit_required=True,
            details={"reason": "Manual rollback already in progress by platform team"},
        )
    )
    ok(f"coordination_audit ← audit_id={override_id!s:.8}…  action=kill_switch_activate")
    info("All agents yield — Human Supremacy §4 enforced")

    ids["lock_id"] = lock_id
    row("audit_entries_written", 3)


async def phase5_outbox_relay(adapters: dict, ids: dict) -> None:
    """
    Tables touched:
      event_outbox      — claim → mark_sent + processed_events
      processed_events  — consumer-side dedup guard
    """
    banner("PHASE 5 — Outbox Relay Mechanics", BLUE)
    section("What happens")
    print(textwrap.dedent("""
      The OutboxRelay runs as a background task. It:

        1. claim_pending()      — atomically changes status pending→processing
                                   (SELECT … FOR UPDATE SKIP LOCKED)
        2. Publishes to stream  — Redis/Kafka (simulated here)
        3. mark_sent()          — status → sent
        4. mark_event_processed() — inserts into processed_events
                                    (consumer-side dedup for at-least-once)

      Dead-letter path:
        mark_failed()  → status=failed  (after max retries)
        mark_dlq()     → status=dlq  + dlq_at + dlq_reason  (terminal)

      increment_retry() is called after each transient failure.
    """).strip())

    pause()
    section("Claiming pending outbox entries")
    pending = await adapters["outbox"].claim_pending(limit=10)
    ok(f"event_outbox ← claimed {len(pending)} entries (status → processing)")
    for p in pending:
        info(f"  outbox_id={str(p['outbox_id']):.8}…  topic={p.get('topic', 'incident.events')}")

    if not pending:
        info("No pending entries — events may have been claimed already. Checking get_pending()…")
        pending = await adapters["outbox"].get_pending(limit=10)
        info(f"  get_pending found {len(pending)} rows (read-only, no lock)")
        return

    pause("Enter to simulate relay publish + mark sent…")
    section("Simulating relay publish → mark_sent + processed_events")
    consumer = "redis-stream-relay-01"
    for entry in pending:
        oid = entry["outbox_id"]
        eid = entry["event_id"]

        # Simulate: publish to stream bus (no-op here)
        info(f"  [stream] publishing event_id={str(eid):.8}… to {entry.get('topic', 'incident.events')}")

        await adapters["outbox"].mark_sent(oid)
        ok(f"  event_outbox ← outbox_id={str(oid):.8}…  status=sent")

        inserted = await adapters["outbox"].mark_event_processed(consumer, eid)
        if inserted:
            ok(f"  processed_events ← consumer={consumer}  event_id={str(eid):.8}…  (new)")
        else:
            info(f"  processed_events ← already processed (idempotent no-op)")

    row("relay_consumer", consumer)
    row("entries_sent",   len(pending))


async def phase6_telemetry_and_events(adapters: dict, ids: dict) -> None:
    """
    Tables touched:
      telemetry_metrics    — high-volume metric time-series
      baseline_snapshots   — computed anomaly detection baselines
      (EventStore writes to incident_events with its own format)
    """
    banner("PHASE 6 — Telemetry Metrics & Baseline Snapshots", CYAN)
    section("What happens")
    print(textwrap.dedent("""
      telemetry_metrics holds raw metric points. The schema mirrors a
      Prometheus remote_write target: (metric_name, service, ts, value, labels).
      A composite PRIMARY KEY includes a label_hash for dedup.

      baseline_snapshots hold computed P95/mean baselines per
      (service, metric_name, window). The anomaly detector compares live
      metrics against these snapshots to produce incident events.
    """).strip())

    pause()
    section("Writing telemetry metric points (memory_usage_bytes)")

    import hashlib

    now = datetime.now(UTC)
    labels = {"namespace": "production", "container": "checkout"}
    label_hash = hashlib.md5(json.dumps(labels, sort_keys=True).encode()).hexdigest()[:16]

    async with adapters["incident"]._pool.acquire() as conn:
        for i, value in enumerate([480_000_000, 496_000_000, 510_000_000, 524_000_000, 538_000_000]):
            ts = now - timedelta(seconds=(4 - i) * 15)
            await conn.execute(
                """
                INSERT INTO telemetry_metrics
                    (metric_name, service, ts, value, labels_json, label_hash)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6)
                ON CONFLICT DO NOTHING
                """,
                "memory_usage_bytes",
                "checkout-service",
                ts,
                float(value),
                json.dumps(labels),
                label_hash,
            )
        ok("telemetry_metrics ← 5 memory_usage_bytes points for checkout-service")

    pause("Enter to write a baseline snapshot…")
    section("Writing a baseline snapshot")
    snap_id = uuid4()
    async with adapters["incident"]._pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO baseline_snapshots
                (snapshot_id, service, metric_name, window_start, window_end,
                 baseline_value, variance_value, generated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            snap_id,
            "checkout-service",
            "memory_usage_bytes",
            now - timedelta(hours=1),
            now,
            420_000_000.0,  # P95 baseline
            15_000_000.0,   # variance
            now,
        )
    ok(f"baseline_snapshots ← snap_id={snap_id!s:.8}…  baseline=420MB  variance=15MB")
    info("Anomaly: live value 538MB > baseline 420MB + 3σ → OOMKill risk triggered")

    ids["snap_id"] = snap_id
    row("metric_points",  5)
    row("baselines",      1)


async def phase7_read_back(adapters: dict, ids: dict, pool: Any) -> None:
    """Full read-back — query every adapter and print a relationship map."""
    banner("PHASE 7 — Full Read-Back & Relationship Map", WHITE)
    section("Querying all tables and printing relationships")

    incident_id = ids["incident_id"]

    # ── incident events ───────────────────────────────────────────────────────
    pause()
    section("incident_events  (append-only source of truth)")
    events = await adapters["incident"].get_events_by_incident(incident_id)
    table_header(["event_id[:8]", "event_type", "occurred_at"])
    for ev in events:
        table_row(str(ev.event_id)[:8] + "…", ev.event_type, str(ev.occurred_at)[:19])

    # ── incidents projection ──────────────────────────────────────────────────
    pause()
    section("incidents  (mutable projection)")
    inc = await adapters["incident"].get_incident(incident_id)
    if inc:
        row("incident_id",       str(inc.incident_id)[:8] + "…")
        row("service",           inc.service)
        row("severity",          inc.severity)
        row("status",            inc.status)
        row("provider",          inc.provider)
        row("compute_mechanism", inc.compute_mechanism)
        row("resource_id",       inc.resource_id)
        row("latest_event_id",   str(inc.latest_event_id)[:8] + "…")

    # ── diagnosis results ──────────────────────────────────────────────────────
    pause()
    section("diagnosis_results  (FK → incidents.incident_id)")
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT diagnosis_id, confidence_score, model_name, generated_at FROM diagnosis_results WHERE incident_id=$1",
            incident_id,
        )
    for r in rows:
        row("diagnosis_id",   str(r["diagnosis_id"])[:8] + "…")
        row("confidence",     r["confidence_score"])
        row("model",          r["model_name"])

    # ── remediation actions ───────────────────────────────────────────────────
    pause()
    section("remediation_actions  (FK → incidents.incident_id)")
    actions = await adapters["remediation"].get_by_incident(incident_id)
    table_header(["action_id[:8]", "action_type", "status"])
    for a in actions:
        table_row(str(a.action_id)[:8] + "…", a.action_type, a.action_status)

    # ── agent_runs + tool_calls + retrieved_contexts ───────────────────────────
    pause()
    section("agent_runs  (FK → incidents.incident_id)")
    run_id = ids["run_id"]
    run = await adapters["trace"].get_run(run_id)
    if run:
        row("run_id",   str(run.run_id)[:8] + "…")
        row("agent_id", run.agent_id)
        row("outcome",  run.outcome)

    section("  └── tool_calls  (FK → agent_runs.run_id)")
    tool_calls = await adapters["trace"].list_tool_calls(run_id)
    table_header(["call_id[:8]", "tool_name", "latency_ms"])
    for tc in tool_calls:
        table_row(str(tc.call_id)[:8] + "…", tc.tool_name, tc.latency_ms)

    section("  └── retrieved_contexts  (FK → agent_runs.run_id)")
    contexts = await adapters["trace"].list_retrieved_contexts(run_id)
    table_header(["ctx_id[:8]", "doc_id", "similarity_score"])
    for ctx in contexts:
        table_row(str(ctx.context_id)[:8] + "…", ctx.doc_id[:24], f"{ctx.similarity_score:.3f}")

    # ── coordination audit ─────────────────────────────────────────────────────
    pause()
    section("coordination_audit  (resource-scoped audit trail)")
    trail = await adapters["coordination"].get_audit_trail("deployment/checkout-service", limit=10)
    table_header(["audit_id[:8]", "actor_id", "action"])
    for entry in trail:
        table_row(str(entry.audit_id)[:8] + "…", entry.actor_id[:24], entry.action)

    # ── event_outbox + processed_events ───────────────────────────────────────
    pause()
    section("event_outbox  (outbox relay status)")
    async with pool.acquire() as conn:
        outbox_rows = await conn.fetch(
            "SELECT outbox_id, event_id, status, retry_count FROM event_outbox ORDER BY created_at"
        )
        proc_rows = await conn.fetch("SELECT consumer, event_id FROM processed_events")

    table_header(["outbox_id[:8]", "event_id[:8]", "status"])
    for r in outbox_rows:
        table_row(str(r["outbox_id"])[:8] + "…", str(r["event_id"])[:8] + "…", r["status"])

    section("  └── processed_events  (consumer dedup — FK → incident_events.event_id)")
    if proc_rows:
        table_header(["consumer", "event_id[:8]"])
        for r in proc_rows:
            table_row(r["consumer"][:24], str(r["event_id"])[:8] + "…")
    else:
        info("  processed_events is empty (relay not yet run or entries not yet marked processed)")

    # ── telemetry ──────────────────────────────────────────────────────────────
    pause()
    section("telemetry_metrics  (time-series metric points)")
    async with pool.acquire() as conn:
        metrics = await conn.fetch(
            "SELECT ts, value FROM telemetry_metrics WHERE service='checkout-service' ORDER BY ts"
        )
    table_header(["ts", "value (bytes)"])
    for m in metrics:
        table_row(str(m["ts"])[:19], int(m["value"]))

    section("baseline_snapshots  (computed anomaly baselines)")
    async with pool.acquire() as conn:
        snaps = await conn.fetch(
            "SELECT metric_name, baseline_value, variance_value, generated_at FROM baseline_snapshots"
        )
    table_header(["metric_name", "baseline", "variance"])
    for s in snaps:
        table_row(s["metric_name"][:24], int(s["baseline_value"]), int(s["variance_value"]))


async def print_table_summary(pool: Any) -> None:
    """Print every public table with its row count for a quick overview."""
    banner("TABLE SUMMARY — All 18 Persistence Tables", GREEN)
    async with pool.acquire() as conn:
        tables = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
        )
    print()
    for t in tables:
        name = t["tablename"]
        async with pool.acquire() as conn:
            cnt = await conn.fetchval(f"SELECT COUNT(*) FROM {name}")
        bar_len = min(cnt, 30)
        bar = "█" * bar_len
        print(f"  {WHITE}{name:<40}{RESET}  {GREEN}{bar}{RESET} {cnt}")
    print()


async def print_relationship_map() -> None:
    banner("ENTITY RELATIONSHIP MAP", CYAN)
    print(f"""
  {BOLD}incidents{RESET} ──────────────────────────────────────────────────────────────────┐
  {DIM}PK: incident_id{RESET}                                                             │
  {DIM}projection rebuilt from incident_events{RESET}                                     │
        │                                                                        │
        │ FK: incident_id                                                         │
        ├──▶  {BOLD}incident_events{RESET}  (append-only, partition by month)               │
        │      └──▶  {BOLD}event_outbox{RESET}  (per-event, transactional write)             │
        │                └──▶  {BOLD}processed_events{RESET}  (consumer dedup, FK→incident_events)
        │                                                                        │
        ├──▶  {BOLD}diagnosis_results{RESET}  (FK→incident_id)                              │
        │                                                                        │
        ├──▶  {BOLD}remediation_actions{RESET}  (FK→incident_id, self-ref rollback FK)      │
        │                                                                        │
        └──▶  {BOLD}agent_runs{RESET}  (FK→incident_id)  ◀───────────────────────────────┘
               ├──▶  {BOLD}tool_calls{RESET}           (FK→run_id)
               └──▶  {BOLD}retrieved_contexts{RESET}   (FK→run_id)

  {BOLD}coordination_audit{RESET}  (monthly partition, no FK to incidents — cross-agent scope)
      action ∈ {{acquire, release, preempt, revoke, set, clear, bypass,
                override, kill_switch_activate, kill_switch_deactivate}}
      priority 1=SecOps > 2=SRE > 3=FinOps  (AGENTS.md §3)

  {BOLD}telemetry_metrics{RESET}  (PK: metric_name + service + ts + label_hash)
      Optional TimescaleDB hypertable; degrades to regular table.

  {BOLD}baseline_snapshots{RESET}  (FK: none — computed from telemetry_metrics)

  {BOLD}vector_embeddings{RESET}  (pgvector column when extension available, else JSONB fallback)
      Used by PgVectorStoreAdapter for RAG knowledge-base lookups.
    """)


async def cleanup(pool: Any, ids: dict) -> None:
    skip = os.getenv("SKIP_CLEANUP") == "1"
    if skip:
        info("SKIP_CLEANUP=1 — data preserved for manual inspection")
        info(f"  Connect with: docker exec -it sre-pg-demo psql -U test -d sre_demo")
        return

    banner("CLEANUP", DIM)
    info("Truncating demo tables (CASCADE)…")
    async with pool.acquire() as conn:
        await conn.execute(
            """
            TRUNCATE TABLE
                processed_events,
                event_outbox,
                retrieved_contexts,
                tool_calls,
                agent_runs,
                diagnosis_results,
                remediation_actions,
                incidents,
                incident_events,
                coordination_audit,
                telemetry_metrics,
                baseline_snapshots
            RESTART IDENTITY CASCADE
            """
        )
    ok("All demo data removed. Run again for a fresh walkthrough.")
    info("Set SKIP_CLEANUP=1 to keep data and inspect with psql.")


# ── main ───────────────────────────────────────────────────────────────────────

async def main() -> None:
    import asyncpg  # type: ignore[import]

    dsn = get_dsn()

    banner("SRE Agent — End-to-End Persistence Layer Live Demo", GREEN)
    print(f"""
  {DIM}This demo exercises every persistence adapter and table by simulating
  a complete incident lifecycle:

    Phase 1  Incident detection    → incident_events, incidents, event_outbox
    Phase 2  RAG diagnosis          → agent_runs, tool_calls, retrieved_contexts,
                                      diagnosis_results
    Phase 3  Remediation execution  → remediation_actions
    Phase 4  Multi-agent locks      → coordination_audit (monthly partitioned)
    Phase 5  Outbox relay           → event_outbox (claim/send), processed_events
    Phase 6  Telemetry & baselines  → telemetry_metrics, baseline_snapshots
    Phase 7  Full read-back         → all adapters queried, relationships printed

  DSN: {dsn}{RESET}
    """)

    pause("Press Enter to start…")

    info("Creating asyncpg connection pool…")
    pool = await asyncpg.create_pool(dsn=dsn, min_size=2, max_size=5)
    ok(f"Connected to PostgreSQL")

    adapters = await build_adapters(pool)
    ok(f"All 7 persistence adapters instantiated")

    ids: dict = {}

    try:
        await phase1_incident_arrives(adapters, ids)
        await phase2_diagnosis(adapters, ids)
        await phase3_remediation(adapters, ids)
        await phase4_coordination(adapters, ids)
        await phase5_outbox_relay(adapters, ids)
        await phase6_telemetry_and_events(adapters, ids)
        await phase7_read_back(adapters, ids, pool)
        await print_table_summary(pool)
        await print_relationship_map()
    finally:
        await cleanup(pool, ids)
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
