"""
Unit tests for ProviderHealthMonitor — Task 13.7, AC-1.5.2/3/4.

Validates circuit breaker state transitions, degraded mode flagging,
and health summary reporting.
"""

from __future__ import annotations

import pytest

from sre_agent.domain.detection.provider_health import (
    CircuitState,
    ProviderHealthMonitor,
)
from sre_agent.events.in_memory import InMemoryEventBus


@pytest.fixture
def monitor() -> ProviderHealthMonitor:
    """Fresh ProviderHealthMonitor with default threshold (3 failures)."""
    bus = InMemoryEventBus()
    phm = ProviderHealthMonitor(event_bus=bus, failure_threshold=3)
    phm.register_component("prometheus")
    phm.register_component("jaeger")
    return phm


@pytest.mark.unit
class TestProviderHealthRegistration:
    """Verify component registration and initial state."""

    def test_register_component_sets_closed(self, monitor: ProviderHealthMonitor) -> None:
        """Newly registered component starts in CLOSED (healthy) state."""
        assert monitor.get_circuit_state("prometheus") == CircuitState.CLOSED

    def test_unregistered_component_defaults_to_closed(self, monitor: ProviderHealthMonitor) -> None:
        """Unregistered component returns CLOSED by default."""
        assert monitor.get_circuit_state("unknown") == CircuitState.CLOSED

    def test_components_returns_all_registered(self, monitor: ProviderHealthMonitor) -> None:
        """All registered components are visible."""
        assert set(monitor.components.keys()) == {"prometheus", "jaeger"}

    def test_is_component_healthy_initially(self, monitor: ProviderHealthMonitor) -> None:
        """Initial state is healthy for registered components."""
        assert monitor.is_component_healthy("prometheus") is True


@pytest.mark.unit
class TestCircuitBreakerTransitions:
    """Verify circuit breaker state machine (CLOSED → OPEN → HALF_OPEN → CLOSED)."""

    @pytest.mark.asyncio
    async def test_single_failure_stays_closed(self, monitor: ProviderHealthMonitor) -> None:
        """One failure below threshold keeps circuit CLOSED."""
        await monitor.record_failure("prometheus", error="connection refused")
        assert monitor.get_circuit_state("prometheus") == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_threshold_failures_opens_circuit(self, monitor: ProviderHealthMonitor) -> None:
        """AC-1.5.3: 3 consecutive failures → circuit OPEN."""
        for _ in range(3):
            await monitor.record_failure("prometheus", error="timeout")
        assert monitor.get_circuit_state("prometheus") == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_open_circuit_flags_degraded(self, monitor: ProviderHealthMonitor) -> None:
        """AC-1.5.4: Open circuit flags system as degraded."""
        for _ in range(3):
            await monitor.record_failure("prometheus")
        assert monitor.is_any_degraded is True
        assert "prometheus" in monitor.degraded_components

    @pytest.mark.asyncio
    async def test_success_resets_failure_counter(self, monitor: ProviderHealthMonitor) -> None:
        """Success after 2 failures resets counter, stays CLOSED."""
        await monitor.record_failure("prometheus")
        await monitor.record_failure("prometheus")
        await monitor.record_success("prometheus")
        assert monitor.get_circuit_state("prometheus") == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_attempt_recovery_half_open(self, monitor: ProviderHealthMonitor) -> None:
        """OPEN → HALF_OPEN via attempt_recovery."""
        for _ in range(3):
            await monitor.record_failure("prometheus")
        await monitor.attempt_recovery("prometheus")
        assert monitor.get_circuit_state("prometheus") == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_success_after_half_open_closes(self, monitor: ProviderHealthMonitor) -> None:
        """HALF_OPEN + success → CLOSED (recovery confirmed)."""
        for _ in range(3):
            await monitor.record_failure("prometheus")
        await monitor.attempt_recovery("prometheus")
        await monitor.record_success("prometheus")
        assert monitor.get_circuit_state("prometheus") == CircuitState.CLOSED
        assert monitor.is_any_degraded is False


@pytest.mark.unit
class TestHealthSummary:
    """Verify health summary output."""

    @pytest.mark.asyncio
    async def test_summary_contains_all_components(self, monitor: ProviderHealthMonitor) -> None:
        """Summary includes all registered components."""
        summary = monitor.get_health_summary()
        assert "prometheus" in summary["components"]
        assert "jaeger" in summary["components"]

    @pytest.mark.asyncio
    async def test_summary_reflects_degraded_state(self, monitor: ProviderHealthMonitor) -> None:
        """Summary correctly reports degraded status."""
        for _ in range(3):
            await monitor.record_failure("prometheus")
        summary = monitor.get_health_summary()
        assert summary["is_degraded"] is True
        assert "prometheus" in summary["degraded_components"]
        assert summary["components"]["prometheus"]["state"] == "open"
