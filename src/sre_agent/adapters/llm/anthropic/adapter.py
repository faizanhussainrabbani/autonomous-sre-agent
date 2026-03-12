"""
Anthropic LLM Adapter — Claude-based diagnostic reasoning.

Implements LLMReasoningPort using the Anthropic API for hypothesis generation
and cross-validation. Shares prompt templates with the OpenAI adapter.

Phase 2: Intelligence Layer — Sprint 2 (Reasoning & Inference)
"""

from __future__ import annotations

import json
import time

import structlog

from sre_agent.adapters.llm.prompts import (
    HYPOTHESIS_SYSTEM_PROMPT,
    VALIDATION_SYSTEM_PROMPT,
)
from sre_agent.adapters.llm.openai.adapter import OpenAILLMAdapter
from sre_agent.adapters.telemetry.metrics import (
    LLM_CALL_DURATION,
    LLM_PARSE_FAILURES,
    LLM_TOKENS_USED,
)
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

        _t0 = time.monotonic()
        response = await self._client.messages.create(
            model=self._config.model_name,
            system=HYPOTHESIS_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=self._config.temperature,
            max_tokens=self._config.max_tokens,
        )
        LLM_CALL_DURATION.labels(provider="anthropic", call_type="hypothesis").observe(
            time.monotonic() - _t0
        )

        if response.usage:
            self._usage.add(
                response.usage.input_tokens,
                response.usage.output_tokens,
            )
            LLM_TOKENS_USED.labels(provider="anthropic", token_type="prompt").inc(
                response.usage.input_tokens
            )
            LLM_TOKENS_USED.labels(provider="anthropic", token_type="completion").inc(
                response.usage.output_tokens
            )

        logger.info(
            "llm_api_called",
            provider="anthropic",
            model=self._config.model_name,
            call_type="hypothesis",
            input_tokens=response.usage.input_tokens if response.usage else None,
            output_tokens=response.usage.output_tokens if response.usage else None,
            duration_ms=round((time.monotonic() - _t0) * 1000),
        )

        content = response.content[0].text if response.content else "{}"
        try:
            return OpenAILLMAdapter._parse_hypothesis(content)
        except Exception:
            LLM_PARSE_FAILURES.labels(provider="anthropic").inc()
            raise

    async def validate_hypothesis(
        self,
        request: ValidationRequest,
    ) -> ValidationResult:
        """Cross-validate a hypothesis using Claude."""
        self._ensure_client()

        user_prompt = OpenAILLMAdapter._build_validation_prompt(request)

        _t0 = time.monotonic()
        response = await self._client.messages.create(
            model=self._config.model_name,
            system=VALIDATION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=self._config.temperature,
            max_tokens=self._config.max_tokens,
        )
        LLM_CALL_DURATION.labels(provider="anthropic", call_type="validation").observe(
            time.monotonic() - _t0
        )

        if response.usage:
            self._usage.add(
                response.usage.input_tokens,
                response.usage.output_tokens,
            )
            LLM_TOKENS_USED.labels(provider="anthropic", token_type="prompt").inc(
                response.usage.input_tokens
            )
            LLM_TOKENS_USED.labels(provider="anthropic", token_type="completion").inc(
                response.usage.output_tokens
            )

        logger.info(
            "llm_api_called",
            provider="anthropic",
            model=self._config.model_name,
            call_type="validation",
            input_tokens=response.usage.input_tokens if response.usage else None,
            output_tokens=response.usage.output_tokens if response.usage else None,
            duration_ms=round((time.monotonic() - _t0) * 1000),
        )

        content = response.content[0].text if response.content else "{}"
        try:
            return OpenAILLMAdapter._parse_validation(content)
        except Exception:
            LLM_PARSE_FAILURES.labels(provider="anthropic").inc()
            raise

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
