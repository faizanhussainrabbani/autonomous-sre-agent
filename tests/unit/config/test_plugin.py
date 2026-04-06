"""Unit tests for provider plugin registry behavior."""

from __future__ import annotations

import pytest

from sre_agent.config.plugin import ProviderPlugin
from sre_agent.config.settings import AgentConfig


def test_provider_plugin_register_and_create() -> None:
    ProviderPlugin.clear()
    config = AgentConfig()
    sentinel = object()

    ProviderPlugin.register("dummy", lambda _cfg: sentinel)

    assert ProviderPlugin.get_factory("dummy") is not None
    assert "dummy" in ProviderPlugin.available_providers()
    assert ProviderPlugin.create_provider("dummy", config) is sentinel


def test_provider_plugin_overwrite_replaces_factory() -> None:
    ProviderPlugin.clear()
    config = AgentConfig()
    first = object()
    second = object()

    ProviderPlugin.register("dummy", lambda _cfg: first)
    ProviderPlugin.register("dummy", lambda _cfg: second)

    assert ProviderPlugin.create_provider("dummy", config) is second


def test_provider_plugin_create_provider_raises_for_unknown_name() -> None:
    ProviderPlugin.clear()

    with pytest.raises(ValueError, match="not registered"):
        ProviderPlugin.create_provider("missing", AgentConfig())
