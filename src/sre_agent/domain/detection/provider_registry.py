"""
Provider Registry — Runtime-configurable telemetry provider management.

Lives in domain/detection/ because it manages provider lifecycle,
emits domain events, and is part of the Detection bounded context (§1.2).

Implements: Task 13.5 — Provider registration system
Validates: AC-1.5.1 through AC-1.5.5
"""

from __future__ import annotations

import structlog
from datetime import datetime
from typing import Any

from sre_agent.domain.models.canonical import DomainEvent, EventTypes
from sre_agent.ports.telemetry import TelemetryProvider
from sre_agent.ports.events import EventBus

logger = structlog.get_logger(__name__)


class ProviderRegistryError(Exception):
    """Raised when provider registration or selection fails."""


class ProviderRegistry:
    """Manages telemetry provider lifecycle and selection.

    Supports runtime-configurable provider selection — switch backends
    via configuration, not code changes (AC-1.5.1).
    """

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self._providers: dict[str, TelemetryProvider] = {}
        self._active_provider_name: str | None = None
        self._is_degraded: bool = False
        self._degradation_reason: str | None = None
        self._event_bus = event_bus

    @property
    def active_provider(self) -> TelemetryProvider:
        """Get the currently active telemetry provider.

        Raises:
            ProviderRegistryError: If no provider is active.
        """
        if self._active_provider_name is None:
            raise ProviderRegistryError("No active telemetry provider configured")
        return self._providers[self._active_provider_name]

    @property
    def active_provider_name(self) -> str | None:
        """Name of the currently active provider."""
        return self._active_provider_name

    @property
    def is_degraded(self) -> bool:
        """Whether the telemetry system is in degraded mode."""
        return self._is_degraded

    @property
    def degradation_reason(self) -> str | None:
        """Reason for degraded mode, if applicable."""
        return self._degradation_reason

    @property
    def registered_providers(self) -> list[str]:
        """List all registered provider names."""
        return list(self._providers.keys())

    def register(self, provider: TelemetryProvider) -> None:
        """Register a telemetry provider adapter.

        Args:
            provider: Provider implementation to register.

        Raises:
            ProviderRegistryError: If a provider with the same name is already registered.

        Validates: AC-1.5.5 (plugin interface — register new providers)
        """
        if provider.name in self._providers:
            raise ProviderRegistryError(
                f"Provider '{provider.name}' is already registered"
            )
        self._providers[provider.name] = provider
        logger.info("provider_registered", provider=provider.name)

    async def activate(self, provider_name: str) -> None:
        """Activate a registered provider, validating connectivity first.

        Args:
            provider_name: Name of the provider to activate.

        Raises:
            ProviderRegistryError: If provider not registered or health check fails.

        Validates: AC-1.5.1 (config-based selection), AC-1.5.2 (startup validation)
        """
        if provider_name not in self._providers:
            available = ", ".join(self._providers.keys()) or "(none)"
            raise ProviderRegistryError(
                f"Provider '{provider_name}' not registered. Available: {available}"
            )

        provider = self._providers[provider_name]

        # Validate connectivity before activating (AC-1.5.2)
        logger.info("provider_health_check", provider=provider_name)
        is_healthy = await provider.health_check()

        if not is_healthy:
            raise ProviderRegistryError(
                f"Provider '{provider_name}' failed health check — "
                f"cannot activate until connectivity is resolved"
            )

        # Deactivate previous provider if different
        if self._active_provider_name and self._active_provider_name != provider_name:
            logger.info(
                "provider_switching",
                from_provider=self._active_provider_name,
                to_provider=provider_name,
            )

        self._active_provider_name = provider_name
        self._is_degraded = False
        self._degradation_reason = None
        logger.info("provider_activated", provider=provider_name)

    async def check_health(self) -> bool:
        """Check health of the active provider.

        If unhealthy, sets degraded mode and emits event (AC-1.5.3, AC-1.5.4).

        Returns:
            True if healthy, False if degraded.
        """
        if self._active_provider_name is None:
            return False

        provider = self._providers[self._active_provider_name]

        try:
            is_healthy = await provider.health_check()
        except Exception as exc:
            is_healthy = False
            logger.error(
                "provider_health_check_failed",
                provider=self._active_provider_name,
                error=str(exc),
            )

        if not is_healthy and not self._is_degraded:
            # Transition to degraded mode (AC-1.5.3, AC-1.5.4)
            self._is_degraded = True
            self._degradation_reason = (
                f"Provider '{self._active_provider_name}' failed health check"
            )
            logger.warning(
                "provider_degraded",
                provider=self._active_provider_name,
                reason=self._degradation_reason,
            )

            # Emit domain event
            if self._event_bus:
                await self._event_bus.publish(
                    DomainEvent(
                        event_type=EventTypes.PROVIDER_HEALTH_CHANGED,
                        payload={
                            "provider": self._active_provider_name,
                            "is_healthy": False,
                            "reason": self._degradation_reason,
                        },
                    )
                )

        elif is_healthy and self._is_degraded:
            # Recovered from degraded mode
            self._is_degraded = False
            self._degradation_reason = None
            logger.info(
                "provider_recovered",
                provider=self._active_provider_name,
            )

            if self._event_bus:
                await self._event_bus.publish(
                    DomainEvent(
                        event_type=EventTypes.PROVIDER_HEALTH_CHANGED,
                        payload={
                            "provider": self._active_provider_name,
                            "is_healthy": True,
                        },
                    )
                )

        return is_healthy

    async def close_all(self) -> None:
        """Close all registered provider connections (graceful shutdown)."""
        for name, provider in self._providers.items():
            try:
                await provider.close()
                logger.info("provider_closed", provider=name)
            except Exception as exc:
                logger.error("provider_close_failed", provider=name, error=str(exc))
