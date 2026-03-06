"""
Anthropic LLM Adapter — Claude-based diagnostic reasoning.

Implements LLMReasoningPort using the Anthropic API for hypothesis generation
and cross-validation. Shares prompt templates with the OpenAI adapter.

Phase 2: Intelligence Layer — Sprint 2 (Reasoning & Inference)
"""

from __future__ import annotations

import json

import structlog

from sre_agent.adapters.llm.prompts import (
    HYPOTHESIS_SYSTEM_PROMPT,
    VALIDATION_SYSTEM_PROMPT,
)
from sre_agent.adapters.llm.openai.adapter import OpenAILLMAdapter
from sre_agent.ports.llm import (
    Hypothesis,
    HypothesisRequest,
    LLMConfig,
    LLMReasoningPort,
    TokenUsage,
    ValidationRequest,
    ValidationResult,
)

logger = structlog.get_logger(__name__)


class AnthropicLLMAdapter(LLMReasoningPort):
    """LLMReasoningPort adapter using the Anthropic Claude API.

    The anthropic package is lazily imported.
    """

    def __init__(self, config: LLMConfig | None = None) -> None:
        self._config = config or LLMConfig(model_name="claude-sonnet-4-20250514")
        self._client = None
        self._usage = TokenUsage()

    def _ensure_client(self):
        """Lazily initialize the Anthropic client."""
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:
                msg = (
                    "anthropic is required for AnthropicLLMAdapter. "
                    "Install with: pip install 'sre-agent[intelligence]'"
                )
                raise ImportError(msg) from exc
            self._client = anthropic.AsyncAnthropic()

    async def generate_hypothesis(
        self,
        request: HypothesisRequest,
    ) -> Hypothesis:
        """Generate a root-cause hypothesis using Claude."""
        self._ensure_client()

        user_prompt = OpenAILLMAdapter._build_hypothesis_prompt(request)

        response = await self._client.messages.create(
            model=self._config.model_name,
            system=HYPOTHESIS_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=self._config.temperature,
            max_tokens=self._config.max_tokens,
        )

        if response.usage:
            self._usage.add(
                response.usage.input_tokens,
                response.usage.output_tokens,
            )

        content = response.content[0].text if response.content else "{}"
        return OpenAILLMAdapter._parse_hypothesis(content)

    async def validate_hypothesis(
        self,
        request: ValidationRequest,
    ) -> ValidationResult:
        """Cross-validate a hypothesis using Claude."""
        self._ensure_client()

        user_prompt = OpenAILLMAdapter._build_validation_prompt(request)

        response = await self._client.messages.create(
            model=self._config.model_name,
            system=VALIDATION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=self._config.temperature,
            max_tokens=self._config.max_tokens,
        )

        if response.usage:
            self._usage.add(
                response.usage.input_tokens,
                response.usage.output_tokens,
            )

        content = response.content[0].text if response.content else "{}"
        return OpenAILLMAdapter._parse_validation(content)

    def count_tokens(self, text: str) -> int:
        """Approximate token count (Claude uses ~4 chars per token)."""
        return len(text) // 4

    def get_token_usage(self) -> TokenUsage:
        """Return cumulative token usage."""
        return self._usage

    async def health_check(self) -> bool:
        """Verify Anthropic API connectivity."""
        try:
            self._ensure_client()
            # Minimal API call to verify connectivity
            await self._client.messages.create(
                model=self._config.model_name,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
            )
            return True
        except Exception:  # noqa: BLE001
            return False
