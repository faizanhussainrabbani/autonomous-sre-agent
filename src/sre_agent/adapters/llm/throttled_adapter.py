"""
Throttled LLM Adapter — Concurrency-limiting wrapper for LLMReasoningPort.

Enforces Engineering Standards §5.3 Rate Limiting & Backpressure:
- Max 10 concurrent LLM API calls (asyncio.Semaphore)
- Priority queue: high-severity calls (SEV1=1) processed before low-severity (SEV4=4)

Architecture: Implements the Bulkhead pattern — a fixed concurrency ceiling
prevents a surge of diagnostic calls from exhausting LLM rate-limit quotas.

Phase 2: Intelligence Layer — Gap B closure
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
from typing import Any

import structlog

from sre_agent.ports.llm import (
    Hypothesis,
    HypothesisRequest,
    LLMReasoningPort,
    TokenUsage,
    ValidationRequest,
    ValidationResult,
)

logger = structlog.get_logger(__name__)

# Engineering Standards §5.3: max concurrent LLM calls
_DEFAULT_MAX_CONCURRENT = 10


class ThrottledLLMAdapter(LLMReasoningPort):
    """LLMReasoningPort wrapper enforcing §5.3 Rate Limiting & Backpressure.

    Wraps any concrete LLMReasoningPort with:
    - An ``asyncio.Semaphore`` capping concurrent LLM API calls.
    - An ``asyncio.PriorityQueue`` ensuring higher-severity requests
      (lower SEV number = higher priority) are served before lower-severity
      ones when the semaphore is contested.

    Usage::

        inner = OpenAILLMAdapter(config)
        throttled = ThrottledLLMAdapter(inner, max_concurrent=10)
        # Callers set request.priority = 1 for SEV1, 4 for SEV4
        result = await throttled.generate_hypothesis(request)
        await throttled.close()  # on shutdown
    """

    _seq_counter: itertools.count = itertools.count()

    def __init__(
        self,
        inner: LLMReasoningPort,
        max_concurrent: int = _DEFAULT_MAX_CONCURRENT,
    ) -> None:
        """Initialise the throttled adapter.

        Args:
            inner: The concrete LLM adapter to throttle.
            max_concurrent: Maximum number of simultaneous LLM API calls.
        """
        self._inner = inner
        self._max_concurrent = max_concurrent

        # Async primitives — lazily created inside a running event loop.
        self._semaphore: asyncio.Semaphore | None = None
        self._queue: asyncio.PriorityQueue[  # type: ignore[type-arg]
            tuple[int, int, asyncio.Future[Any], Any, tuple[Any, ...]]
        ] | None = None
        self._drain_task: asyncio.Task[None] | None = None

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def _ensure_initialized(self) -> None:
        """Lazily initialise asyncio objects (must run inside an event loop)."""
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._max_concurrent)
            self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
            self._drain_task = asyncio.ensure_future(self._drain_loop())

    async def close(self) -> None:
        """Cancel the background drain task on shutdown."""
        if self._drain_task and not self._drain_task.done():
            self._drain_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._drain_task

    # -------------------------------------------------------------------------
    # Internal priority-queue machinery
    # -------------------------------------------------------------------------

    async def _drain_loop(self) -> None:
        """Background coroutine: drain the priority queue, honouring the concurrency cap.

        - Pulls items in priority order (lowest number = highest priority).
        - Acquires the semaphore *before* spawning execution, so the cap is
          respected and high-priority items are served first when slots open.
        """
        assert self._queue is not None
        assert self._semaphore is not None

        while True:
            priority, seq, fut, coro_func, args = await self._queue.get()

            if fut.cancelled():
                self._queue.task_done()
                continue

            # Block until a concurrency slot is available.
            # Because the drain loop is single-threaded, items are dequeued
            # strictly in priority order.
            await self._semaphore.acquire()

            # Spawn execution without blocking the drain loop.
            asyncio.ensure_future(self._execute(fut, coro_func, args))
            self._queue.task_done()

    async def _execute(
        self,
        fut: asyncio.Future[Any],
        coro_func: Any,
        args: tuple[Any, ...],
    ) -> None:
        """Run the LLM call with the semaphore already acquired, then release it."""
        try:
            result = await coro_func(*args)
            if not fut.done():
                fut.set_result(result)
        except Exception as exc:  # noqa: BLE001
            logger.warning("throttled_llm_call_failed", error=str(exc))
            if not fut.done():
                fut.set_exception(exc)
        finally:
            assert self._semaphore is not None
            self._semaphore.release()

    async def _enqueue(
        self,
        priority: int,
        coro_func: Any,
        *args: Any,
    ) -> Any:
        """Submit a call to the priority queue and await its completion.

        Args:
            priority: Call priority (1=highest/SEV1, 4=lowest/SEV4).
            coro_func: Coroutine-returning callable to invoke.
            *args: Arguments forwarded to ``coro_func``.

        Returns:
            The coroutine's result.
        """
        self._ensure_initialized()
        loop = asyncio.get_event_loop()
        fut: asyncio.Future[Any] = loop.create_future()
        seq = next(self._seq_counter)
        assert self._queue is not None
        await self._queue.put((priority, seq, fut, coro_func, args))

        logger.debug(
            "llm_call_enqueued",
            priority=priority,
            seq=seq,
            queue_depth=self._queue.qsize(),
        )

        return await fut

    # -------------------------------------------------------------------------
    # LLMReasoningPort implementation
    # -------------------------------------------------------------------------

    async def generate_hypothesis(self, request: HypothesisRequest) -> Hypothesis:
        """Generate hypothesis via the inner adapter with priority throttling."""
        priority = getattr(request, "priority", 3)
        return await self._enqueue(
            priority,
            self._inner.generate_hypothesis,
            request,
        )

    async def validate_hypothesis(self, request: ValidationRequest) -> ValidationResult:
        """Cross-validate hypothesis via the inner adapter with priority throttling."""
        priority = getattr(request, "priority", 3)
        return await self._enqueue(
            priority,
            self._inner.validate_hypothesis,
            request,
        )

    def count_tokens(self, text: str) -> int:
        """Delegate token counting to the inner adapter."""
        return self._inner.count_tokens(text)

    def get_token_usage(self) -> TokenUsage:
        """Delegate token usage tracking to the inner adapter."""
        return self._inner.get_token_usage()

    async def health_check(self) -> bool:
        """Delegate health check to the inner adapter."""
        return await self._inner.health_check()

    # -------------------------------------------------------------------------
    # Observability
    # -------------------------------------------------------------------------

    @property
    def queue_depth(self) -> int:
        """Number of calls currently waiting in the priority queue."""
        return self._queue.qsize() if self._queue is not None else 0

    @property
    def max_concurrent(self) -> int:
        """Configured concurrency ceiling."""
        return self._max_concurrent
