"""
Unit tests for OpenAILLMAdapter.

Tests timeout enforcement via asyncio.wait_for and system_context
prompt inclusion — LLM Integration Hardening.
"""

from __future__ import annotations

import asyncio
import builtins
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from sre_agent.adapters.llm.openai.adapter import OpenAILLMAdapter
from sre_agent.ports.llm import (
    EvidenceContext,
    Hypothesis,
    HypothesisRequest,
    LLMConfig,
    ValidationRequest,
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


def _mock_chat_response(
    content: str,
    prompt_tokens: int = 100,
    completion_tokens: int = 40,
):
    usage = SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(usage=usage, choices=[choice])


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


class TestOpenAILLMAdapterAdditionalCoverage:
    """Additional branch and success-path coverage for OpenAI adapter."""

    def test_ensure_client_raises_clear_error_when_openai_missing(self, monkeypatch):
        adapter = OpenAILLMAdapter()
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "openai":
                raise ImportError("openai missing")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        with pytest.raises(ImportError, match="sre-agent\\[intelligence\\]"):
            adapter._ensure_client()

    def test_count_tokens_raises_clear_error_when_tiktoken_missing(self, monkeypatch):
        adapter = OpenAILLMAdapter()
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "tiktoken":
                raise ImportError("tiktoken missing")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        with pytest.raises(ImportError, match="sre-agent\\[intelligence\\]"):
            adapter.count_tokens("hello world")

    def test_count_tokens_falls_back_to_cl100k_for_unknown_model(self, monkeypatch):
        class FakeTokenizer:
            def encode(self, text: str):
                return text.split()

        module = types.ModuleType("tiktoken")

        def encoding_for_model(_model_name: str):
            raise KeyError("unknown model")

        module.encoding_for_model = encoding_for_model
        module.get_encoding = lambda _name: FakeTokenizer()
        monkeypatch.setitem(sys.modules, "tiktoken", module)

        adapter = OpenAILLMAdapter(config=LLMConfig(model_name="custom-model"))
        assert adapter.count_tokens("alpha beta gamma") == 3

    async def test_generate_hypothesis_success_parses_and_tracks_usage(self):
        adapter = OpenAILLMAdapter(config=LLMConfig(timeout_seconds=1.0))

        async def create(**_kwargs):
            return _mock_chat_response(
                """```json
                {"root_cause":"memory leak","confidence":0.88,
                 "reasoning":["RSS increased","OOM events observed"],
                 "evidence_citations":["runbook/oom.md"],
                 "suggested_remediation":"restart pod"}
                ```""",
                prompt_tokens=11,
                completion_tokens=7,
            )

        adapter._client = MagicMock()
        adapter._client.chat.completions.create = create

        result = await adapter.generate_hypothesis(_make_request())

        assert result.root_cause == "memory leak"
        assert result.confidence == 0.88
        assert "1. RSS increased" in result.reasoning
        assert result.evidence_citations == ["runbook/oom.md"]
        assert result.suggested_remediation == "restart pod"
        usage = adapter.get_token_usage()
        assert usage.prompt_tokens == 11
        assert usage.completion_tokens == 7

    async def test_validate_hypothesis_success_parses_and_tracks_usage(self):
        adapter = OpenAILLMAdapter(config=LLMConfig(timeout_seconds=1.0))

        async def create(**_kwargs):
            return _mock_chat_response(
                '{"agrees": true, "confidence": 0.73, "reasoning": "consistent", '
                '"contradictions": [], "corrected_root_cause": null, '
                '"corrected_remediation": null}',
                prompt_tokens=5,
                completion_tokens=3,
            )

        adapter._client = MagicMock()
        adapter._client.chat.completions.create = create

        request = ValidationRequest(
            hypothesis=Hypothesis(
                root_cause="Memory leak",
                confidence=0.8,
                reasoning="RSS growth",
            ),
            original_evidence=[],
            alert_description="OOM kill",
        )

        result = await adapter.validate_hypothesis(request)

        assert result.agrees is True
        assert result.confidence == 0.73
        assert result.reasoning == "consistent"
        usage = adapter.get_token_usage()
        assert usage.prompt_tokens == 5
        assert usage.completion_tokens == 3

    async def test_health_check_returns_true_when_models_list_succeeds(self):
        adapter = OpenAILLMAdapter()
        adapter._client = MagicMock()
        adapter._client.models.list = AsyncMock(return_value=[])

        assert await adapter.health_check() is True

    async def test_health_check_returns_false_on_exception(self):
        adapter = OpenAILLMAdapter()
        adapter._client = MagicMock()
        adapter._client.models.list = AsyncMock(side_effect=RuntimeError("down"))

        assert await adapter.health_check() is False

    def test_parse_hypothesis_returns_fallback_on_invalid_json(self):
        parsed = OpenAILLMAdapter._parse_hypothesis("not-json")

        assert parsed.root_cause == "Failed to parse LLM response."
        assert parsed.confidence == 0.0

    def test_parse_validation_returns_fallback_on_invalid_json(self):
        parsed = OpenAILLMAdapter._parse_validation("not-json")

        assert parsed.agrees is False
        assert parsed.confidence == 0.0
