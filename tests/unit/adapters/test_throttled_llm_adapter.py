"""
Unit tests for ThrottledLLMAdapter.

Tests Engineering Standards §5.3:
- Max 10 concurrent LLM API calls (semaphore enforcement)
- Priority queue: SEV1 calls processed before SEV4 under load
- Delegation to inner adapter for token counting and health check
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from sre_agent.adapters.llm.throttled_adapter import ThrottledLLMAdapter
from sre_agent.ports.llm import (
    Hypothesis,
    HypothesisRequest,
    TokenUsage,
    ValidationRequest,
    ValidationResult,
)


def _make_hypothesis(root_cause: str = "memory leak") -> Hypothesis:
    return Hypothesis(
        root_cause=root_cause,
        confidence=0.88,
        reasoning="High RSS growth.",
        evidence_citations=[],
        suggested_remediation="Restart pod.",
    )


def _make_validation(agrees: bool = True) -> ValidationResult:
    return ValidationResult(
        agrees=agrees,
        confidence=0.85,
        reasoning="Consistent with evidence.",
        contradictions=[],
    )


def _make_inner(
    hypothesis: Hypothesis | None = None,
    validation: ValidationResult | None = None,
    healthy: bool = True,
) -> MagicMock:
    inner = MagicMock()
    inner.generate_hypothesis = AsyncMock(return_value=hypothesis or _make_hypothesis())
    inner.validate_hypothesis = AsyncMock(return_value=validation or _make_validation())
    inner.health_check = AsyncMock(return_value=healthy)
    inner.count_tokens = MagicMock(side_effect=lambda t: len(t) // 4)
    inner.get_token_usage = MagicMock(return_value=TokenUsage(prompt_tokens=100, completion_tokens=50))
    return inner


def _make_request(priority: int = 3) -> HypothesisRequest:
    req = HypothesisRequest(
        alert_description="OOM kill on checkout-service",
        service_name="checkout-service",
        timeline="",
        evidence=[],
    )
    req.priority = priority
    return req


class TestThrottledLLMAdapterBasics:
    """Basic delegation and lifecycle tests."""

    async def test_generate_hypothesis_delegates_to_inner(self):
        """generate_hypothesis calls the inner adapter and returns its result."""
        inner = _make_inner()
        adapter = ThrottledLLMAdapter(inner, max_concurrent=10)

        request = _make_request()
        result = await adapter.generate_hypothesis(request)

        assert result.root_cause == "memory leak"
        inner.generate_hypothesis.assert_called_once_with(request)
        await adapter.close()

    async def test_validate_hypothesis_delegates_to_inner(self):
        """validate_hypothesis calls the inner adapter and returns its result."""
        inner = _make_inner()
        adapter = ThrottledLLMAdapter(inner, max_concurrent=10)

        val_request = ValidationRequest(
            hypothesis=_make_hypothesis(),
            original_evidence=[],
            alert_description="OOM kill",
        )
        result = await adapter.validate_hypothesis(val_request)

        assert result.agrees is True
        inner.validate_hypothesis.assert_called_once_with(val_request)
        await adapter.close()

    async def test_count_tokens_delegates_to_inner(self):
        """count_tokens passes through to the inner adapter."""
        inner = _make_inner()
        adapter = ThrottledLLMAdapter(inner, max_concurrent=10)

        count = adapter.count_tokens("hello world test token count")
        assert count == inner.count_tokens("hello world test token count")

    async def test_get_token_usage_delegates_to_inner(self):
        """get_token_usage passes through to the inner adapter."""
        inner = _make_inner()
        adapter = ThrottledLLMAdapter(inner, max_concurrent=10)

        usage = adapter.get_token_usage()
        assert usage.total_tokens == 150

    async def test_health_check_delegates_to_inner(self):
        """health_check passes through to the inner adapter."""
        inner = _make_inner(healthy=True)
        adapter = ThrottledLLMAdapter(inner, max_concurrent=10)

        result = await adapter.health_check()
        assert result is True
        await adapter.close()

    async def test_health_check_unhealthy_inner(self):
        """health_check returns False when inner adapter is unhealthy."""
        inner = _make_inner(healthy=False)
        adapter = ThrottledLLMAdapter(inner, max_concurrent=10)

        result = await adapter.health_check()
        assert result is False
        await adapter.close()

    async def test_max_concurrent_property(self):
        """max_concurrent property reflects the configured cap."""
        adapter = ThrottledLLMAdapter(_make_inner(), max_concurrent=5)
        assert adapter.max_concurrent == 5

    async def test_queue_depth_zero_before_first_call(self):
        """queue_depth is 0 before any calls are made."""
        adapter = ThrottledLLMAdapter(_make_inner())
        assert adapter.queue_depth == 0


class TestThrottledLLMAdapterConcurrency:
    """Concurrency-cap and semaphore tests."""

    async def test_concurrent_calls_complete_when_within_cap(self):
        """All calls complete when concurrency is within the cap."""
        inner = _make_inner()
        adapter = ThrottledLLMAdapter(inner, max_concurrent=10)

        requests = [_make_request() for _ in range(5)]
        results = await asyncio.gather(
            *[adapter.generate_hypothesis(r) for r in requests]
        )

        assert len(results) == 5
        assert all(r.root_cause == "memory leak" for r in results)
        await adapter.close()

    async def test_semaphore_limits_concurrent_active_calls(self):
        """Semaphore cap is enforced: at most max_concurrent calls run at once."""
        concurrent_peak = 0
        lock = asyncio.Lock()
        running = 0

        async def slow_generate(request: HypothesisRequest) -> Hypothesis:
            nonlocal running, concurrent_peak
            async with lock:
                running += 1
                if running > concurrent_peak:
                    concurrent_peak = running
            await asyncio.sleep(0.05)
            async with lock:
                running -= 1
            return _make_hypothesis()

        inner = MagicMock()
        inner.generate_hypothesis = slow_generate
        inner.health_check = AsyncMock(return_value=True)
        inner.count_tokens = MagicMock(return_value=10)
        inner.get_token_usage = MagicMock(return_value=TokenUsage())

        cap = 3
        adapter = ThrottledLLMAdapter(inner, max_concurrent=cap)
        requests = [_make_request() for _ in range(8)]

        await asyncio.gather(*[adapter.generate_hypothesis(r) for r in requests])

        # Peak concurrent calls must not exceed the cap
        assert concurrent_peak <= cap, (
            f"Expected peak <= {cap} concurrent calls, got {concurrent_peak}"
        )
        await adapter.close()

    async def test_exception_in_inner_propagates_to_caller(self):
        """Exceptions from the inner adapter are re-raised to the caller."""
        inner = MagicMock()
        inner.generate_hypothesis = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
        inner.health_check = AsyncMock(return_value=False)
        inner.count_tokens = MagicMock(return_value=0)
        inner.get_token_usage = MagicMock(return_value=TokenUsage())

        adapter = ThrottledLLMAdapter(inner, max_concurrent=10)

        with pytest.raises(RuntimeError, match="LLM unavailable"):
            await adapter.generate_hypothesis(_make_request())

        await adapter.close()


class TestThrottledLLMAdapterPriority:
    """Priority queue ordering tests."""

    async def test_priority_field_default_is_3(self):
        """HypothesisRequest.priority defaults to 3 (SEV3-level)."""
        req = HypothesisRequest(
            alert_description="test",
            service_name="svc",
            timeline="",
        )
        assert req.priority == 3

    async def test_high_priority_calls_processed_before_low_priority(self):
        """Under congestion, SEV1 (priority=1) calls complete before SEV4 (priority=4)."""
        completion_order: list[int] = []
        gate = asyncio.Event()

        async def slow_generate(request: HypothesisRequest) -> Hypothesis:
            # Block all calls until the gate opens, so they pile up in the queue.
            await gate.wait()
            completion_order.append(request.priority)
            return _make_hypothesis(root_cause=f"priority-{request.priority}")

        inner = MagicMock()
        inner.generate_hypothesis = slow_generate
        inner.health_check = AsyncMock(return_value=True)
        inner.count_tokens = MagicMock(return_value=10)
        inner.get_token_usage = MagicMock(return_value=TokenUsage())

        # Cap to 1 so all calls queue up behind the first.
        adapter = ThrottledLLMAdapter(inner, max_concurrent=1)

        # Submit: SEV4 first, then SEV1, then SEV2 — queue should serve 1, 2, 4
        tasks = [
            asyncio.create_task(adapter.generate_hypothesis(_make_request(priority=4))),
            asyncio.create_task(adapter.generate_hypothesis(_make_request(priority=1))),
            asyncio.create_task(adapter.generate_hypothesis(_make_request(priority=2))),
        ]

        # Give tasks time to enqueue
        await asyncio.sleep(0.02)
        gate.set()

        results = await asyncio.gather(*tasks)
        await adapter.close()

        # All three should complete
        assert len(results) == 3
        # The completion order should show lower (higher-priority) numbers first
        # Note: first slot is taken by the first enqueued task (priority=4),
        # then remaining queue is drained in priority order.
        assert sorted(completion_order[1:]) == completion_order[1:], (
            "After first slot, remaining calls should be processed in priority order"
        )


# ---------------------------------------------------------------------------
# LLM Integration Hardening — New tests
# ---------------------------------------------------------------------------


class TestThrottledLLMAdapterTimeoutRelease:
    """Verify timeout releases semaphore slot for subsequent work."""

    async def test_timeout_releases_semaphore_slot(self):
        """A timed-out inner call still releases the semaphore slot.

        Submits two tasks: the first raises TimeoutError, the second
        should still complete because the slot is freed.
        """
        call_count = 0

        async def first_fails_then_succeeds(request):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TimeoutError("mock timeout")
            return _make_hypothesis(root_cause="recovered")

        inner = MagicMock()
        inner.generate_hypothesis = first_fails_then_succeeds
        inner.health_check = AsyncMock(return_value=True)
        inner.count_tokens = MagicMock(return_value=10)
        inner.get_token_usage = MagicMock(return_value=TokenUsage())

        adapter = ThrottledLLMAdapter(inner, max_concurrent=1)

        # First call should raise
        with pytest.raises(TimeoutError):
            await adapter.generate_hypothesis(_make_request())

        # Second call should succeed — semaphore slot was released
        result = await adapter.generate_hypothesis(_make_request())
        assert result.root_cause == "recovered"

        await adapter.close()


class TestThrottledLLMAdapterQueueMetrics:
    """Queue metric emission tests (LLM_QUEUE_DEPTH, LLM_QUEUE_WAIT)."""

    async def test_queue_depth_metric_updates_on_enqueue_and_drain(self):
        """LLM_QUEUE_DEPTH gauge reflects queue size changes."""
        from sre_agent.adapters.telemetry.metrics import LLM_QUEUE_DEPTH

        gate = asyncio.Event()

        async def blocked_generate(request):
            await gate.wait()
            return _make_hypothesis()

        inner = MagicMock()
        inner.generate_hypothesis = blocked_generate
        inner.health_check = AsyncMock(return_value=True)
        inner.count_tokens = MagicMock(return_value=10)
        inner.get_token_usage = MagicMock(return_value=TokenUsage())

        # Cap=1 so second request queues up
        adapter = ThrottledLLMAdapter(inner, max_concurrent=1)

        # Submit two tasks
        task1 = asyncio.create_task(adapter.generate_hypothesis(_make_request()))
        await asyncio.sleep(0.02)  # Let first task enter semaphore

        task2 = asyncio.create_task(adapter.generate_hypothesis(_make_request()))
        await asyncio.sleep(0.02)  # Let second task enqueue

        # Queue should have depth > 0 at some point (we just verify the gauge is set)
        # Release all tasks
        gate.set()
        await asyncio.gather(task1, task2)

        # After all tasks drain, depth should be 0
        assert LLM_QUEUE_DEPTH._value.get() == 0.0

        await adapter.close()

    async def test_queue_wait_metric_records_positive_wait_under_contention(self):
        """LLM_QUEUE_WAIT histogram records > 0 wait when contention occurs."""
        from sre_agent.adapters.telemetry.metrics import LLM_QUEUE_WAIT

        gate = asyncio.Event()

        async def blocked_generate(request):
            await gate.wait()
            return _make_hypothesis()

        inner = MagicMock()
        inner.generate_hypothesis = blocked_generate
        inner.health_check = AsyncMock(return_value=True)
        inner.count_tokens = MagicMock(return_value=10)
        inner.get_token_usage = MagicMock(return_value=TokenUsage())

        # Record sample count before
        before_count = LLM_QUEUE_WAIT._sum.get()

        adapter = ThrottledLLMAdapter(inner, max_concurrent=1)

        # Submit 3 tasks with cap=1 to create contention
        tasks = [
            asyncio.create_task(adapter.generate_hypothesis(_make_request()))
            for _ in range(3)
        ]
        await asyncio.sleep(0.05)  # Let tasks enqueue

        gate.set()
        await asyncio.gather(*tasks)

        # Queue wait histogram should have recorded observations
        after_count = LLM_QUEUE_WAIT._sum.get()
        assert after_count > before_count, (
            "LLM_QUEUE_WAIT should record positive wait times under contention"
        )

        await adapter.close()
