"""Unit tests for SentenceTransformersEmbeddingAdapter."""

from __future__ import annotations

import builtins
import sys
import types

import pytest

from sre_agent.adapters.embedding.sentence_transformers_adapter import (
    SentenceTransformersEmbeddingAdapter,
)
from sre_agent.ports.embedding import EmbeddingConfig


class _FakeVector:
    def __init__(self, values: list[float]) -> None:
        self._values = values

    def tolist(self) -> list[float]:
        return list(self._values)


def _install_fake_sentence_transformers(monkeypatch):
    created_instances: list[object] = []

    class FakeSentenceTransformer:
        def __init__(self, model_name: str) -> None:
            self.model_name = model_name
            self.calls: list[tuple[object, dict[str, object]]] = []
            created_instances.append(self)

        def encode(self, payload, **kwargs):
            self.calls.append((payload, kwargs))
            if isinstance(payload, str):
                return _FakeVector([0.1, 0.2, 0.3])
            return [_FakeVector([float(i), float(i) + 0.1]) for i, _ in enumerate(payload)]

    module = types.ModuleType("sentence_transformers")
    module.SentenceTransformer = FakeSentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)

    return created_instances


class TestSentenceTransformersEmbeddingAdapter:
    """Behavioral tests for lazy loading and embedding calls."""

    def test_load_model_raises_clear_error_when_dependency_missing(self, monkeypatch):
        adapter = SentenceTransformersEmbeddingAdapter()
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "sentence_transformers":
                raise ImportError("module not installed")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        with pytest.raises(ImportError, match="sre-agent\\[intelligence\\]"):
            adapter._load_model()

    async def test_embed_text_loads_model_once_and_reuses_it(self, monkeypatch):
        created_instances = _install_fake_sentence_transformers(monkeypatch)
        adapter = SentenceTransformersEmbeddingAdapter()

        first = await adapter.embed_text("service degraded")
        second = await adapter.embed_text("service recovered")

        assert first == [0.1, 0.2, 0.3]
        assert second == [0.1, 0.2, 0.3]
        assert len(created_instances) == 1
        encoded_payloads = [payload for payload, _ in created_instances[0].calls]
        assert encoded_payloads == ["service degraded", "service recovered"]
        for _, kwargs in created_instances[0].calls:
            assert kwargs["normalize_embeddings"] is True

    async def test_embed_batch_respects_batch_size_and_normalization(self, monkeypatch):
        created_instances = _install_fake_sentence_transformers(monkeypatch)
        adapter = SentenceTransformersEmbeddingAdapter(
            EmbeddingConfig(batch_size=8, normalize=False),
        )

        result = await adapter.embed_batch(["alpha", "beta"])

        assert result == [[0.0, 0.1], [1.0, 1.1]]
        assert len(created_instances) == 1
        payload, kwargs = created_instances[0].calls[0]
        assert payload == ["alpha", "beta"]
        assert kwargs["batch_size"] == 8
        assert kwargs["normalize_embeddings"] is False

    def test_get_dimensions_returns_config_dimensions(self):
        adapter = SentenceTransformersEmbeddingAdapter(EmbeddingConfig(dimensions=768))
        assert adapter.get_dimensions() == 768

    async def test_health_check_true_when_model_loads(self, monkeypatch):
        _install_fake_sentence_transformers(monkeypatch)
        adapter = SentenceTransformersEmbeddingAdapter()

        assert await adapter.health_check() is True

    async def test_health_check_false_when_model_loading_fails(self, monkeypatch):
        adapter = SentenceTransformersEmbeddingAdapter()

        def raise_runtime_error() -> None:
            raise RuntimeError("boom")

        monkeypatch.setattr(adapter, "_load_model", raise_runtime_error)

        assert await adapter.health_check() is False
