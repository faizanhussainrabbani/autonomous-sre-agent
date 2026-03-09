"""
OpenAI LLM Adapter — GPT-based diagnostic reasoning.

Implements LLMReasoningPort using the OpenAI API for hypothesis generation
and cross-validation. Includes token counting via tiktoken.

Phase 2: Intelligence Layer — Sprint 2 (Reasoning & Inference)
"""

from __future__ import annotations

import json
import re
import time

import structlog

from sre_agent.adapters.llm.prompts import (
    HYPOTHESIS_SYSTEM_PROMPT,
    VALIDATION_SYSTEM_PROMPT,
)
from sre_agent.adapters.telemetry.metrics import (
    LLM_CALL_DURATION,
    LLM_PARSE_FAILURES,
    LLM_TOKENS_USED,
)
from sre_agent.ports.llm import (
    EvidenceContext,
    Hypothesis,
    HypothesisRequest,
    LLMConfig,
    LLMReasoningPort,
    TokenUsage,
    ValidationRequest,
    ValidationResult,
)

logger = structlog.get_logger(__name__)


class OpenAILLMAdapter(LLMReasoningPort):
    """LLMReasoningPort adapter using the OpenAI API.

    The openai and tiktoken packages are lazily imported.
    """

    def __init__(self, config: LLMConfig | None = None) -> None:
        self._config = config or LLMConfig()
        self._client = None
        self._tokenizer = None
        self._usage = TokenUsage()

    def _ensure_client(self):
        """Lazily initialize the OpenAI client."""
        if self._client is None:
            try:
                import openai
            except ImportError as exc:
                msg = (
                    "openai is required for OpenAILLMAdapter. "
                    "Install with: pip install 'sre-agent[intelligence]'"
                )
                raise ImportError(msg) from exc
            self._client = openai.AsyncOpenAI()

    def _ensure_tokenizer(self):
        """Lazily load the tiktoken tokenizer."""
        if self._tokenizer is None:
            try:
                import tiktoken
            except ImportError as exc:
                msg = (
                    "tiktoken is required for OpenAILLMAdapter. "
                    "Install with: pip install 'sre-agent[intelligence]'"
                )
                raise ImportError(msg) from exc
            try:
                self._tokenizer = tiktoken.encoding_for_model(self._config.model_name)
            except KeyError:
                self._tokenizer = tiktoken.get_encoding("cl100k_base")

    async def generate_hypothesis(
        self,
        request: HypothesisRequest,
    ) -> Hypothesis:
        """Generate a root-cause hypothesis using GPT."""
        self._ensure_client()

        user_prompt = self._build_hypothesis_prompt(request)

        _t0 = time.monotonic()
        response = await self._client.chat.completions.create(
            model=self._config.model_name,
            messages=[
                {"role": "system", "content": HYPOTHESIS_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self._config.temperature,
            max_tokens=self._config.max_tokens,
            response_format={"type": "json_object"},
        )
        LLM_CALL_DURATION.labels(provider="openai", call_type="hypothesis").observe(
            time.monotonic() - _t0
        )

        # Track token usage
        if response.usage:
            self._usage.add(
                response.usage.prompt_tokens,
                response.usage.completion_tokens,
            )
            LLM_TOKENS_USED.labels(provider="openai", token_type="prompt").inc(
                response.usage.prompt_tokens
            )
            LLM_TOKENS_USED.labels(provider="openai", token_type="completion").inc(
                response.usage.completion_tokens
            )

        content = response.choices[0].message.content or "{}"
        return self._parse_hypothesis(content)

    async def validate_hypothesis(
        self,
        request: ValidationRequest,
    ) -> ValidationResult:
        """Cross-validate a hypothesis using a second GPT call."""
        self._ensure_client()

        user_prompt = self._build_validation_prompt(request)

        _t0 = time.monotonic()
        response = await self._client.chat.completions.create(
            model=self._config.model_name,
            messages=[
                {"role": "system", "content": VALIDATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self._config.temperature,
            max_tokens=self._config.max_tokens,
            response_format={"type": "json_object"},
        )
        LLM_CALL_DURATION.labels(provider="openai", call_type="validation").observe(
            time.monotonic() - _t0
        )

        if response.usage:
            self._usage.add(
                response.usage.prompt_tokens,
                response.usage.completion_tokens,
            )
            LLM_TOKENS_USED.labels(provider="openai", token_type="prompt").inc(
                response.usage.prompt_tokens
            )
            LLM_TOKENS_USED.labels(provider="openai", token_type="completion").inc(
                response.usage.completion_tokens
            )

        content = response.choices[0].message.content or "{}"
        return self._parse_validation(content)

    def count_tokens(self, text: str) -> int:
        """Count tokens using tiktoken."""
        self._ensure_tokenizer()
        return len(self._tokenizer.encode(text))

    def get_token_usage(self) -> TokenUsage:
        """Return cumulative token usage."""
        return self._usage

    async def health_check(self) -> bool:
        """Verify OpenAI API connectivity."""
        try:
            self._ensure_client()
            await self._client.models.list()
            return True
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    def _build_hypothesis_prompt(request: HypothesisRequest) -> str:
        """Build the user prompt for hypothesis generation."""
        parts = [
            f"## Alert\n{request.alert_description}",
            f"\n## Service\n{request.service_name}",
        ]

        if request.timeline:
            parts.append(f"\n## Timeline\n{request.timeline}")

        if request.evidence:
            parts.append("\n## Evidence")
            for i, e in enumerate(request.evidence, 1):
                parts.append(
                    f"\n### Evidence {i} (relevance: {e.relevance_score:.2f}, "
                    f"source: {e.source})\n{e.content}"
                )

        return "\n".join(parts)

    @staticmethod
    def _build_validation_prompt(request: ValidationRequest) -> str:
        """Build the user prompt for hypothesis validation."""
        h = request.hypothesis
        parts = [
            f"## Hypothesis\nRoot cause: {h.root_cause}",
            f"Confidence: {h.confidence}",
            f"Reasoning: {h.reasoning}",
        ]

        if request.alert_description:
            parts.append(f"\n## Original Alert\n{request.alert_description}")

        if request.original_evidence:
            parts.append("\n## Original Evidence")
            for i, e in enumerate(request.original_evidence, 1):
                parts.append(f"\n### Evidence {i}\n{e.content}")

        return "\n".join(parts)

    @staticmethod
    def _strip_code_fences(content: str) -> str:
        """Strip markdown code fences from LLM output.

        Some models (e.g. Claude) wrap JSON responses in ```json ... ``` blocks
        even when instructed to return raw JSON. This helper extracts the inner
        JSON text so that json.loads() can succeed.
        """
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
        return match.group(1).strip() if match else content.strip()

    @staticmethod
    def _normalize_reasoning(reasoning: object) -> str:
        """Normalize reasoning to a plain string.

        The LLM may return reasoning as a list of step strings or a single
        string.  Either form is accepted and converted to a numbered list.
        """
        if isinstance(reasoning, list):
            return "\n".join(f"{i}. {step}" for i, step in enumerate(reasoning, 1))
        return str(reasoning) if reasoning else ""

    @staticmethod
    def _parse_hypothesis(content: str) -> Hypothesis:
        """Parse JSON response into a Hypothesis."""
        cleaned = OpenAILLMAdapter._strip_code_fences(content)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            LLM_PARSE_FAILURES.labels(provider="openai").inc()
            logger.warning("hypothesis_parse_failed", raw_content=content[:200])
            return Hypothesis(
                root_cause="Failed to parse LLM response.",
                confidence=0.0,
                reasoning=content,
            )

        return Hypothesis(
            root_cause=data.get("root_cause", "Unknown"),
            confidence=float(data.get("confidence", 0.0)),
            reasoning=OpenAILLMAdapter._normalize_reasoning(data.get("reasoning", "")),
            evidence_citations=data.get("evidence_citations", []),
            suggested_remediation=data.get("suggested_remediation", ""),
        )

    @staticmethod
    def _parse_validation(content: str) -> ValidationResult:
        """Parse JSON response into a ValidationResult."""
        cleaned = OpenAILLMAdapter._strip_code_fences(content)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            LLM_PARSE_FAILURES.labels(provider="openai").inc()
            logger.warning("validation_parse_failed", raw_content=content[:200])
            return ValidationResult(
                agrees=False,
                confidence=0.0,
                reasoning=content,
            )

        return ValidationResult(
            agrees=bool(data.get("agrees", False)),
            confidence=float(data.get("confidence", 0.0)),
            reasoning=OpenAILLMAdapter._normalize_reasoning(data.get("reasoning", "")),
            contradictions=data.get("contradictions", []),
        )
