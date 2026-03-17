"""
Unit tests for AnthropicLLMAdapter.

Tests timeout enforcement via asyncio.wait_for and parse failure
fallback consistency — LLM Integration Hardening.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sre_agent.adapters.llm.anthropic.adapter import AnthropicLLMAdapter
from sre_agent.adapters.telemetry.metrics import LLM_PARSE_FAILURES
from sre_agent.ports.llm import (
    Hypothesis,
    HypothesisRequest,
    LLMConfig,
    ValidationRequest,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(timeout: float = 0.1) -> LLMConfig:
    return LLMConfig(
        model_name="claude-sonnet-4-20250514",
        timeout_seconds=timeout,
    )


def _make_request() -> HypothesisRequest:
    return HypothesisRequest(
        alert_description="OOM kill on checkout-service",
        service_name="checkout-service",
        timeline="14:00 RSS spike",
        evidence=[],
    )


def _make_validation_request() -> ValidationRequest:
    return ValidationRequest(
        hypothesis=Hypothesis(
            root_cause="Memory leak",
            confidence=0.8,
            reasoning="RSS growth",
        ),
        original_evidence=[],
        alert_description="OOM kill",
    )


def _mock_response(text: str, input_tokens: int = 100, output_tokens: int = 50):
    """Create a mock Anthropic response with given text content."""
    content_block = SimpleNamespace(text=text)
    usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)
    return SimpleNamespace(content=[content_block], usage=usage)


# ---------------------------------------------------------------------------
# Timeout tests
# ---------------------------------------------------------------------------


class TestAnthropicLLMAdapterTimeout:
    """Timeout enforcement on Anthropic adapter API calls."""

    async def test_generate_hypothesis_times_out(self):
        """generate_hypothesis raises TimeoutError when the API call exceeds timeout."""
        config = _make_config(timeout=0.05)
        adapter = AnthropicLLMAdapter(config=config)

        async def slow_create(**kwargs):
            await asyncio.sleep(10)

        mock_client = MagicMock()
        mock_client.messages.create = slow_create
        adapter._client = mock_client

        with pytest.raises(TimeoutError, match="timed out"):
            await adapter.generate_hypothesis(_make_request())

    async def test_validate_hypothesis_times_out(self):
        """validate_hypothesis raises TimeoutError when the API call exceeds timeout."""
        config = _make_config(timeout=0.05)
        adapter = AnthropicLLMAdapter(config=config)

        async def slow_create(**kwargs):
            await asyncio.sleep(10)

        mock_client = MagicMock()
        mock_client.messages.create = slow_create
        adapter._client = mock_client

        with pytest.raises(TimeoutError, match="timed out"):
            await adapter.validate_hypothesis(_make_validation_request())


# ---------------------------------------------------------------------------
# Parse failure fallback tests
# ---------------------------------------------------------------------------


class TestAnthropicParseFailureFallback:
    """Anthropic parse failures return fallback objects instead of crashing."""

    async def test_anthropic_parse_failure_returns_fallback_hypothesis(self):
        """Parse failure in generate_hypothesis returns a fallback Hypothesis."""
        config = _make_config(timeout=5.0)
        adapter = AnthropicLLMAdapter(config=config)

        # Mock a successful API call but with unparseable content
        async def return_garbage(**kwargs):
            return _mock_response("this is not json at all {{{")

        mock_client = MagicMock()
        mock_client.messages.create = return_garbage
        adapter._client = mock_client

        result = await adapter.generate_hypothesis(_make_request())

        # Should return a fallback instead of raising
        assert result.root_cause == "Failed to parse LLM response."
        assert result.confidence == 0.0

    async def test_anthropic_parse_failure_returns_fallback_validation_result(self):
        """Parse failure in validate_hypothesis returns a fallback ValidationResult."""
        config = _make_config(timeout=5.0)
        adapter = AnthropicLLMAdapter(config=config)

        async def return_garbage(**kwargs):
            return _mock_response("not valid json ][")

        mock_client = MagicMock()
        mock_client.messages.create = return_garbage
        adapter._client = mock_client

        result = await adapter.validate_hypothesis(_make_validation_request())

        # Should return a fallback instead of raising
        assert result.agrees is False
        assert result.confidence == 0.0

    async def test_anthropic_parse_failure_increments_metric(self):
        """Parse failure increments LLM_PARSE_FAILURES counter."""
        from prometheus_client import REGISTRY

        config = _make_config(timeout=5.0)
        adapter = AnthropicLLMAdapter(config=config)

        async def return_garbage(**kwargs):
            return _mock_response("{{broken json")

        mock_client = MagicMock()
        mock_client.messages.create = return_garbage
        adapter._client = mock_client

        # Record metric value before
        before = REGISTRY.get_sample_value(
            "sre_agent_llm_parse_failures_total",
            {"provider": "anthropic"},
        ) or 0.0

        await adapter.validate_hypothesis(_make_validation_request())

        after = REGISTRY.get_sample_value(
            "sre_agent_llm_parse_failures_total",
            {"provider": "anthropic"},
        ) or 0.0
        assert after > before, "LLM_PARSE_FAILURES should be incremented on parse failure"
