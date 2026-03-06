"""
Unit tests for SecondOpinionValidator.

Tests rule-based and cross-check validation strategies.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from sre_agent.domain.diagnostics.validator import SecondOpinionValidator, ValidationStrategy
from sre_agent.ports.llm import Hypothesis, ValidationResult


def _make_hypothesis(**kwargs) -> Hypothesis:
    """Helper to create a Hypothesis with defaults."""
    defaults = {
        "root_cause": "OOM kill due to memory leak in checkout-service",
        "confidence": 0.85,
        "reasoning": "Evidence shows RSS growth over 6 hours",
        "evidence_citations": ["runbook/oom.md"],
        "suggested_remediation": "Increase memory limits",
    }
    defaults.update(kwargs)
    return Hypothesis(**defaults)


class TestSecondOpinionValidator:
    """Tests for hypothesis validation."""

    async def test_rule_based_pass(self):
        validator = SecondOpinionValidator(strategy=ValidationStrategy.RULE_BASED)
        hypothesis = _make_hypothesis()
        result = await validator.validate(hypothesis, evidence_count=3)
        assert result.agrees is True
        assert "passed" in result.reasoning.lower()

    async def test_rule_based_fail_no_citations(self):
        validator = SecondOpinionValidator(strategy=ValidationStrategy.RULE_BASED)
        hypothesis = _make_hypothesis(evidence_citations=[])
        result = await validator.validate(hypothesis, evidence_count=3)
        assert result.agrees is False
        assert "no evidence" in result.reasoning.lower()

    async def test_rule_based_fail_zero_confidence(self):
        validator = SecondOpinionValidator(strategy=ValidationStrategy.RULE_BASED)
        hypothesis = _make_hypothesis(confidence=0.0)
        result = await validator.validate(hypothesis, evidence_count=1)
        assert result.agrees is False
        assert "zero" in result.reasoning.lower()

    async def test_rule_based_fail_empty_root_cause(self):
        validator = SecondOpinionValidator(strategy=ValidationStrategy.RULE_BASED)
        hypothesis = _make_hypothesis(root_cause="  ")
        result = await validator.validate(hypothesis, evidence_count=1)
        assert result.agrees is False
        assert "empty" in result.reasoning.lower()

    async def test_cross_check_agreement(self):
        mock_llm = MagicMock()
        mock_llm.validate_hypothesis = AsyncMock(return_value=ValidationResult(
            agrees=True,
            confidence=0.90,
            reasoning="Hypothesis well-supported by evidence.",
            contradictions=[],
        ))
        validator = SecondOpinionValidator(
            llm=mock_llm, strategy=ValidationStrategy.CROSS_CHECK,
        )
        hypothesis = _make_hypothesis()
        result = await validator.validate(hypothesis, alert_description="latency spike")
        assert result.agrees is True
        mock_llm.validate_hypothesis.assert_called_once()

    async def test_cross_check_disagreement(self):
        mock_llm = MagicMock()
        mock_llm.validate_hypothesis = AsyncMock(return_value=ValidationResult(
            agrees=False,
            confidence=0.40,
            reasoning="Evidence contradicts hypothesis.",
            contradictions=["Claim X unsupported."],
        ))
        validator = SecondOpinionValidator(
            llm=mock_llm, strategy=ValidationStrategy.CROSS_CHECK,
        )
        hypothesis = _make_hypothesis()
        result = await validator.validate(hypothesis, alert_description="latency spike")
        assert result.agrees is False
        assert len(result.contradictions) > 0

    async def test_both_strategy_short_circuits_on_rule_failure(self):
        mock_llm = MagicMock()
        mock_llm.validate_hypothesis = AsyncMock()
        validator = SecondOpinionValidator(
            llm=mock_llm, strategy=ValidationStrategy.BOTH,
        )
        hypothesis = _make_hypothesis(root_cause="")
        result = await validator.validate(hypothesis, evidence_count=1)
        assert result.agrees is False
        mock_llm.validate_hypothesis.assert_not_called()
