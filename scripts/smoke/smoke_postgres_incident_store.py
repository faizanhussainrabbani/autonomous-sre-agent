#!/usr/bin/env python3
"""
Smoke test — PostgresIncidentStore adapter (non-demo path).

Writes one incident event through PostgresIncidentStore, updates the
incident projection, reads both back, and asserts row counts in
incident_events, incidents, and event_outbox grew exactly as expected.

Purpose: prove the persistence adapters and DB schema are functioning
end-to-end before enabling full API persistence wiring.

Usage
-----
    source .venv/bin/activate
    python scripts/smoke/smoke_postgres_incident_store.py

Exit codes: 0 = all assertions passed, 1 = failure.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Make the src tree importable when run from any working directory.
_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "src"))


async def main() -> int:  # noqa: C901
    from datetime import UTC, datetime
    from uuid import uuid4

    try:
        import asyncpg  # type: ignore[import]
    except ImportError:
        print("ERROR: asyncpg is not installed. Install with: pip install asyncpg")
        return 1

    from sre_agent.adapters.persistence.incident_store import PostgresIncidentStore
    from sre_agent.config.settings import AgentConfig
    from sre_agent.ports.persistence import IncidentEventRecord

    # ── Load config ───────────────────────────────────────────────────────────
    config_path = _ROOT / "config" / "agent.yaml"
    if config_path.exists():
        config = AgentConfig.from_yaml(config_path)
    else:
        config = AgentConfig()

    # Allow DSN override via env var for CI / LocalStack environments.
    dsn = os.getenv("POSTGRES_DSN") or config.persistence.postgres_dsn
    if not dsn:
        print(
            "ERROR: No postgres_dsn configured.\n"
            "  Set POSTGRES_DSN env var or enable persistence in config/agent.yaml"
        )
        return 1

    print(f"Connecting to: {dsn}")

    # ── Connect ───────────────────────────────────────────────────────────────
    try:
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=2)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: Could not connect to PostgreSQL: {exc}")
        return 1

    store = PostgresIncidentStore(pool=pool)

    # ── Count rows before ─────────────────────────────────────────────────────
    async with pool.acquire() as conn:
        before_events = await conn.fetchval("SELECT COUNT(*) FROM incident_events")
        before_incidents = await conn.fetchval("SELECT COUNT(*) FROM incidents")
        before_outbox = await conn.fetchval("SELECT COUNT(*) FROM event_outbox")

    print(
        f"Before: incident_events={before_events}, "
        f"incidents={before_incidents}, "
        f"event_outbox={before_outbox}"
    )

    # ── Build test fixtures ───────────────────────────────────────────────────
    incident_id = uuid4()
    event_id = uuid4()
    # Idempotency key scoped to this run so repeated smoke tests don't collide.
    idempotency_key = f"smoke::{event_id}"

    event = IncidentEventRecord(
        event_id=event_id,
        incident_id=incident_id,
        event_type="incident.detected",
        occurred_at=datetime.now(UTC),
        provider="kubernetes",
        compute_mechanism="KUBERNETES",
        resource_id="deployment/smoke-test-svc",
        payload_json={"source": "smoke_test", "note": "persistence adapter check"},
        idempotency_key=idempotency_key,
        correlation_key=None,
    )

    # ── save_event (writes incident_events + event_outbox atomically) ─────────
    try:
        await store.save_event(event)
        print(f"save_event OK  event_id={event_id}  incident_id={incident_id}")
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: save_event failed: {exc}")
        await pool.close()
        return 1

    # ── update_projection (upserts incidents row) ─────────────────────────────
    try:
        await store.update_projection(
            incident_id=incident_id,
            status="open",
            latest_event_id=event_id,
            provider="kubernetes",
            compute_mechanism="KUBERNETES",
            resource_id="deployment/smoke-test-svc",
            severity="medium",
        )
        print("update_projection OK")
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: update_projection failed: {exc}")
        await pool.close()
        return 1

    # ── Read back: event log ──────────────────────────────────────────────────
    events = await store.get_events_by_incident(incident_id)
    if len(events) != 1:
        print(f"FAIL: expected 1 event, got {len(events)}")
        await pool.close()
        return 1
    if events[0].event_id != event_id:
        print(f"FAIL: event_id mismatch — expected {event_id}, got {events[0].event_id}")
        await pool.close()
        return 1
    print(f"get_events_by_incident OK  count={len(events)}")

    # ── Read back: projection ─────────────────────────────────────────────────
    projection = await store.get_incident(incident_id)
    if projection is None:
        print("FAIL: get_incident returned None")
        await pool.close()
        return 1
    if projection.status != "open":
        print(f"FAIL: expected status='open', got '{projection.status}'")
        await pool.close()
        return 1
    if projection.severity != "medium":
        print(f"FAIL: expected severity='medium', got '{projection.severity}'")
        await pool.close()
        return 1
    print(f"get_incident OK  status={projection.status}  severity={projection.severity}")

    # ── Count rows after ──────────────────────────────────────────────────────
    async with pool.acquire() as conn:
        after_events = await conn.fetchval("SELECT COUNT(*) FROM incident_events")
        after_incidents = await conn.fetchval("SELECT COUNT(*) FROM incidents")
        after_outbox = await conn.fetchval("SELECT COUNT(*) FROM event_outbox")

    print(
        f"After:  incident_events={after_events}, "
        f"incidents={after_incidents}, "
        f"event_outbox={after_outbox}"
    )

    # ── Assert row growth ─────────────────────────────────────────────────────
    failures: list[str] = []
    if after_events != before_events + 1:
        failures.append(
            f"incident_events: expected {before_events + 1}, got {after_events}"
        )
    if after_incidents != before_incidents + 1:
        failures.append(
            f"incidents: expected {before_incidents + 1}, got {after_incidents}"
        )
    if after_outbox != before_outbox + 1:
        failures.append(
            f"event_outbox: expected {before_outbox + 1}, got {after_outbox}"
        )

    await pool.close()

    if failures:
        print("FAIL — row count assertions failed:")
        for f in failures:
            print(f"  {f}")
        return 1

    print("\nALL ASSERTIONS PASSED — PostgresIncidentStore adapter is functioning correctly.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
