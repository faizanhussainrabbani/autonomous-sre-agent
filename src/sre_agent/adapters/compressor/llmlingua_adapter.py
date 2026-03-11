"""
LLMLingua Compressor Adapter — evidence compression using Microsoft LLMLingua.

Compresses evidence text using a distilled language model to remove
low-information tokens while preserving SRE-critical terminology.

Phase 2.2: Token Optimization

NOTE: This adapter requires the `llmlingua` package. Since this is a
heavy optional dependency (~1.2GB model), it is lazily imported and the
adapter provides a graceful no-op fallback if unavailable.
"""

from __future__ import annotations

import structlog

from sre_agent.ports.compressor import CompressorPort, CompressionResult

logger = structlog.get_logger(__name__)

# SRE-critical tokens that must survive compression
_SRE_FORCE_TOKENS = [
    "OOM", "kill", "restart", "latency", "p99", "p50", "p95",
    "CPU", "memory", "disk", "threshold", "deployment",
    "rollback", "scale", "pod", "container", "node",
    "certificate", "expired", "connection", "timeout",
    "error", "5xx", "4xx", "health", "readiness",
    "service", "namespace", "replica", "crashloop",
]

_DEFAULT_INSTRUCTION = (
    "Preserve SRE incident details, metrics, and remediation steps. "
    "Keep all numerical values, service names, and error codes."
)


class LLMLinguaCompressor(CompressorPort):
    """Compresses evidence text using Microsoft LLMLingua-2.

    Uses a distilled xlm-roberta model to identify and remove
    low-information tokens while preserving technical SRE terminology.

    Falls back to a simple extractive compression if the llmlingua
    package is not installed.
    """

    def __init__(
        self,
        model_name: str = "microsoft/llmlingua-2-xlm-roberta-large-meetingbank",
        use_llmlingua2: bool = True,
        device: str = "cpu",
    ) -> None:
        self._model_name = model_name
        self._use_llmlingua2 = use_llmlingua2
        self._device = device
        self._compressor = None
        self._available = False
        self._init_attempted = False

    def _ensure_compressor(self) -> bool:
        """Lazily initialize the compressor."""
        if self._init_attempted:
            return self._available

        self._init_attempted = True
        try:
            from llmlingua import PromptCompressor
            self._compressor = PromptCompressor(
                model_name=self._model_name,
                use_llmlingua2=self._use_llmlingua2,
                device_map=self._device,
            )
            self._available = True
            logger.info("llmlingua_compressor_initialized", model=self._model_name)
        except (ImportError, Exception) as exc:
            logger.warning(
                "llmlingua_unavailable_using_fallback",
                error=str(exc),
            )
            self._available = False
        return self._available

    def compress(
        self,
        text: str,
        target_ratio: float = 0.5,
        instruction: str = "",
    ) -> CompressionResult:
        """Compress text using LLMLingua or extractive fallback."""
        if not text or len(text.split()) < 10:
            # Too short to compress meaningfully
            return CompressionResult(
                original_text=text,
                compressed_text=text,
                original_tokens=len(text.split()),
                compressed_tokens=len(text.split()),
                compression_ratio=1.0,
            )

        if self._ensure_compressor() and self._compressor is not None:
            return self._compress_llmlingua(text, target_ratio, instruction)

        return self._compress_extractive(text, target_ratio)

    def compress_batch(
        self,
        texts: list[str],
        target_ratio: float = 0.5,
    ) -> list[CompressionResult]:
        """Compress multiple texts."""
        return [self.compress(t, target_ratio) for t in texts]

    def _compress_llmlingua(
        self,
        text: str,
        target_ratio: float,
        instruction: str,
    ) -> CompressionResult:
        """Compress using LLMLingua."""
        result = self._compressor.compress_prompt(
            [text],
            instruction=instruction or _DEFAULT_INSTRUCTION,
            rate=target_ratio,
            force_tokens=_SRE_FORCE_TOKENS,
        )

        compressed_text = result["compressed_prompt"]
        original_tokens = result["origin_tokens"]
        compressed_tokens = result["compressed_tokens"]

        logger.debug(
            "evidence_compressed_llmlingua",
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            ratio=round(compressed_tokens / max(original_tokens, 1), 3),
        )

        return CompressionResult(
            original_text=text,
            compressed_text=compressed_text,
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            compression_ratio=compressed_tokens / max(original_tokens, 1),
        )

    def _compress_extractive(
        self,
        text: str,
        target_ratio: float,
    ) -> CompressionResult:
        """Fallback: extractive compression by keeping important sentences.

        Selects sentences containing SRE keywords and high-information
        content (numbers, error codes) up to the target ratio.
        """
        sentences = [s.strip() for s in text.split(". ") if s.strip()]
        original_word_count = len(text.split())
        target_words = int(original_word_count * target_ratio)

        # Score each sentence by SRE keyword density
        scored: list[tuple[float, str]] = []
        for sentence in sentences:
            lower = sentence.lower()
            keyword_hits = sum(
                1 for kw in _SRE_FORCE_TOKENS if kw.lower() in lower
            )
            # Bonus for sentences with numbers (metrics, thresholds)
            has_numbers = any(c.isdigit() for c in sentence)
            score = keyword_hits + (0.5 if has_numbers else 0)
            scored.append((score, sentence))

        # Sort by score (highest first) and take until budget
        scored.sort(key=lambda x: x[0], reverse=True)

        kept: list[str] = []
        word_count = 0
        for _, sentence in scored:
            words = len(sentence.split())
            if word_count + words <= target_words:
                kept.append(sentence)
                word_count += words

        compressed = ". ".join(kept) + "." if kept else text
        compressed_word_count = len(compressed.split())

        logger.debug(
            "evidence_compressed_extractive",
            original_words=original_word_count,
            compressed_words=compressed_word_count,
            ratio=round(compressed_word_count / max(original_word_count, 1), 3),
        )

        return CompressionResult(
            original_text=text,
            compressed_text=compressed,
            original_tokens=original_word_count,
            compressed_tokens=compressed_word_count,
            compression_ratio=compressed_word_count / max(original_word_count, 1),
        )
