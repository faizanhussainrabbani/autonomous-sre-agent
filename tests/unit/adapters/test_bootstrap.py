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
