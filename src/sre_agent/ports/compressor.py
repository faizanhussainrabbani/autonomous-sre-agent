"""
Compressor Port — abstract interface for text compression.

Used to compress evidence chunks before LLM submission to reduce
token consumption while preserving critical SRE information.

Phase 2.2: Token Optimization
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CompressionResult:
    """Result of compressing text."""

    original_text: str
    compressed_text: str
    original_tokens: int
    compressed_tokens: int
    compression_ratio: float


class CompressorPort(ABC):
    """Port for text compression to reduce LLM token usage."""

    @abstractmethod
    def compress(
        self,
        text: str,
        target_ratio: float = 0.5,
        instruction: str = "",
    ) -> CompressionResult:
        """Compress text while preserving key information.

        Args:
            text: Text to compress.
            target_ratio: Target ratio of tokens to KEEP (0.5 = keep 50%).
            instruction: Optional task instruction to guide compression.

        Returns:
            CompressionResult with original and compressed text.
        """
        ...

    @abstractmethod
    def compress_batch(
        self,
        texts: list[str],
        target_ratio: float = 0.5,
    ) -> list[CompressionResult]:
        """Compress multiple texts."""
        ...
