"""
Tests for bootstrap.py — provider and cloud operator bootstrapping.

Covers: adapters/bootstrap.py — raising coverage from 0% to ~85%.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sre_agent.config.plugin import ProviderPlugin
from sre_agent.config.settings import AgentConfig
from sre_agent.domain.models.canonical import ComputeMechanism


# ---------------------------------------------------------------------------
# Tests: register_builtin_providers
# ---------------------------------------------------------------------------

def test_register_builtin_providers():
    """Verify OTel and NewRelic factories are registered."""
    from sre_agent.adapters.bootstrap import register_builtin_providers

    register_builtin_providers()

    available = ProviderPlugin.available_providers()
    assert "otel" in available
    assert "newrelic" in available


# ---------------------------------------------------------------------------
# Tests: bootstrap_cloud_operators
# ---------------------------------------------------------------------------

def test_bootstrap_cloud_operators_returns_registry():
    """bootstrap_cloud_operators returns a CloudOperatorRegistry."""
    from sre_agent.adapters.bootstrap import bootstrap_cloud_operators

    mock_config = MagicMock()
    mock_config.aws_region = "us-west-2"

    registry = bootstrap_cloud_operators(mock_config)
    assert registry is not None


def test_bootstrap_cloud_operators_without_sdks():
    """When no cloud SDKs installed, returns empty registry (no crash)."""
    from sre_agent.adapters.bootstrap import bootstrap_cloud_operators

    mock_config = MagicMock()

    with patch.dict(
        "sys.modules",
        {"boto3": None, "azure.mgmt.web": None, "azure.identity": None, "kubernetes": None},
    ):
        registry = bootstrap_cloud_operators(mock_config)
        assert registry is not None
        # Registry should have no registered operators
        assert len(registry._operators) == 0


def test_bootstrap_cloud_operators_registers_kubernetes_when_sdk_present():
    """Kubernetes operator is registered when kubernetes module is importable."""
    from sre_agent.adapters.bootstrap import bootstrap_cloud_operators

    mock_config = MagicMock()

    with patch.dict(
        "sys.modules",
        {
            "kubernetes": MagicMock(),
            "boto3": None,
            "azure.mgmt.web": None,
            "azure.identity": None,
        },
    ):
        registry = bootstrap_cloud_operators(mock_config)

    assert registry.get_operator("kubernetes", ComputeMechanism.KUBERNETES) is not None


def test_bootstrap_lock_manager_redis_selected(monkeypatch):
    from sre_agent.adapters.bootstrap import bootstrap_lock_manager
    from sre_agent.config.settings import LockBackendType

    class _FakeRedisLockManager:
        def __init__(self, config=None):
            self.config = config

    class _FakeRedisLockConfig:
        def __init__(self, url: str = "", key_prefix: str = ""):
            self.url = url
            self.key_prefix = key_prefix

    module = MagicMock(
        RedisDistributedLockManager=_FakeRedisLockManager,
        RedisLockConfig=_FakeRedisLockConfig,
    )
    monkeypatch.setitem(__import__("sys").modules, "sre_agent.adapters.coordination.redis_lock_manager", module)

    config = AgentConfig.from_dict({"lock": {"backend": LockBackendType.REDIS.value}})
    lock_manager = bootstrap_lock_manager(config)

    assert lock_manager.__class__.__name__ == "_FakeRedisLockManager"


def test_bootstrap_lock_manager_falls_back_to_in_memory(monkeypatch):
    from sre_agent.adapters.bootstrap import bootstrap_lock_manager
    from sre_agent.adapters.coordination.in_memory_lock_manager import InMemoryDistributedLockManager
    from sre_agent.config.settings import LockBackendType

    monkeypatch.setitem(
        __import__("sys").modules,
        "sre_agent.adapters.coordination.redis_lock_manager",
        None,
    )

    config = AgentConfig.from_dict({"lock": {"backend": LockBackendType.REDIS.value}})
    lock_manager = bootstrap_lock_manager(config)

    assert isinstance(lock_manager, InMemoryDistributedLockManager)


# ---------------------------------------------------------------------------
# Tests: bootstrap_provider
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bootstrap_provider():
    """Full bootstrap: registers providers and activates configured one."""
    from sre_agent.adapters.bootstrap import bootstrap_provider
    from sre_agent.domain.detection.provider_registry import ProviderRegistry

    mock_config = MagicMock()
    mock_config.telemetry_provider.value = "otel"
    mock_config.otel = MagicMock()
    mock_config.otel.loki_url = "http://localhost:3100"

    registry = ProviderRegistry()

    # Create a mock provider with correct async interfaces
    mock_provider = MagicMock()
    mock_provider.name = "otel"
    mock_provider.is_healthy = True
    mock_provider.health_check = AsyncMock(return_value=True)
    mock_provider.close = AsyncMock()

    with patch(
        "sre_agent.adapters.telemetry.otel.provider.OTelProvider",
        return_value=mock_provider,
    ):
        provider = await bootstrap_provider(mock_config, registry)

    assert provider is not None
    assert provider.name == "otel"


def test_build_otel_log_adapter_with_kubernetes_fallback():
    """_build_otel_log_adapter composes fallback chain when available."""
    from sre_agent.adapters.bootstrap import _build_otel_log_adapter

    config = AgentConfig()
    config.otel.loki_url = "http://localhost:3100"

    mock_primary = MagicMock()
    mock_fallback = MagicMock()
    mock_chain = MagicMock()

    with (
        patch(
            "sre_agent.adapters.telemetry.otel.loki_adapter.LokiLogAdapter",
            return_value=mock_primary,
        ),
        patch(
            "sre_agent.adapters.bootstrap._maybe_build_kubernetes_log_adapter",
            return_value=mock_fallback,
        ),
        patch(
            "sre_agent.adapters.telemetry.fallback_log_adapter.FallbackLogAdapter",
            return_value=mock_chain,
        ) as mock_fallback_adapter,
    ):
        adapter = _build_otel_log_adapter(config)

    assert adapter is mock_chain
    mock_fallback_adapter.assert_called_once_with(
        primary=mock_primary,
        fallback=mock_fallback,
        primary_name="loki",
        fallback_name="kubernetes_api",
    )


def test_build_otel_log_adapter_without_kubernetes_fallback():
    """_build_otel_log_adapter returns Loki adapter when fallback is unavailable."""
    from sre_agent.adapters.bootstrap import _build_otel_log_adapter

    config = AgentConfig()
    config.otel.loki_url = "http://localhost:3100"

    mock_primary = MagicMock()

    with (
        patch(
            "sre_agent.adapters.telemetry.otel.loki_adapter.LokiLogAdapter",
            return_value=mock_primary,
        ),
        patch(
            "sre_agent.adapters.bootstrap._maybe_build_kubernetes_log_adapter",
            return_value=None,
        ),
    ):
        adapter = _build_otel_log_adapter(config)

    assert adapter is mock_primary


@pytest.mark.asyncio
async def test_bootstrap_provider_logs_and_raises_on_create_failure():
    """bootstrap_provider re-raises provider creation failures for callers."""
    from sre_agent.adapters.bootstrap import bootstrap_provider
    from sre_agent.domain.detection.provider_registry import ProviderRegistry

    config = AgentConfig.from_dict({"telemetry_provider": "otel"})
    registry = ProviderRegistry()

    with patch(
        "sre_agent.config.plugin.ProviderPlugin.create_provider",
        side_effect=RuntimeError("factory exploded"),
    ):
        with pytest.raises(RuntimeError, match="factory exploded"):
            await bootstrap_provider(config, registry)


def test_otel_factory_injects_built_log_adapter():
    """_otel_factory should inject composed logs adapter into OTelProvider."""
    from sre_agent.adapters.bootstrap import _otel_factory

    config = AgentConfig()
    mock_logs = MagicMock()
    mock_provider = MagicMock()

    with (
        patch(
            "sre_agent.adapters.bootstrap._build_otel_log_adapter",
            return_value=mock_logs,
        ),
        patch(
            "sre_agent.adapters.telemetry.otel.provider.OTelProvider",
            return_value=mock_provider,
        ) as mock_otel_provider,
    ):
        provider = _otel_factory(config)

    assert provider is mock_provider
    mock_otel_provider.assert_called_once_with(config.otel, logs_adapter=mock_logs)


# ---------------------------------------------------------------------------
# Tests: CloudWatch provider registration — AC-LF-1.2, AC-LF-1.3
# ---------------------------------------------------------------------------

def test_register_builtin_providers_includes_cloudwatch():
    """CloudWatch factory must be registered alongside OTel and NewRelic."""
    from sre_agent.adapters.bootstrap import register_builtin_providers

    ProviderPlugin.clear()
    register_builtin_providers()

    available = ProviderPlugin.available_providers()
    assert "cloudwatch" in available
    assert "otel" in available
    assert "newrelic" in available


def test_cloudwatch_factory_creates_provider():
    """_cloudwatch_factory() must return a CloudWatchProvider instance."""
    from sre_agent.adapters.bootstrap import _cloudwatch_factory
    from sre_agent.adapters.telemetry.cloudwatch.provider import CloudWatchProvider

    config = AgentConfig()

    with patch("boto3.client", return_value=MagicMock()) as mock_boto3:
        provider = _cloudwatch_factory(config)

    assert isinstance(provider, CloudWatchProvider)
    assert provider.name == "cloudwatch"
    # boto3.client should have been called 3 times (cloudwatch, logs, xray)
    assert mock_boto3.call_count == 3


def test_cloudwatch_factory_uses_endpoint_url():
    """_cloudwatch_factory() passes endpoint_url when configured."""
    from sre_agent.adapters.bootstrap import _cloudwatch_factory
    from sre_agent.config.settings import CloudWatchConfig

    config = AgentConfig()
    config.cloudwatch = CloudWatchConfig(endpoint_url="http://localhost:4566")

    with patch("boto3.client", return_value=MagicMock()) as mock_boto3:
        _cloudwatch_factory(config)

    # All 3 boto3 calls should include endpoint_url
    for call in mock_boto3.call_args_list:
        assert call.kwargs.get("endpoint_url") == "http://localhost:4566"

