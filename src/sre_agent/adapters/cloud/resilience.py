"""
Resilience utilities for cloud operator adapters.

Provides retry with exponential backoff and circuit breaker patterns
for all CloudOperatorPort implementations.

Phase 1.5: Follows FAANG-standard resilience patterns (Netflix Hystrix,
Google SRE error budget, AWS Well-Architected retry guidance).
"""

from __future__ import annotations

import asyncio
import functools
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, TypeVar

import structlog

from sre_agent.adapters.telemetry.metrics import CIRCUIT_BREAKER_STATE

logger = structlog.get_logger(__name__)

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Custom exceptions for cloud operator errors
# ---------------------------------------------------------------------------

class CloudOperatorError(Exception):
    """Base exception for cloud operator failures."""


class AuthenticationError(CloudOperatorError):
    """Cloud credentials are invalid or expired."""


class RateLimitError(CloudOperatorError):
    """API rate limit exceeded."""


class ResourceNotFoundError(CloudOperatorError):
    """Target resource does not exist."""


class TransientError(CloudOperatorError):
    """Transient error that may succeed on retry (5xx, timeouts)."""


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------

class CircuitState(Enum):
    CLOSED = "closed"        # Normal operation
    OPEN = "open"            # Failing — reject requests immediately
    HALF_OPEN = "half_open"  # Testing — allow one request to probe


@dataclass
class CircuitBreaker:
    """Simple circuit breaker with configurable thresholds.

    - CLOSED: normal; tracks consecutive failures
    - OPEN: rejects all calls immediately; resets after `recovery_timeout`
    - HALF_OPEN: allows one probe call; success → CLOSED, failure → OPEN
    """

    failure_threshold: int = 5
    recovery_timeout_seconds: float = 30.0
    name: str = "default"

    # Internal state
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _last_failure_time: float = field(default=0.0, init=False)

    def _set_state_gauge(self) -> None:
        """Export current circuit breaker state to Prometheus (OBS-009).

        Gauge values:  0 = CLOSED,  1 = HALF_OPEN,  2 = OPEN.
        Labels use the breaker ``name`` as ``resource_type``; provider defaults
        to "cloud" since circuit breakers are not provider-specific here.
        """
        _state_values = {
            CircuitState.CLOSED: 0,
            CircuitState.HALF_OPEN: 1,
            CircuitState.OPEN: 2,
        }
        CIRCUIT_BREAKER_STATE.labels(
            provider="cloud",
            resource_type=self.name,
        ).set(_state_values.get(self._state, 0))

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self.recovery_timeout_seconds:
                self._state = CircuitState.HALF_OPEN
                self._set_state_gauge()
                logger.info(
                    "circuit_half_open",
                    breaker=self.name,
                    elapsed=round(elapsed, 1),
                )
        return self._state

    def record_success(self) -> None:
        self._failure_count = 0
        if self._state != CircuitState.CLOSED:
            logger.info("circuit_closed", breaker=self.name)
        self._state = CircuitState.CLOSED
        self._set_state_gauge()

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            self._set_state_gauge()
            logger.warning(
                "circuit_opened",
                breaker=self.name,
                failures=self._failure_count,
                recovery_seconds=self.recovery_timeout_seconds,
            )


class CircuitOpenError(CloudOperatorError):
    """Circuit breaker is open — calls are rejected."""


# ---------------------------------------------------------------------------
# Retry with exponential backoff
# ---------------------------------------------------------------------------

@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0
    exponential_base: float = 2.0
    retryable_exceptions: tuple[type[Exception], ...] = (
        TransientError,
        RateLimitError,
        ConnectionError,
        TimeoutError,
    )
    non_retryable_exceptions: tuple[type[Exception], ...] = (
        AuthenticationError,
        ResourceNotFoundError,
    )


async def retry_with_backoff(
    func: Callable[..., Any],
    *args: Any,
    config: RetryConfig | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    **kwargs: Any,
) -> Any:
    """Execute an async function with retry, backoff, and optional circuit breaker.

    Args:
        func: Async callable to execute.
        *args: Positional arguments for func.
        config: Retry configuration.
        circuit_breaker: Optional circuit breaker instance.
        **kwargs: Keyword arguments for func.

    Returns:
        The result of the function call.

    Raises:
        CircuitOpenError: If the circuit breaker is open.
        CloudOperatorError: If all retries are exhausted.
    """
    cfg = config or RetryConfig()
    last_exception: Exception | None = None

    for attempt in range(cfg.max_retries + 1):
        # Check circuit breaker
        if circuit_breaker is not None:
            state = circuit_breaker.state
            if state == CircuitState.OPEN:
                raise CircuitOpenError(
                    f"Circuit breaker '{circuit_breaker.name}' is OPEN. "
                    f"Recovering in {circuit_breaker.recovery_timeout_seconds}s."
                )

        try:
            result = await func(*args, **kwargs)

            # Success — record it
            if circuit_breaker is not None:
                circuit_breaker.record_success()

            return result

        except cfg.non_retryable_exceptions as exc:
            logger.error(
                "non_retryable_error",
                error=str(exc),
                attempt=attempt + 1,
            )
            if circuit_breaker is not None:
                circuit_breaker.record_failure()
            raise

        except cfg.retryable_exceptions as exc:
            last_exception = exc

            if circuit_breaker is not None:
                circuit_breaker.record_failure()

            if attempt >= cfg.max_retries:
                break

            delay = min(
                cfg.base_delay_seconds * (cfg.exponential_base ** attempt),
                cfg.max_delay_seconds,
            )

            logger.warning(
                "retry_attempt",
                error=str(exc),
                attempt=attempt + 1,
                max_retries=cfg.max_retries,
                delay_seconds=round(delay, 2),
            )

            await asyncio.sleep(delay)

        except Exception as exc:
            # Unexpected exception — don't retry
            if circuit_breaker is not None:
                circuit_breaker.record_failure()
            raise

    raise TransientError(
        f"All {cfg.max_retries} retries exhausted. Last error: {last_exception}"
    ) from last_exception


# ---------------------------------------------------------------------------
# Decorator for convenience
# ---------------------------------------------------------------------------

def with_resilience(
    retry_config: RetryConfig | None = None,
    circuit_breaker: CircuitBreaker | None = None,
):
    """Decorator that wraps an async method with retry + circuit breaker."""

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            return await retry_with_backoff(
                func,
                *args,
                config=retry_config,
                circuit_breaker=circuit_breaker,
                **kwargs,
            )
        return wrapper

    return decorator
