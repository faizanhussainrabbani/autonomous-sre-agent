"""
LLM Reasoning Port — Provider-agnostic language model interface.

Defines abstract operations for hypothesis generation, validation,
and token management used by the RAG diagnostic pipeline.

Phase 2: Intelligence Layer — Sprint 2 (Reasoning & Inference)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class LLMProvider(Enum):
    """Supported LLM providers."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"


@dataclass(frozen=True)
class LLMConfig:
    """Configuration for LLM adapter selection and tuning."""

    provider: LLMProvider = LLMProvider.OPENAI
    model_name: str = "gpt-4o-mini"
    max_tokens: int = 4096
    temperature: float = 0.1
    context_budget: int = 4000  # Max tokens for RAG context window
    timeout_seconds: float = 30.0


@dataclass(frozen=True)
class EvidenceContext:
    """A piece of retrieved evidence passed into the LLM prompt."""

    content: str
    source: str
    relevance_score: float


@dataclass
class HypothesisRequest:
    """Request payload for generating a diagnostic hypothesis."""

    alert_description: str
    service_name: str
    timeline: str
    evidence: list[EvidenceContext] = field(default_factory=list)
    system_context: str = ""
    priority: int = 3  # §5.3 priority queue: 1=highest (SEV1), 4=lowest (SEV4)


@dataclass(frozen=True)
class Hypothesis:
    """Structured hypothesis output from the LLM."""

    root_cause: str
    confidence: float
    reasoning: str
    evidence_citations: list[str] = field(default_factory=tuple)  # type: ignore[assignment]
    suggested_remediation: str = ""


@dataclass
class ValidationRequest:
    """Request payload for cross-validating a hypothesis."""

    hypothesis: Hypothesis
    original_evidence: list[EvidenceContext] = field(default_factory=list)
    alert_description: str = ""


@dataclass(frozen=True)
class ValidationResult:
    """Result of hypothesis cross-validation."""

    agrees: bool
    confidence: float
    reasoning: str
    contradictions: list[str] = field(default_factory=tuple)  # type: ignore[assignment]
    corrected_root_cause: str | None = None
    corrected_remediation: str | None = None


@dataclass
class TokenUsage:
    """Cumulative token usage tracking for cost monitoring."""

    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def add(self, prompt: int, completion: int) -> None:
        self.prompt_tokens += prompt
        self.completion_tokens += completion


class LLMReasoningPort(ABC):
    """Abstract interface for LLM-powered diagnostic reasoning.

    Concrete adapters (OpenAI, Anthropic) implement this to provide
    hypothesis generation and cross-validation capabilities.
    """

    @abstractmethod
    async def generate_hypothesis(
        self,
        request: HypothesisRequest,
    ) -> Hypothesis:
        """Generate a root-cause hypothesis from evidence and timeline.

        Args:
            request: Structured request with alert context and evidence.

        Returns:
            A Hypothesis with root cause, confidence, and reasoning.
        """
        ...

    @abstractmethod
    async def validate_hypothesis(
        self,
        request: ValidationRequest,
    ) -> ValidationResult:
        """Cross-validate a hypothesis using a second LLM call.

        Args:
            request: The hypothesis to validate with its original evidence.

        Returns:
            ValidationResult indicating agreement/disagreement.
        """
        ...

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Count tokens in a text string using the model's tokenizer.

        Args:
            text: The text to tokenize.

        Returns:
            Number of tokens.
        """
        ...

    @abstractmethod
    def get_token_usage(self) -> TokenUsage:
        """Return cumulative token usage since adapter creation.

        Returns:
            TokenUsage with prompt and completion token counts.
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Verify connectivity to the LLM provider.

        Returns:
            True if the LLM API is reachable and operational.
        """
        ...
