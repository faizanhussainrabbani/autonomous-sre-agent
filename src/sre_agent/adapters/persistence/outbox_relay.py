"""Outbox relay service.

The OutboxRelay is a background service (not a port) that bridges the
transactional outbox table to the event bus. It is the final piece of
the at-least-once delivery guarantee:

  incident saved to DB
    └─► outbox row written (same transaction)
          └─► OutboxRelay polls, publishes, marks sent

This class has a single responsibility: relay pending outbox entries.
It does not own the database connection (OutboxPort) or event bus
connection (EventBus) — those are injected at construction time (DIP).

Design notes:
- ``run_once()`` processes one batch — fully testable in isolation.
- ``run()`` is the daemon loop; uses ``anyio.sleep()`` (not asyncio.sleep)
  per the project's async-first standard.
- ``stop()`` sets a flag; the loop exits cleanly on the next iteration.
- Entries that fail publish increment their retry count in memory; after
  ``max_retries`` the entry is marked failed in the DB.

Phase 4.0 — Persistence Architecture Reconciliation
Engineering Standards §2.1 (SRP), §2.3 (DIP)
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import anyio
import structlog

from sre_agent.domain.models.canonical import DomainEvent
from sre_agent.ports.events import EventBus
from sre_agent.ports.persistence import OutboxPort

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


class OutboxRelay:
    """Polls the outbox store and publishes pending entries to the event bus.

    Args:
        outbox: The OutboxPort implementation to read/update entries.
        event_bus: The EventBus implementation to publish events.
        poll_interval_s: Seconds to sleep between batches when the outbox
            is empty (or after each batch).
        max_retries: Number of publish failures before an entry is marked
            permanently failed.
        batch_size: Maximum entries to process per ``run_once()`` call.
    """

    def __init__(
        self,
        outbox: OutboxPort,
        event_bus: EventBus,
        poll_interval_s: float = 1.0,
        max_retries: int = 10,
        batch_size: int = 100,
    ) -> None:
        self._outbox = outbox
        self._event_bus = event_bus
        self._poll_interval_s = poll_interval_s
        self._max_retries = max_retries
        self._batch_size = batch_size
        self._running = False

    async def run_once(self) -> int:
        """Process one batch of pending outbox entries.

        Atomically claims entries via ``claim_pending()`` (status → 'processing')
        so concurrent relay workers cannot process the same row.

        For each claimed entry:
        - Preserves the original event_id and occurred_at timestamp from the
          outbox payload so downstream consumers can correlate events.
        - On publish success: marks the entry as 'sent'.
        - On publish failure: increments the persisted retry_count; resets status
          to 'pending' for retry, or marks 'failed' when max_retries exceeded.

        Returns:
            The number of entries claimed and processed in this batch.
        """
        entries = await self._outbox.claim_pending(limit=self._batch_size)

        for entry in entries:
            outbox_id_uuid: UUID = entry["outbox_id"]
            outbox_id = str(outbox_id_uuid)
            event_id_str = str(entry["event_id"])
            topic = entry["topic"]
            payload = entry["payload_json"]

            # --- Preserve original event identity (F9) ---
            raw_event_id = payload.get("event_id", event_id_str)
            try:
                preserved_event_id: UUID = UUID(str(raw_event_id))
            except (ValueError, AttributeError):
                preserved_event_id = uuid4()

            raw_ts = payload.get("occurred_at")
            try:
                preserved_ts: datetime = (
                    datetime.fromisoformat(raw_ts) if raw_ts else datetime.now(tz=UTC)
                )
            except (ValueError, TypeError):
                preserved_ts = datetime.now(tz=UTC)

            raw_agg_id = payload.get("incident_id", event_id_str)
            try:
                agg_uuid: UUID | None = UUID(str(raw_agg_id))
            except (ValueError, AttributeError):
                agg_uuid = None

            try:
                domain_event = DomainEvent(
                    event_id=preserved_event_id,
                    timestamp=preserved_ts,
                    event_type=payload.get("event_type", topic),
                    aggregate_id=agg_uuid,
                    payload=payload,
                )
                await self._event_bus.publish(domain_event)
                await self._outbox.mark_sent(outbox_id_uuid)
                logger.info(
                    "outbox_relay.entry_sent",
                    outbox_id=outbox_id,
                    event_id=event_id_str,
                    topic=topic,
                )
            except Exception as exc:  # noqa: BLE001
                # Persist the retry increment in the DB (durable across restarts).
                new_count = await self._outbox.increment_retry(outbox_id_uuid)
                logger.warning(
                    "outbox_relay.publish_failed",
                    outbox_id=outbox_id,
                    event_id=event_id_str,
                    retry_count=new_count,
                    max_retries=self._max_retries,
                    error=str(exc),
                )
                if new_count >= self._max_retries:
                    await self._outbox.mark_failed(outbox_id_uuid)
                    logger.error(
                        "outbox_relay.entry_permanently_failed",
                        outbox_id=outbox_id,
                        event_id=event_id_str,
                    )
                else:
                    # Return to pending so the next cycle can retry.
                    await self._outbox.release_claim(outbox_id_uuid)

        return len(entries)

    async def run(self) -> None:
        """Run the relay loop until ``stop()`` is called.

        Uses ``anyio.sleep()`` for async-first compliance.
        """
        self._running = True
        logger.info(
            "outbox_relay.started",
            poll_interval_s=self._poll_interval_s,
            batch_size=self._batch_size,
            max_retries=self._max_retries,
        )
        while self._running:
            try:
                processed = await self.run_once()
                if processed == 0:
                    # Nothing to do — sleep the full interval.
                    await anyio.sleep(self._poll_interval_s)
                # If we processed a full batch, loop immediately to check for more.
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "outbox_relay.run_once_error",
                    error=str(exc),
                )
                await anyio.sleep(self._poll_interval_s)

        logger.info("outbox_relay.stopped")

    def stop(self) -> None:
        """Signal the relay loop to exit on the next iteration."""
        self._running = False
        logger.info("outbox_relay.stop_requested")
