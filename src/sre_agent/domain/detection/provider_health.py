"""
Provider Health Monitor — continuous health checking with circuit breaker.

Runs periodic health checks on the active telemetry provider, transitions
to degraded mode on failure, and emits domain events for the operator
dashboard and notification system.

Implements: Task 13.7 — Provider health monitoring
Validates: AC-1.5.3, AC-1.5.4 (internal alert + degraded mode)
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

import structlog

from sre_agent.domain.models.canonical import DomainEvent, EventTypes
from sre_agent.ports.events import EventBus

logger = structlog.get_logger(__name__)


class CircuitState(Enum):
    """Circuit breaker states per Engineering Standards §3.2."""
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failures exceeded threshold — provider considered down
    HALF_OPEN = "half_open" # Testing if provider has recovered


class ProviderHealthMonitor:
    """Monitors telemetry provider health with circuit breaker pattern.

    Per Engineering Standards §3.2: 3 consecutive API failures → OPEN state,
    then fall back to cached data and flag "degraded telemetry".
    """

    def __init__(
        self,
        event_bus: EventBus | None = None,
        failure_threshold: int = 3,
        recovery_probe_interval_seconds: int = 30,
    ) -> None:
        self._event_bus = event_bus
        self._failure_threshold = failure_threshold
        self._recovery_probe_interval = recovery_probe_interval_seconds

        # Per-component circuit state
        self._circuits: dict[str, CircuitState] = {}
        self._consecutive_failures: dict[str, int] = {}
        self._last_failure_time: dict[str, datetime] = {}
        self._health_history: list[dict[str, Any]] = []

    def register_component(self, component_name: str) -> None:
        """Register a component for health monitoring."""
        self._circuits[component_name] = CircuitState.CLOSED
        self._consecutive_failures[component_name] = 0

    @property
    def components(self) -> dict[str, CircuitState]:
        """Current circuit state for all registered components."""
        return dict(self._circuits)

    def get_circuit_state(self, component: str) -> CircuitState:
        """Get the circuit breaker state for a component."""
        return self._circuits.get(component, CircuitState.CLOSED)

    def is_component_healthy(self, component: str) -> bool:
        """Check if a component's circuit is CLOSED (healthy)."""
        return self.get_circuit_state(component) == CircuitState.CLOSED

    @property
    def is_any_degraded(self) -> bool:
        """True if any component has an open circuit."""
        return any(s == CircuitState.OPEN for s in self._circuits.values())

    @property
    def degraded_components(self) -> list[str]:
        """List of components with open circuits."""
        return [c for c, s in self._circuits.items() if s == CircuitState.OPEN]

    async def record_success(self, component: str) -> None:
        """Record a successful health check for a component."""
        previous_state = self._circuits.get(component, CircuitState.CLOSED)
        self._consecutive_failures[component] = 0
        self._circuits[component] = CircuitState.CLOSED

        self._health_history.append({
            "component": component,
            "status": "success",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        if previous_state != CircuitState.CLOSED:
            logger.info(
                "circuit_breaker_closed",
                component=component,
                previous_state=previous_state.value,
            )
            if self._event_bus:
                await self._event_bus.publish(
                    DomainEvent(
                        event_type=EventTypes.PROVIDER_HEALTH_CHANGED,
                        payload={
                            "component": component,
                            "circuit_state": "closed",
                            "recovered": True,
                        },
                    )
                )

    async def record_failure(self, component: str, error: str = "") -> None:
        """Record a failed health check. Opens circuit after threshold."""
        self._consecutive_failures[component] = (
            self._consecutive_failures.get(component, 0) + 1
        )
        self._last_failure_time[component] = datetime.now(timezone.utc)

        failures = self._consecutive_failures[component]

        self._health_history.append({
            "component": component,
            "status": "failure",
            "error": error,
            "consecutive_failures": failures,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        if failures >= self._failure_threshold:
            previous_state = self._circuits.get(component, CircuitState.CLOSED)
            self._circuits[component] = CircuitState.OPEN

            if previous_state != CircuitState.OPEN:
                logger.warning(
                    "circuit_breaker_opened",
                    component=component,
                    consecutive_failures=failures,
                    threshold=self._failure_threshold,
                    error=error,
                )
                if self._event_bus:
                    await self._event_bus.publish(
                        DomainEvent(
                            event_type=EventTypes.PROVIDER_HEALTH_CHANGED,
                            payload={
                                "component": component,
                                "circuit_state": "open",
                                "consecutive_failures": failures,
                                "error": error,
                            },
                        )
                    )
        else:
            logger.warning(
                "health_check_failure",
                component=component,
                consecutive_failures=failures,
                threshold=self._failure_threshold,
                error=error,
            )

    async def attempt_recovery(self, component: str) -> None:
        """Transition from OPEN to HALF_OPEN to allow a recovery probe."""
        if self._circuits.get(component) == CircuitState.OPEN:
            self._circuits[component] = CircuitState.HALF_OPEN
            logger.info("circuit_breaker_half_open", component=component)

    def get_health_summary(self) -> dict[str, Any]:
        """Get a summary of all component health states."""
        return {
            "components": {
                name: {
                    "state": state.value,
                    "consecutive_failures": self._consecutive_failures.get(name, 0),
                    "last_failure": (
                        self._last_failure_time[name].isoformat()
                        if name in self._last_failure_time
                        else None
                    ),
                }
                for name, state in self._circuits.items()
            },
            "is_degraded": self.is_any_degraded,
            "degraded_components": self.degraded_components,
        }
