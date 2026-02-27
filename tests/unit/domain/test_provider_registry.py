"""
Tests for the Provider Registry — Task 13.5.

Validates: AC-1.5.1 through AC-1.5.5
"""

from __future__ import annotations

import pytest
from datetime import datetime
from typing import Any

from sre_agent.config.provider_registry import ProviderRegistry, ProviderRegistryError
from sre_agent.domain.models.canonical import EventTypes
from sre_agent.events.in_memory import InMemoryEventBus
from sre_agent.ports.telemetry import (
    DependencyGraphQuery,
    LogQuery,
    MetricsQuery,
    TelemetryProvider,
    TraceQuery,
)
from sre_agent.domain.models.canonical import (
    CanonicalLogEntry,
    CanonicalMetric,
    CanonicalTrace,
    ServiceGraph,
)


# ---------------------------------------------------------------------------
# Stub provider for testing
# ---------------------------------------------------------------------------

class StubMetricsQuery(MetricsQuery):
    async def query(self, service, metric, start_time, end_time, labels=None, step_seconds=15):
        return []
    async def query_instant(self, service, metric, timestamp=None, labels=None):
        return None
    async def list_metrics(self, service):
        return []

class StubTraceQuery(TraceQuery):
    async def get_trace(self, trace_id):
        return None
    async def query_traces(self, service, start_time, end_time, limit=100, min_duration_ms=None, status_code=None):
        return []

class StubLogQuery(LogQuery):
    async def query_logs(self, service, start_time, end_time, severity=None, trace_id=None, search_text=None, limit=1000):
        return []
    async def query_by_trace_id(self, trace_id, start_time=None, end_time=None):
        return []

class StubDepGraphQuery(DependencyGraphQuery):
    async def get_graph(self):
        return ServiceGraph()
    async def get_service_dependencies(self, service, include_transitive=False):
        return ServiceGraph()
    async def get_service_health(self, service):
        return {"is_healthy": True}


class StubProvider(TelemetryProvider):
    """Configurable stub for testing provider registry."""

    def __init__(self, name: str = "stub", healthy: bool = True):
        self._name = name
        self._healthy = healthy
        self._closed = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def metrics(self) -> MetricsQuery:
        return StubMetricsQuery()

    @property
    def traces(self) -> TraceQuery:
        return StubTraceQuery()

    @property
    def logs(self) -> LogQuery:
        return StubLogQuery()

    @property
    def dependency_graph(self) -> DependencyGraphQuery:
        return StubDepGraphQuery()

    async def health_check(self) -> bool:
        return self._healthy

    async def close(self) -> None:
        self._closed = True


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestProviderRegistration:
    """AC-1.5.5: New providers can be registered."""

    def test_register_provider(self):
        registry = ProviderRegistry()
        provider = StubProvider(name="otel")
        registry.register(provider)
        assert "otel" in registry.registered_providers

    def test_register_duplicate_raises(self):
        registry = ProviderRegistry()
        registry.register(StubProvider(name="otel"))
        with pytest.raises(ProviderRegistryError, match="already registered"):
            registry.register(StubProvider(name="otel"))

    def test_register_multiple_providers(self):
        registry = ProviderRegistry()
        registry.register(StubProvider(name="otel"))
        registry.register(StubProvider(name="newrelic"))
        assert set(registry.registered_providers) == {"otel", "newrelic"}


class TestProviderActivation:
    """AC-1.5.1: Config-based selection. AC-1.5.2: Startup validation."""

    @pytest.mark.asyncio
    async def test_activate_healthy_provider(self):
        registry = ProviderRegistry()
        registry.register(StubProvider(name="otel", healthy=True))
        await registry.activate("otel")
        assert registry.active_provider_name == "otel"
        assert not registry.is_degraded

    @pytest.mark.asyncio
    async def test_activate_unhealthy_provider_raises(self):
        registry = ProviderRegistry()
        registry.register(StubProvider(name="otel", healthy=False))
        with pytest.raises(ProviderRegistryError, match="failed health check"):
            await registry.activate("otel")

    @pytest.mark.asyncio
    async def test_activate_unregistered_raises(self):
        registry = ProviderRegistry()
        with pytest.raises(ProviderRegistryError, match="not registered"):
            await registry.activate("unknown")

    @pytest.mark.asyncio
    async def test_switch_provider(self):
        registry = ProviderRegistry()
        registry.register(StubProvider(name="otel"))
        registry.register(StubProvider(name="newrelic"))
        await registry.activate("otel")
        assert registry.active_provider_name == "otel"
        await registry.activate("newrelic")
        assert registry.active_provider_name == "newrelic"

    def test_no_active_provider_raises(self):
        registry = ProviderRegistry()
        with pytest.raises(ProviderRegistryError, match="No active"):
            _ = registry.active_provider


class TestProviderHealthMonitoring:
    """AC-1.5.3: Internal alert on failure. AC-1.5.4: Degraded telemetry mode."""

    @pytest.mark.asyncio
    async def test_healthy_check(self):
        registry = ProviderRegistry()
        registry.register(StubProvider(name="otel", healthy=True))
        await registry.activate("otel")
        result = await registry.check_health()
        assert result is True
        assert not registry.is_degraded

    @pytest.mark.asyncio
    async def test_unhealthy_triggers_degraded_mode(self):
        provider = StubProvider(name="otel", healthy=True)
        event_bus = InMemoryEventBus()
        registry = ProviderRegistry(event_bus=event_bus)
        registry.register(provider)
        await registry.activate("otel")

        # Simulate provider going unhealthy
        provider._healthy = False
        result = await registry.check_health()

        assert result is False
        assert registry.is_degraded
        assert "failed health check" in (registry.degradation_reason or "")

        # Verify domain event emitted (AC-1.5.3)
        assert len(event_bus.published_events) == 1
        event = event_bus.published_events[0]
        assert event.event_type == EventTypes.PROVIDER_HEALTH_CHANGED
        assert event.payload["is_healthy"] is False

    @pytest.mark.asyncio
    async def test_recovery_from_degraded(self):
        provider = StubProvider(name="otel", healthy=True)
        event_bus = InMemoryEventBus()
        registry = ProviderRegistry(event_bus=event_bus)
        registry.register(provider)
        await registry.activate("otel")

        # Go degraded
        provider._healthy = False
        await registry.check_health()
        assert registry.is_degraded

        # Recover
        provider._healthy = True
        result = await registry.check_health()
        assert result is True
        assert not registry.is_degraded

        # Verify recovery event
        assert len(event_bus.published_events) == 2
        assert event_bus.published_events[1].payload["is_healthy"] is True


class TestProviderLifecycle:
    """Graceful shutdown."""

    @pytest.mark.asyncio
    async def test_close_all(self):
        p1 = StubProvider(name="otel")
        p2 = StubProvider(name="newrelic")
        registry = ProviderRegistry()
        registry.register(p1)
        registry.register(p2)

        await registry.close_all()
        assert p1._closed
        assert p2._closed
