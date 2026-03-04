"""
Tests for Phase 1.5 — Resilience utilities (retry, circuit breaker).

Validates retry with exponential backoff, circuit breaker state transitions,
and error taxonomy classification.
"""

from __future__ import annotations

import asyncio

import pytest

from sre_agent.adapters.cloud.resilience import (
    AuthenticationError,
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
    RateLimitError,
    RetryConfig,
    TransientError,
    retry_with_backoff,
)


# ---------------------------------------------------------------------------
# Circuit Breaker tests
# ---------------------------------------------------------------------------

def test_circuit_starts_closed():
    cb = CircuitBreaker(name="test")
    assert cb.state == CircuitState.CLOSED


def test_circuit_opens_after_threshold():
    cb = CircuitBreaker(failure_threshold=3, name="test")
    for _ in range(3):
        cb.record_failure()
    assert cb.state == CircuitState.OPEN


def test_circuit_resets_on_success():
    cb = CircuitBreaker(failure_threshold=3, name="test")
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb._failure_count == 0


def test_circuit_half_open_after_recovery_timeout():
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout_seconds=0.0, name="test")
    cb.record_failure()
    assert cb._state == CircuitState.OPEN
    # With 0s timeout, immediately transitions to half-open
    assert cb.state == CircuitState.HALF_OPEN


# ---------------------------------------------------------------------------
# Retry tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retry_succeeds_on_first_attempt():
    call_count = 0

    async def success():
        nonlocal call_count
        call_count += 1
        return "ok"

    result = await retry_with_backoff(success, config=RetryConfig(max_retries=3))
    assert result == "ok"
    assert call_count == 1


@pytest.mark.asyncio
async def test_retry_succeeds_after_transient_failures():
    call_count = 0

    async def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise TransientError("temporary")
        return "recovered"

    result = await retry_with_backoff(
        flaky,
        config=RetryConfig(max_retries=3, base_delay_seconds=0.01),
    )
    assert result == "recovered"
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_exhausted_raises():
    async def always_fail():
        raise TransientError("permanent")

    with pytest.raises(TransientError, match="retries exhausted"):
        await retry_with_backoff(
            always_fail,
            config=RetryConfig(max_retries=2, base_delay_seconds=0.01),
        )


@pytest.mark.asyncio
async def test_non_retryable_fails_immediately():
    call_count = 0

    async def auth_fail():
        nonlocal call_count
        call_count += 1
        raise AuthenticationError("bad creds")

    with pytest.raises(AuthenticationError):
        await retry_with_backoff(
            auth_fail,
            config=RetryConfig(max_retries=3),
        )
    assert call_count == 1  # No retries


@pytest.mark.asyncio
async def test_circuit_breaker_rejects_when_open():
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout_seconds=60, name="test")
    cb.record_failure()  # Opens the circuit

    async def noop():
        return "ok"

    with pytest.raises(CircuitOpenError):
        await retry_with_backoff(noop, circuit_breaker=cb)


@pytest.mark.asyncio
async def test_rate_limit_is_retryable():
    call_count = 0

    async def rate_limited():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise RateLimitError("throttled")
        return "ok"

    result = await retry_with_backoff(
        rate_limited,
        config=RetryConfig(max_retries=3, base_delay_seconds=0.01),
    )
    assert result == "ok"
    assert call_count == 2
