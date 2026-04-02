"""Integration-style verification for CloudWatch provider bootstrap path."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sre_agent.adapters.bootstrap import bootstrap_provider
from sre_agent.config.settings import AgentConfig
from sre_agent.domain.detection.provider_registry import ProviderRegistry


@pytest.mark.asyncio
@pytest.mark.integration
async def test_bootstrap_provider_cloudwatch_activates_registry():
    """CloudWatch provider can be bootstrapped and activated via registry."""
    config = AgentConfig.from_dict(
        {
            "telemetry_provider": "cloudwatch",
            "cloudwatch": {
                "region": "us-east-1",
                "endpoint_url": "http://localhost:4566",
            },
        }
    )
    registry = ProviderRegistry()

    mock_provider = MagicMock()
    mock_provider.name = "cloudwatch"
    mock_provider.health_check = AsyncMock(return_value=True)
    mock_provider.close = AsyncMock()

    with (
        patch("boto3.client", return_value=MagicMock()),
        patch(
            "sre_agent.adapters.telemetry.cloudwatch.provider.CloudWatchProvider",
            return_value=mock_provider,
        ),
    ):
        provider = await bootstrap_provider(config, registry)

    assert provider is mock_provider
    assert registry.active_provider_name == "cloudwatch"
