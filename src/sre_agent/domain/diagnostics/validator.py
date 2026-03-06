"""
Second-Opinion Validator — hypothesis cross-validation.

Provides rule-based and LLM cross-check validation strategies to
detect hallucinations and unsupported conclusions.

Phase 2: Intelligence Layer — Sprint 2 (Reasoning & Inference)
"""

from __future__ import annotations

from enum import Enum

from sre_agent.ports.llm import (
    Hypothesis,
    LLMReasoningPort,
    ValidationRequest,
    ValidationResult,
)


class ValidationStrategy(Enum):
    """Available validation strategies."""

    RULE_BASED = "rule_based"
    CROSS_CHECK = "cross_check"
    BOTH = "both"


class SecondOpinionValidator:
    """Validates diagnostic hypotheses using rule-based and LLM strategies."""

    def __init__(
        self,
        llm: LLMReasoningPort | None = None,
        strategy: ValidationStrategy = ValidationStrategy.RULE_BASED,
    ) -> None:
        self._llm = llm
        self._strategy = strategy

    async def validate(
        self,
        hypothesis: Hypothesis,
        evidence_count: int = 0,
        alert_description: str = "",
    ) -> ValidationResult:
        """Validate a hypothesis using the configured strategy.

        Args:
            hypothesis: The hypothesis to validate.
            evidence_count: Number of evidence items that were available.
            alert_description: Original alert description for context.

        Returns:
            ValidationResult with agreement status and reasoning.
        """
        if self._strategy == ValidationStrategy.RULE_BASED:
            return self._rule_based_validate(hypothesis, evidence_count)

        if self._strategy == ValidationStrategy.CROSS_CHECK:
            return await self._cross_check_validate(
                hypothesis, alert_description,
            )

        # BOTH: run rule-based first, then cross-check if it passes
        rule_result = self._rule_based_validate(hypothesis, evidence_count)
        if not rule_result.agrees:
            return rule_result

        if self._llm is not None:
            return await self._cross_check_validate(
                hypothesis, alert_description,
            )
        return rule_result

    def _rule_based_validate(
        self,
        hypothesis: Hypothesis,
        evidence_count: int,
    ) -> ValidationResult:
        """Apply deterministic validation rules.

        Rules:
        1. Hypothesis must cite at least one piece of evidence.
        2. Confidence must be non-zero.
        3. Root cause must be non-empty.
        """
        contradictions: list[str] = []

        if not hypothesis.evidence_citations and evidence_count > 0:
            contradictions.append(
                "Hypothesis cites no evidence despite available evidence."
            )

        if hypothesis.confidence <= 0.0:
            contradictions.append("Confidence is zero or negative.")

        if not hypothesis.root_cause.strip():
            contradictions.append("Root cause is empty.")

        agrees = len(contradictions) == 0
        return ValidationResult(
            agrees=agrees,
            confidence=hypothesis.confidence if agrees else 0.0,
            reasoning="Rule-based validation passed." if agrees
            else f"Validation failed: {'; '.join(contradictions)}",
            contradictions=contradictions,
        )

    async def _cross_check_validate(
        self,
        hypothesis: Hypothesis,
        alert_description: str,
    ) -> ValidationResult:
        """Use LLM cross-check to validate the hypothesis."""
        if self._llm is None:
            return ValidationResult(
                agrees=True,
                confidence=hypothesis.confidence,
                reasoning="No LLM available for cross-check; assuming valid.",
                contradictions=[],
            )

        request = ValidationRequest(
            hypothesis=hypothesis,
            alert_description=alert_description,
        )
        return await self._llm.validate_hypothesis(request)
