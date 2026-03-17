"""
Unit tests for OpenAILLMAdapter.

Tests timeout enforcement via asyncio.wait_for and system_context
prompt inclusion — LLM Integration Hardening.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sre_agent.adapters.llm.openai.adapter import OpenAILLMAdapter
from sre_agent.ports.llm import (
    EvidenceContext,
    HypothesisRequest,
    LLMConfig,
    ValidationRequest,
    Hypothesis,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(timeout: float = 0.1) -> LLMConfig:
    """Create an LLMConfig with a very short timeout for testing."""
    return LLMConfig(timeout_seconds=timeout)


def _make_request(system_context: str = "") -> HypothesisRequest:
    return HypothesisRequest(
        alert_description="OOM kill on checkout-service",
        service_name="checkout-service",
        timeline="14:00 RSS spike, 14:05 OOM kill",
        evidence=[
            EvidenceContext(
                content="Runbook: restart pod after OOM.",
                source="runbook/oom.md",
                relevance_score=0.9,
            ),
        ],
        system_context=system_context,
    )


# ---------------------------------------------------------------------------
# Timeout tests
# ---------------------------------------------------------------------------


class TestOpenAILLMAdapterTimeout:
    """Timeout enforcement on OpenAI adapter API calls."""

    async def test_generate_hypothesis_times_out(self):
        """generate_hypothesis raises TimeoutError when the API call exceeds timeout."""
        config = _make_config(timeout=0.05)
        adapter = OpenAILLMAdapter(config=config)

        # Mock client with a slow coroutine
        async def slow_create(**kwargs):
            await asyncio.sleep(10)  # Far exceeds timeout

        mock_client = MagicMock()
        mock_client.chat.completions.create = slow_create
        adapter._client = mock_client

        with pytest.raises(TimeoutError, match="timed out"):
            await adapter.generate_hypothesis(_make_request())

    async def test_validate_hypothesis_times_out(self):
        """validate_hypothesis raises TimeoutError when the API call exceeds timeout."""
        config = _make_config(timeout=0.05)
        adapter = OpenAILLMAdapter(config=config)

        async def slow_create(**kwargs):
            await asyncio.sleep(10)

        mock_client = MagicMock()
        mock_client.chat.completions.create = slow_create
        adapter._client = mock_client

        request = ValidationRequest(
            hypothesis=Hypothesis(
                root_cause="Memory leak",
                confidence=0.8,
                reasoning="RSS growth",
            ),
            original_evidence=[],
            alert_description="OOM kill",
        )

        with pytest.raises(TimeoutError, match="timed out"):
            await adapter.validate_hypothesis(request)


# ---------------------------------------------------------------------------
# System context prompt tests
# ---------------------------------------------------------------------------


class TestBuildHypothesisPromptSystemContext:
    """Tests for system_context inclusion in hypothesis prompts."""

    def test_build_hypothesis_prompt_includes_system_context_when_present(self):
        """_build_hypothesis_prompt includes ## System Context section when provided."""
        request = _make_request(system_context="This is a critical payment path.")
        prompt = OpenAILLMAdapter._build_hypothesis_prompt(request)

        assert "## System Context" in prompt
        assert "This is a critical payment path." in prompt

        # Verify ordering: System Context after Service, before Timeline
        service_pos = prompt.index("## Service")
        context_pos = prompt.index("## System Context")
        timeline_pos = prompt.index("## Timeline")
        assert service_pos < context_pos < timeline_pos

    def test_build_hypothesis_prompt_omits_system_context_when_empty(self):
        """_build_hypothesis_prompt omits ## System Context when context is empty."""
        request = _make_request(system_context="")
        prompt = OpenAILLMAdapter._build_hypothesis_prompt(request)

        assert "## System Context" not in prompt
        # Other sections should still be present
        assert "## Alert" in prompt
        assert "## Service" in prompt
        assert "## Timeline" in prompt

    def test_build_hypothesis_prompt_omits_system_context_when_default(self):
        """_build_hypothesis_prompt omits ## System Context with default (empty) value."""
        request = HypothesisRequest(
            alert_description="test",
            service_name="svc",
            timeline="now",
        )
        prompt = OpenAILLMAdapter._build_hypothesis_prompt(request)

        assert "## System Context" not in prompt
