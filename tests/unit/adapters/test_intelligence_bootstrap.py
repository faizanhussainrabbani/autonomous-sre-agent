"""Unit tests for Intelligence Layer bootstrap factories."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, Mock

from sre_agent.adapters import intelligence_bootstrap as bootstrap
from sre_agent.adapters.llm.throttled_adapter import ThrottledLLMAdapter
from sre_agent.ports.llm import LLMConfig, LLMProvider


def _install_module(monkeypatch, module_name: str, **attrs: object) -> None:
    module = types.ModuleType(module_name)
    for name, value in attrs.items():
        setattr(module, name, value)
    monkeypatch.setitem(sys.modules, module_name, module)


class TestFactoryCreation:
    """Tests for low-level adapter factory functions."""

    def test_create_vector_store_passes_configuration(self, monkeypatch) -> None:
        class FakeChromaVectorStoreAdapter:
            def __init__(self, collection_name: str, persist_directory: str | None) -> None:
                self.collection_name = collection_name
                self.persist_directory = persist_directory

        _install_module(
            monkeypatch,
            "sre_agent.adapters.vectordb.chroma.adapter",
            ChromaVectorStoreAdapter=FakeChromaVectorStoreAdapter,
        )

        adapter = bootstrap.create_vector_store(
            collection_name="incident-docs",
            persist_directory="/tmp/chroma",
        )

        assert isinstance(adapter, FakeChromaVectorStoreAdapter)
        assert adapter.collection_name == "incident-docs"
        assert adapter.persist_directory == "/tmp/chroma"

    def test_create_embedding_returns_sentence_adapter(self, monkeypatch) -> None:
        class FakeSentenceAdapter:
            pass

        _install_module(
            monkeypatch,
            "sre_agent.adapters.embedding.sentence_transformers_adapter",
            SentenceTransformersEmbeddingAdapter=FakeSentenceAdapter,
        )

        adapter = bootstrap.create_embedding()
        assert isinstance(adapter, FakeSentenceAdapter)


class TestLLMProviderSelection:
    """Tests for provider selection logic in create_llm."""

    def test_create_llm_prefers_explicit_config_provider(self, monkeypatch) -> None:
        class FakeAnthropicAdapter:
            def __init__(self, config):
                self.config = config

        class FakeOpenAIAdapter:
            def __init__(self, config):
                self.config = config

        _install_module(
            monkeypatch,
            "sre_agent.adapters.llm.anthropic.adapter",
            AnthropicLLMAdapter=FakeAnthropicAdapter,
        )
        _install_module(
            monkeypatch,
            "sre_agent.adapters.llm.openai.adapter",
            OpenAILLMAdapter=FakeOpenAIAdapter,
        )
        monkeypatch.setenv("ANTHROPIC_API_KEY", "k-ant")
        monkeypatch.setenv("OPENAI_API_KEY", "k-open")

        config = LLMConfig(provider=LLMProvider.ANTHROPIC)
        llm = bootstrap.create_llm(config)

        assert isinstance(llm, FakeAnthropicAdapter)
        assert llm.config is config

    def test_create_llm_prefers_anthropic_when_both_env_keys_exist(self, monkeypatch) -> None:
        class FakeAnthropicAdapter:
            def __init__(self, config):
                self.config = config

        class FakeOpenAIAdapter:
            def __init__(self, config):
                self.config = config

        _install_module(
            monkeypatch,
            "sre_agent.adapters.llm.anthropic.adapter",
            AnthropicLLMAdapter=FakeAnthropicAdapter,
        )
        _install_module(
            monkeypatch,
            "sre_agent.adapters.llm.openai.adapter",
            OpenAILLMAdapter=FakeOpenAIAdapter,
        )
        monkeypatch.setenv("ANTHROPIC_API_KEY", "k-ant")
        monkeypatch.setenv("OPENAI_API_KEY", "k-open")

        llm = bootstrap.create_llm()

        assert isinstance(llm, FakeAnthropicAdapter)
        assert llm.config is None

    def test_create_llm_uses_openai_when_only_openai_key_exists(self, monkeypatch) -> None:
        class FakeOpenAIAdapter:
            def __init__(self, config):
                self.config = config

        _install_module(
            monkeypatch,
            "sre_agent.adapters.llm.openai.adapter",
            OpenAILLMAdapter=FakeOpenAIAdapter,
        )
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "k-open")

        llm = bootstrap.create_llm()

        assert isinstance(llm, FakeOpenAIAdapter)
        assert llm.config is None

    def test_create_llm_defaults_to_openai_without_env_keys(self, monkeypatch) -> None:
        class FakeOpenAIAdapter:
            def __init__(self, config):
                self.config = config

        _install_module(
            monkeypatch,
            "sre_agent.adapters.llm.openai.adapter",
            OpenAILLMAdapter=FakeOpenAIAdapter,
        )
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        llm = bootstrap.create_llm()

        assert isinstance(llm, FakeOpenAIAdapter)
        assert llm.config is None


class TestPipelineWiring:
    """Tests for higher-level pipeline wiring factories."""

    def test_create_diagnostic_pipeline_wraps_plain_llm(self) -> None:
        vector_store = object()
        embedding = object()
        raw_llm = MagicMock(name="raw_llm")

        pipeline = bootstrap.create_diagnostic_pipeline(
            vector_store=vector_store,
            embedding=embedding,
            llm=raw_llm,
            context_budget=1024,
        )

        assert pipeline._vector_store is vector_store
        assert pipeline._embedding is embedding
        assert isinstance(pipeline._llm, ThrottledLLMAdapter)
        assert pipeline._llm._inner is raw_llm
        assert pipeline._context_budget == 1024

    def test_create_diagnostic_pipeline_keeps_prethrottled_llm(self) -> None:
        vector_store = object()
        embedding = object()
        throttled = ThrottledLLMAdapter(MagicMock(name="inner"))

        pipeline = bootstrap.create_diagnostic_pipeline(
            vector_store=vector_store,
            embedding=embedding,
            llm=throttled,
        )

        assert pipeline._llm is throttled

    def test_create_diagnostic_pipeline_uses_default_factories(self, monkeypatch) -> None:
        vector_store = object()
        embedding = object()
        llm = MagicMock(name="llm")

        vector_store_factory = Mock(return_value=vector_store)
        embedding_factory = Mock(return_value=embedding)
        llm_factory = Mock(return_value=llm)
        monkeypatch.setattr(bootstrap, "create_vector_store", vector_store_factory)
        monkeypatch.setattr(bootstrap, "create_embedding", embedding_factory)
        monkeypatch.setattr(bootstrap, "create_llm", llm_factory)

        pipeline = bootstrap.create_diagnostic_pipeline()

        vector_store_factory.assert_called_once_with()
        embedding_factory.assert_called_once_with()
        llm_factory.assert_called_once_with()
        assert pipeline._vector_store is vector_store
        assert pipeline._embedding is embedding
        assert isinstance(pipeline._llm, ThrottledLLMAdapter)
        assert pipeline._llm._inner is llm

    def test_create_ingestion_pipeline_uses_default_factories(self, monkeypatch) -> None:
        vector_store = object()
        embedding = object()

        vector_store_factory = Mock(return_value=vector_store)
        embedding_factory = Mock(return_value=embedding)
        monkeypatch.setattr(bootstrap, "create_vector_store", vector_store_factory)
        monkeypatch.setattr(bootstrap, "create_embedding", embedding_factory)

        pipeline = bootstrap.create_ingestion_pipeline()

        vector_store_factory.assert_called_once_with()
        embedding_factory.assert_called_once_with()
        assert pipeline._vector_store is vector_store
        assert pipeline._embedding is embedding

    def test_create_ingestion_pipeline_respects_explicit_dependencies(self) -> None:
        vector_store = object()
        embedding = object()

        pipeline = bootstrap.create_ingestion_pipeline(
            vector_store=vector_store,
            embedding=embedding,
        )

        assert pipeline._vector_store is vector_store
        assert pipeline._embedding is embedding
