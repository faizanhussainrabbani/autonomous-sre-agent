"""
Application Bootstrap — wire adapters to domain via plugin registry.

This is the ONLY place where adapter implementations are imported and
connected to the domain layer. It lives in the adapters layer, not
in domain or config, per hexagonal architecture (§1.1).

This module is called at application startup (e.g., from main.py).
"""

from __future__ import annotations

import structlog

from sre_agent.config.plugin import ProviderPlugin, ProviderFactory
from sre_agent.config.settings import AgentConfig
from sre_agent.domain.detection.provider_registry import ProviderRegistry
from sre_agent.ports.telemetry import TelemetryProvider

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Built-in provider factories (adapter layer — OK to import adapters here)
# ---------------------------------------------------------------------------

def _otel_factory(config: AgentConfig) -> TelemetryProvider:
    """Factory for the OTel provider (Prometheus + Jaeger + Loki)."""
    from sre_agent.adapters.telemetry.otel.provider import OTelProvider
    return OTelProvider(config.otel)


def _newrelic_factory(config: AgentConfig) -> TelemetryProvider:
    """Factory for the New Relic provider.

    Note: API key must be resolved from secrets manager before calling this.
    For now, uses a placeholder — real secrets integration in cloud-portability.
    """
    from sre_agent.adapters.telemetry.newrelic.provider import NewRelicProvider
    # In production, api_key comes from secrets manager (AWS SM, Azure KV, Vault)
    api_key = ""  # Placeholder — resolved at runtime
    return NewRelicProvider(config.newrelic, api_key=api_key)


def _create_pixie_adapter(config: AgentConfig):
    """Factory for the Pixie eBPF adapter (optional — kernel telemetry).

    Returns an eBPFQuery implementation. This is separate from the
    TelemetryProvider since eBPF is supplementary to the primary
    metrics/traces/logs provider.
    """
    from sre_agent.adapters.telemetry.ebpf.pixie_adapter import PixieAdapter
    return PixieAdapter(
        api_url=getattr(config, "pixie_api_url", "https://work.withpixie.ai"),
        cluster_id=getattr(config, "pixie_cluster_id", ""),
        api_key=getattr(config, "pixie_api_key", ""),
    )


def register_builtin_providers() -> None:
    """Register the built-in OTel and New Relic provider factories."""
    ProviderPlugin.register("otel", _otel_factory)
    ProviderPlugin.register("newrelic", _newrelic_factory)


async def bootstrap_provider(
    config: AgentConfig,
    registry: ProviderRegistry,
) -> TelemetryProvider:
    """Bootstrap the telemetry provider from configuration.

    1. Register built-in providers
    2. Create the configured provider via plugin system
    3. Register and activate it in the provider registry

    Returns:
        The activated TelemetryProvider instance.
    """
    register_builtin_providers()

    provider_name = config.telemetry_provider.value
    logger.info("bootstrapping_provider", provider=provider_name)

    provider = ProviderPlugin.create_provider(provider_name, config)
    registry.register(provider)
    await registry.activate(provider_name)

    logger.info(
        "provider_bootstrapped",
        provider=provider_name,
        available=ProviderPlugin.available_providers(),
    )
    return provider
