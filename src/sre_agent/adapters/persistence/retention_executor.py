"""Background retention executor for persistence tables.

Applies app-managed cleanup for monotonic-growth tables that now have
retention support indexes:
- processed_events(processed_at)
- baseline_snapshots(generated_at)
"""

from __future__ import annotations

import time
from typing import Any

import anyio
import structlog

from sre_agent.observability.metrics import DB_POOL_ACTIVE_CONNECTIONS, DB_QUERY_DURATION

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

_DELETE_OLD_PROCESSED_EVENTS = """
WITH deleted AS (
    DELETE FROM processed_events
    WHERE processed_at < now() - ($1::int * INTERVAL '1 day')
    RETURNING 1
)
SELECT count(*) AS deleted_count FROM deleted
"""

_DELETE_OLD_BASELINE_SNAPSHOTS = """
WITH deleted AS (
    DELETE FROM baseline_snapshots
    WHERE generated_at < now() - ($1::int * INTERVAL '1 day')
    RETURNING 1
)
SELECT count(*) AS deleted_count FROM deleted
"""

_DB_ADAPTER_LABEL = "postgres_retention_executor"


def _observe_db_query(operation: str, statement_type: str, started_at: float) -> None:
    """Observe SQL statement latency for persistence adapters."""
    elapsed = max(0.0, time.monotonic() - started_at)
    DB_QUERY_DURATION.labels(
        adapter=_DB_ADAPTER_LABEL,
        operation=operation,
        statement_type=statement_type,
    ).observe(elapsed)


def _observe_pool_active(pool: Any) -> None:
    """Set DB_POOL_ACTIVE_CONNECTIONS when pool introspection is available."""
    get_size = getattr(pool, "get_size", None)
    get_idle_size = getattr(pool, "get_idle_size", None)
    if not callable(get_size) or not callable(get_idle_size):
        return

    try:
        active = max(int(get_size()) - int(get_idle_size()), 0)
    except Exception:  # noqa: BLE001
        return

    DB_POOL_ACTIVE_CONNECTIONS.labels(adapter=_DB_ADAPTER_LABEL).set(active)


class RetentionExecutor:
    """Periodic retention executor for persistence cleanup."""

    def __init__(
        self,
        pool: Any,
        *,
        poll_interval_s: float = 3600.0,
        processed_events_retention_days: int = 30,
        baseline_snapshots_retention_days: int = 90,
    ) -> None:
        self._pool = pool
        self._poll_interval_s = poll_interval_s
        self._processed_events_retention_days = processed_events_retention_days
        self._baseline_snapshots_retention_days = baseline_snapshots_retention_days
        self._running = False

    async def run_once(self) -> dict[str, int]:
        """Execute one cleanup cycle and return deleted row counts."""
        async with self._pool.acquire() as conn:
            _observe_pool_active(self._pool)

            started = time.monotonic()
            processed_deleted = int(
                await conn.fetchval(
                    _DELETE_OLD_PROCESSED_EVENTS,
                    self._processed_events_retention_days,
                )
                or 0
            )
            _observe_db_query("retention.delete_processed_events", "delete", started)

            started = time.monotonic()
            baseline_deleted = int(
                await conn.fetchval(
                    _DELETE_OLD_BASELINE_SNAPSHOTS,
                    self._baseline_snapshots_retention_days,
                )
                or 0
            )
            _observe_db_query("retention.delete_baseline_snapshots", "delete", started)

        counts = {
            "processed_events_deleted": processed_deleted,
            "baseline_snapshots_deleted": baseline_deleted,
        }
        logger.info("retention_executor.run_once_complete", **counts)
        return counts

    async def run(self) -> None:
        """Run periodic cleanup until stop() is called."""
        self._running = True
        logger.info(
            "retention_executor.started",
            poll_interval_s=self._poll_interval_s,
            processed_events_days=self._processed_events_retention_days,
            baseline_snapshots_days=self._baseline_snapshots_retention_days,
        )
        while self._running:
            try:
                await self.run_once()
            except Exception as exc:  # noqa: BLE001
                logger.warning("retention_executor.run_once_failed", error=str(exc))
            await anyio.sleep(self._poll_interval_s)

        logger.info("retention_executor.stopped")

    def stop(self) -> None:
        """Signal the periodic loop to stop on the next iteration."""
        self._running = False
