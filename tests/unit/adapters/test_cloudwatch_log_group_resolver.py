"""Unit tests for shared CloudWatch log-group resolver."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from sre_agent.adapters.telemetry.cloudwatch.log_group_resolver import (
    CloudWatchLogGroupResolver,
)


@pytest.mark.asyncio
async def test_resolve_service_uses_override_before_discovery():
    """Explicit overrides take priority over DescribeLogGroups discovery."""
    client = MagicMock()
    resolver = CloudWatchLogGroupResolver(
        logs_client=client,
        overrides={"orders": "/custom/orders"},
    )

    result = await resolver.resolve("orders")

    assert result == "/custom/orders"
    client.describe_log_groups.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_service_uses_pattern_discovery_order():
    """Resolver tries patterns in order and returns first discovered group."""
    client = MagicMock()
    attempted_prefixes: list[str] = []

    def _describe(*, logGroupNamePrefix: str, limit: int):
        attempted_prefixes.append(logGroupNamePrefix)
        if logGroupNamePrefix == "/ecs/orders":
            return {"logGroups": [{"logGroupName": "/ecs/orders"}]}
        return {"logGroups": []}

    client.describe_log_groups.side_effect = _describe

    resolver = CloudWatchLogGroupResolver(
        logs_client=client,
        patterns=["/aws/lambda/{service}", "/ecs/{service}", "/aws/ecs/{service}"],
    )

    result = await resolver.resolve("orders")

    assert result == "/ecs/orders"
    assert attempted_prefixes == ["/aws/lambda/orders", "/ecs/orders"]


@pytest.mark.asyncio
async def test_resolve_service_falls_back_to_lambda_convention():
    """Unknown services resolve to the deterministic Lambda fallback group."""
    client = MagicMock()
    client.describe_log_groups.return_value = {"logGroups": []}
    resolver = CloudWatchLogGroupResolver(logs_client=client)

    result = await resolver.resolve("unknown-service")

    assert result == "/aws/lambda/unknown-service"


@pytest.mark.asyncio
async def test_resolve_service_uses_cache_for_repeat_lookups():
    """Second resolution for same service must use cache and skip API calls."""
    client = MagicMock()
    client.describe_log_groups.return_value = {
        "logGroups": [{"logGroupName": "/aws/lambda/payment-handler"}],
    }

    resolver = CloudWatchLogGroupResolver(logs_client=client)

    first = await resolver.resolve("payment-handler")
    call_count_after_first = client.describe_log_groups.call_count
    second = await resolver.resolve("payment-handler")

    assert first == "/aws/lambda/payment-handler"
    assert second == "/aws/lambda/payment-handler"
    assert client.describe_log_groups.call_count == call_count_after_first
