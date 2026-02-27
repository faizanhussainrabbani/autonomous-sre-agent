"""
Plugin Interface — extensible provider registration system.

Pure registry for telemetry provider factories. Does NOT import any
adapter modules — factories are registered externally by the application
bootstrap layer (§1.1 — hexagonal architecture).

Implements: Task 13.8 — Extensible plugin interface
Validates: AC-1.5.5
"""

from __future__ import annotations

from typing import Any, Callable

import structlog

from sre_agent.config.settings import AgentConfig
from sre_agent.ports.telemetry import TelemetryProvider

logger = structlog.get_logger(__name__)


# Type for provider factory functions
ProviderFactory = Callable[[AgentConfig], TelemetryProvider]


class ProviderPlugin:
    """Plugin registry for telemetry provider factories.

    Providers register themselves as factory functions that take an AgentConfig
    and produce a TelemetryProvider. This allows new providers to be added
    without modifying core agent code.

    NOTE: This class does NOT import adapter code. Factory registrations
    happen at the application bootstrap layer (see adapters/bootstrap.py).
    """

    _factories: dict[str, ProviderFactory] = {}

    @classmethod
    def register(cls, name: str, factory: ProviderFactory) -> None:
        """Register a provider factory.

        Args:
            name: Provider name (e.g., "otel", "newrelic", "datadog").
            factory: Callable that accepts AgentConfig and returns TelemetryProvider.
        """
        if name in cls._factories:
            logger.warning("provider_factory_overwritten", provider=name)
        cls._factories[name] = factory
        logger.info("provider_factory_registered", provider=name)

    @classmethod
    def get_factory(cls, name: str) -> ProviderFactory | None:
        """Get a registered provider factory by name."""
        return cls._factories.get(name)

    @classmethod
    def available_providers(cls) -> list[str]:
        """List all registered provider names."""
        return list(cls._factories.keys())

    @classmethod
    def clear(cls) -> None:
        """Clear all registered factories (for testing)."""
        cls._factories.clear()

    @classmethod
    def create_provider(cls, name: str, config: AgentConfig) -> TelemetryProvider:
        """Create a provider instance from the registry.

        Args:
            name: Provider name.
            config: Agent configuration.

        Returns:
            Instantiated TelemetryProvider.

        Raises:
            ValueError: If provider name is not registered.
        """
        factory = cls._factories.get(name)
        if factory is None:
            available = ", ".join(cls._factories.keys()) or "(none)"
            raise ValueError(
                f"Provider '{name}' not registered. Available: {available}"
            )
        return factory(config)
