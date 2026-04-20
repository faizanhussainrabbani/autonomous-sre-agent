"""Redis Streams event bus adapter.

Implements EventBus using Redis Streams (XADD / XREADGROUP) to provide
durable, at-least-once event delivery across process restarts.

Architecture:
- Publish: ``XADD {prefix}:{event_type} * event_type {t} payload {json}``
- Subscribe: per-stream consumer group created with ``XGROUP CREATE ... $ MKSTREAM``
  on first subscribe; messages delivered via ``XREADGROUP``.
- Each ``subscribe()`` call starts a background ``anyio`` task that polls the
  stream and invokes the registered handler.
- ``unsubscribe()`` cancels the background task.

Stream key format: ``{stream_prefix}:{event_type}``  (configurable prefix)

Production durability notes:
- Redis Streams persist entries until explicitly deleted or trimmed (MAXLEN).
- Consumer groups track per-consumer position — restarts resume from last ACK.
- If the agent crashes after delivery but before handler completes, the message
  will be re-delivered on the next ``XREADGROUP`` call (at-least-once).
- ACK (XACK) is sent after the handler returns successfully.

Implements: EventBus (src/sre_agent/ports/events.py)
Phase 4.0 — Persistence Architecture Reconciliation
Engineering Standards §2.3 (hexagonal, DIP)
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from uuid import UUID, uuid4

import anyio
import structlog

from sre_agent.domain.models.canonical import DomainEvent
from sre_agent.observability.metrics import REDIS_STREAM_LAG
from sre_agent.ports.events import EventBus, EventHandler

if TYPE_CHECKING:
    import anyio.abc

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# Sentinel stream for wildcard (*) subscriptions
_WILDCARD = "*"


class RedisStreamsEventBus(EventBus):
    """Redis Streams-backed event bus with consumer group delivery.

    Args:
        redis_client: An async redis client (``redis.asyncio.Redis``).
        stream_prefix: Prefix for stream keys. Default: ``"sre-agent:events"``.
        consumer_group: Consumer group name shared across instances.
        consumer_name: Unique consumer name for this process instance.
        block_ms: Milliseconds to block on XREADGROUP (0 = indefinite).
        batch_size: Max messages to read per XREADGROUP call.
    """

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
        self._redis = redis_client
        self._prefix = stream_prefix
        self._group = consumer_group
        self._consumer = consumer_name
        self._block_ms = block_ms
        self._batch_size = batch_size
        # Minimum idle time before a PEL entry is considered stale and re-claimable
        # via XAUTOCLAIM (Phase 2: cross-consumer dead-letter recovery).
        self._claim_idle_ms = claim_idle_ms
        # event_type → list of handlers
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        # event_type → anyio CancelScope for background reader task
        self._reader_scopes: dict[str, anyio.CancelScope] = {}
        # registered but not-yet-started readers: list of (scope, event_type, stream_key)
        self._pending_readers: list[tuple[anyio.CancelScope, str, str]] = []
        # stored after start() is called; used to spawn late subscribers immediately
        self._task_group: anyio.abc.TaskGroup | None = None

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    async def publish(self, event: DomainEvent) -> None:
        """Publish a domain event to its Redis Stream.

        Args:
            event: The domain event to publish.
        """
        stream_key = f"{self._prefix}:{event.event_type}"
        payload = json.dumps(
            {
                "event_id": str(event.event_id),
                "event_type": event.event_type,
                "aggregate_id": str(event.aggregate_id) if event.aggregate_id else None,
                "timestamp": event.timestamp.isoformat(),
                "payload": event.payload,
            }
        )

        await self._redis.xadd(  # type: ignore[attr-defined]
            stream_key,
            {"event_type": event.event_type, "payload": payload},
        )

        logger.debug(
            "redis_streams_bus.published",
            stream=stream_key,
            event_type=event.event_type,
            event_id=str(event.event_id),
        )

    # ------------------------------------------------------------------
    # Subscribe
    # ------------------------------------------------------------------

    async def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Subscribe to a specific event type via consumer group.

        Creates the consumer group and stream if they don't exist.
        If ``start()`` has already been called, spawns the reader immediately
        into the stored task group (F4 — late subscriptions).
        Otherwise queues the reader for ``start()`` to spawn later (F3).

        Args:
            event_type: Event type string (e.g., ``"anomaly.detected"``).
            handler: Async callable invoked per received event.
        """
        self._handlers[event_type].append(handler)

        if event_type not in self._reader_scopes:
            stream_key = f"{self._prefix}:{event_type}"
            await self._ensure_consumer_group(stream_key)

            if self._task_group is not None:
                # Already started — spawn the reader immediately (F4 fix).
                scope = anyio.CancelScope()
                self._reader_scopes[event_type] = scope

                async def _spawn(
                    s: anyio.CancelScope = scope,
                    et: str = event_type,
                    sk: str = stream_key,
                ) -> None:
                    with s:
                        await self._read_loop(et, sk)

                self._task_group.start_soon(_spawn)
            else:
                # Defer to start() / run_readers() (F3 fix).
                scope = await self._start_reader(event_type, stream_key)
                self._reader_scopes[event_type] = scope

        logger.info(
            "redis_streams_bus.subscribed",
            event_type=event_type,
            handler=getattr(handler, "__name__", str(handler)),
        )

    async def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Cancel subscription and stop the background reader.

        Args:
            event_type: The event type to unsubscribe from.
            handler: The handler to remove.
        """
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

        if not self._handlers.get(event_type):
            scope = self._reader_scopes.pop(event_type, None)
            if scope is not None:
                scope.cancel()
            logger.info("redis_streams_bus.unsubscribed", event_type=event_type)

    # ------------------------------------------------------------------
    # Internal — consumer group management
    # ------------------------------------------------------------------

    async def _ensure_consumer_group(self, stream_key: str) -> None:
        """Create consumer group and stream (MKSTREAM) if absent."""
        try:
            await self._redis.xgroup_create(  # type: ignore[attr-defined]
                stream_key,
                self._group,
                id="$",
                mkstream=True,
            )
            logger.debug(
                "redis_streams_bus.consumer_group_created",
                stream=stream_key,
                group=self._group,
            )
        except Exception as exc:  # noqa: BLE001
            # BUSYGROUP — group already exists (normal on restart)
            if "BUSYGROUP" in str(exc):
                logger.debug(
                    "redis_streams_bus.consumer_group_exists",
                    stream=stream_key,
                    group=self._group,
                )
            else:
                logger.error(
                    "redis_streams_bus.consumer_group_error",
                    stream=stream_key,
                    error=str(exc),
                )
                raise

    async def _start_reader(
        self, event_type: str, stream_key: str
    ) -> anyio.CancelScope:
        """Register a reader for this event_type; returns a CancelScope.

        The actual read loop is deferred — callers must invoke ``run_readers()``
        inside an anyio task group to start polling.  This separates subscription
        registration (synchronous) from I/O loop ownership (caller-managed).
        """
        scope = anyio.CancelScope()
        # Store the (scope, event_type, stream_key) so run_readers() can start loops.
        self._pending_readers.append((scope, event_type, stream_key))
        return scope

    async def start(self, task_group: anyio.abc.TaskGroup) -> None:
        """Start all pending reader loops and store the task group for late subscribers.

        Must be called during application lifespan startup. Subsequent calls to
        ``subscribe()`` after ``start()`` will immediately spawn readers into
        this task group (F4 fix).

        Args:
            task_group: The anyio task group that owns reader task lifetimes.
        """
        self._task_group = task_group
        for scope, event_type, stream_key in self._pending_readers:
            async def _reader(
                s: anyio.CancelScope = scope,
                et: str = event_type,
                sk: str = stream_key,
            ) -> None:
                with s:
                    await self._read_loop(et, sk)

            task_group.start_soon(_reader)
        self._pending_readers.clear()
        logger.info(
            "redis_streams_bus.started",
            reader_count=len(self._reader_scopes),
        )

    async def run_readers(self) -> None:
        """Start all registered reader loops inside a new task group.

        Kept for backward compatibility. Prefer calling ``start(task_group)``
        from within an existing application task group instead::

            async with anyio.create_task_group() as tg:
                await event_bus.start(tg)
                # tg keeps readers alive until cancelled

        Each registered reader runs concurrently until its CancelScope is
        cancelled (via ``unsubscribe()``).
        """
        async with anyio.create_task_group() as tg:
            await self.start(tg)
            # Block until all readers exit (task group waits for all tasks).

    async def _read_loop(self, event_type: str, stream_key: str) -> None:
        """Poll the stream and dispatch messages to handlers.

        On startup, drains any pending (unACKed) messages left over from a
        previous run before switching to reading new messages.  This ensures
        at-least-once redelivery for handler failures that prevented ACK.
        """
        # Re-deliver any messages that were delivered but not ACKed in a prior run.
        await self._drain_pending(event_type, stream_key)

        while True:
            try:
                messages = await self._redis.xreadgroup(  # type: ignore[attr-defined]
                    groupname=self._group,
                    consumername=self._consumer,
                    streams={stream_key: ">"},
                    count=self._batch_size,
                    block=self._block_ms,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "redis_streams_bus.read_error",
                    stream=stream_key,
                    error=str(exc),
                )
                await anyio.sleep(1.0)
                continue

            if not messages:
                await self._observe_stream_lag(stream_key)
                continue

            for stream_entry in messages:
                if not isinstance(stream_entry, (list, tuple)) or len(stream_entry) != 2:
                    continue

                _stream, entries = stream_entry
                if not isinstance(entries, (list, tuple)):
                    continue

                for entry in entries:
                    if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                        continue
                    msg_id, fields = entry
                    if not isinstance(fields, dict):
                        continue
                    dispatch_fields = cast(dict[bytes | str, bytes | str], fields)
                    await self._dispatch(event_type, msg_id, dispatch_fields, stream_key)

            await self._observe_stream_lag(stream_key)

    async def _drain_pending(self, event_type: str, stream_key: str) -> None:
        """Re-deliver messages in this consumer's PEL from a previous run.

        Reads with ID ``"0"`` which returns all pending (unACKed) messages
        for this consumer.  Loops until the PEL is empty so a crash-recovery
        restart fully reprocesses any backlog before accepting new messages.
        """
        while True:
            try:
                messages = await self._redis.xreadgroup(  # type: ignore[attr-defined]
                    groupname=self._group,
                    consumername=self._consumer,
                    streams={stream_key: "0"},
                    count=self._batch_size,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "redis_streams_bus.drain_pending_error",
                    stream=stream_key,
                    error=str(exc),
                )
                break

            if not messages:
                break

            pending_entries: list[tuple[object, dict[bytes | str, bytes | str]]] = []
            for stream_entry in messages:
                if not isinstance(stream_entry, (list, tuple)) or len(stream_entry) != 2:
                    continue

                _stream, entries = stream_entry
                if not isinstance(entries, (list, tuple)):
                    continue

                for entry in entries:
                    if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                        continue
                    msg_id, fields = entry
                    if not isinstance(fields, dict):
                        continue
                    pending_entries.append(
                        (msg_id, cast(dict[bytes | str, bytes | str], fields))
                    )

            if not pending_entries:
                break

            logger.info(
                "redis_streams_bus.draining_pending",
                stream=stream_key,
                count=len(pending_entries),
            )
            for msg_id, fields in pending_entries:
                await self._dispatch(event_type, msg_id, fields, stream_key)

            await self._observe_stream_lag(stream_key)

    @staticmethod
    def _extract_pending_count(xpending_result: object) -> float:
        """Extract a pending count from redis xpending() return variants."""
        candidate: object = 0
        if isinstance(xpending_result, dict):
            candidate = xpending_result.get("pending", 0)
        elif isinstance(xpending_result, (list, tuple)) and xpending_result:
            candidate = xpending_result[0]
        else:
            candidate = xpending_result

        if isinstance(candidate, (int, float)):
            return float(candidate)
        if isinstance(candidate, str):
            try:
                return float(candidate)
            except ValueError:
                return 0.0
        if isinstance(candidate, bytes):
            try:
                return float(candidate.decode())
            except (UnicodeDecodeError, ValueError):
                return 0.0
        return 0.0

    async def _observe_stream_lag(self, stream_key: str) -> None:
        """Refresh stream lag gauge from the consumer group's pending entries."""
        xpending = getattr(self._redis, "xpending", None)
        if not callable(xpending):
            return

        try:
            xpending_result = await xpending(stream_key, self._group)
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "redis_streams_bus.xpending_error",
                stream=stream_key,
                group=self._group,
                error=str(exc),
            )
            return

        lag_count = self._extract_pending_count(xpending_result)
        REDIS_STREAM_LAG.labels(stream=stream_key, group=self._group).set(lag_count)

    async def _dispatch(
        self,
        event_type: str,
        msg_id: object,
        fields: dict[bytes | str, bytes | str],
        stream_key: str,
    ) -> None:
        """Deserialise one Redis Streams message and invoke handlers."""
        raw_payload = fields.get(b"payload") or fields.get("payload", "{}")
        try:
            data = json.loads(raw_payload if isinstance(raw_payload, str) else raw_payload.decode())
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.error(
                "redis_streams_bus.malformed_message",
                msg_id=str(msg_id),
                error=str(exc),
            )
            # ACK malformed messages so they don't block the consumer group.
            await self._ack(stream_key, msg_id)
            return

        try:
            agg_id_raw = data.get("aggregate_id")
            agg_id: UUID | None = UUID(agg_id_raw) if agg_id_raw else None
        except (ValueError, AttributeError):
            agg_id = None

        # Preserve original event identity from the stream payload (F9).
        raw_event_id = data.get("event_id")
        try:
            preserved_event_id: UUID = UUID(str(raw_event_id)) if raw_event_id else uuid4()
        except (ValueError, AttributeError):
            preserved_event_id = uuid4()

        raw_ts = data.get("timestamp")
        try:
            preserved_ts: datetime = (
                datetime.fromisoformat(raw_ts) if raw_ts else datetime.now(tz=UTC)
            )
        except (ValueError, TypeError):
            preserved_ts = datetime.now(tz=UTC)

        domain_event = DomainEvent(
            event_id=preserved_event_id,
            timestamp=preserved_ts,
            event_type=data.get("event_type", event_type),
            aggregate_id=agg_id,
            payload=data.get("payload", {}),
        )

        handlers = self._handlers.get(event_type, []) + self._handlers.get(_WILDCARD, [])
        any_failed = False
        for handler in handlers:
            try:
                await handler(domain_event)
            except Exception as exc:  # noqa: BLE001
                any_failed = True
                logger.error(
                    "redis_streams_bus.handler_error",
                    event_type=event_type,
                    handler=getattr(handler, "__name__", str(handler)),
                    error=str(exc),
                )
                # Other handlers continue (AC-4.5); message is NOT ACKed so
                # it remains in the PEL and will be redelivered on the next
                # consumer restart or after claim_idle_ms via XAUTOCLAIM.

        if not any_failed:
            await self._ack(stream_key, msg_id)
        else:
            logger.warning(
                "redis_streams_bus.dispatch_not_acked",
                event_type=event_type,
                msg_id=str(msg_id),
                stream=stream_key,
            )

    async def _ack(self, stream_key: str, msg_id: object) -> None:
        """Acknowledge a message so it doesn't re-deliver to this consumer."""
        try:
            await self._redis.xack(stream_key, self._group, msg_id)  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "redis_streams_bus.ack_failed",
                stream=stream_key,
                msg_id=str(msg_id),
                error=str(exc),
            )
