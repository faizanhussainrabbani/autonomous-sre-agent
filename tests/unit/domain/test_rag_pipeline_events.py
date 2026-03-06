"""
Unit tests for domain event emission in RAGDiagnosticPipeline.

Tests Gap A: Engineering Standards §1.4 / §1.5 compliance.
- INCIDENT_DETECTED emitted at pipeline start
- DIAGNOSIS_GENERATED emitted after LLM hypothesis
- SECOND_OPINION_COMPLETED emitted after validation
- SEVERITY_ASSIGNED emitted after classification
- Events persisted to EventStore
- Event emission failure does not abort diagnosis
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from sre_agent.domain.diagnostics.rag_pipeline import RAGDiagnosticPipeline
from sre_agent.domain.diagnostics.severity import SeverityClassifier
from sre_agent.domain.models.canonical import AnomalyAlert, AnomalyType, EventTypes
from sre_agent.domain.models.diagnosis import ServiceTier
from sre_agent.events.in_memory import InMemoryEventBus, InMemoryEventStore
from sre_agent.ports.diagnostics import DiagnosisRequest
from sre_agent.ports.llm import Hypothesis, ValidationResult
from sre_agent.ports.vector_store import SearchResult


def _make_search_results(n: int = 2) -> list[SearchResult]:
    return [
        SearchResult(
            doc_id=f"doc-{i}",
            content=f"Runbook section {i}: OOM recovery procedures for containers.",
            score=0.85 - i * 0.05,
            source=f"runbook/oom-{i}.md",
        )
        for i in range(n)
    ]


def _make_pipeline(
    event_bus: InMemoryEventBus | None = None,
    event_store: InMemoryEventStore | None = None,
    search_results: list[SearchResult] | None = None,
) -> RAGDiagnosticPipeline:
    mock_vs = MagicMock()
    mock_vs.search = AsyncMock(return_value=search_results if search_results is not None else _make_search_results())
    mock_vs.health_check = AsyncMock(return_value=True)

    mock_emb = MagicMock()
    mock_emb.embed_text = AsyncMock(return_value=[0.1] * 384)
    mock_emb.health_check = AsyncMock(return_value=True)

    mock_llm = MagicMock()
    mock_llm.generate_hypothesis = AsyncMock(
        return_value=Hypothesis(
            root_cause="Memory leak in checkout-service",
            confidence=0.88,
            reasoning="RSS growth indicates a leak.",
            evidence_citations=["runbook/oom.md"],
            suggested_remediation="Restart pod.",
        ),
    )
    mock_llm.validate_hypothesis = AsyncMock(
        return_value=ValidationResult(
            agrees=True,
            confidence=0.90,
            reasoning="Hypothesis is well-supported.",
            contradictions=[],
        ),
    )
    mock_llm.count_tokens = MagicMock(side_effect=lambda t: len(t) // 4)
    mock_llm.health_check = AsyncMock(return_value=True)

    classifier = SeverityClassifier(
        service_tiers={"checkout-service": ServiceTier.TIER_1},
    )

    return RAGDiagnosticPipeline(
        vector_store=mock_vs,
        embedding=mock_emb,
        llm=mock_llm,
        severity_classifier=classifier,
        event_bus=event_bus,
        event_store=event_store,
    )


def _make_alert() -> AnomalyAlert:
    return AnomalyAlert(
        service="checkout-service",
        anomaly_type=AnomalyType.MEMORY_PRESSURE,
        description="OOM kill detected",
        metric_name="container_memory_rss",
        current_value=4.0,
        baseline_value=2.0,
        deviation_sigma=4.5,
    )


class TestRAGPipelineEventEmission:
    """Tests for domain event emission from the RAG diagnostic pipeline."""

    async def test_incident_detected_event_emitted(self):
        """INCIDENT_DETECTED is emitted at the start of every diagnosis."""
        bus = InMemoryEventBus()
        pipeline = _make_pipeline(event_bus=bus)

        await pipeline.diagnose(DiagnosisRequest(alert=_make_alert()))

        event_types = [e.event_type for e in bus.published_events]
        assert EventTypes.INCIDENT_DETECTED in event_types

    async def test_diagnosis_generated_event_emitted(self):
        """DIAGNOSIS_GENERATED is emitted after the LLM generates a hypothesis."""
        bus = InMemoryEventBus()
        pipeline = _make_pipeline(event_bus=bus)

        await pipeline.diagnose(DiagnosisRequest(alert=_make_alert()))

        event_types = [e.event_type for e in bus.published_events]
        assert EventTypes.DIAGNOSIS_GENERATED in event_types

    async def test_second_opinion_completed_event_emitted(self):
        """SECOND_OPINION_COMPLETED is emitted after hypothesis validation."""
        bus = InMemoryEventBus()
        pipeline = _make_pipeline(event_bus=bus)

        await pipeline.diagnose(DiagnosisRequest(alert=_make_alert()))

        event_types = [e.event_type for e in bus.published_events]
        assert EventTypes.SECOND_OPINION_COMPLETED in event_types

    async def test_severity_assigned_event_emitted(self):
        """SEVERITY_ASSIGNED is emitted after severity classification."""
        bus = InMemoryEventBus()
        pipeline = _make_pipeline(event_bus=bus)

        await pipeline.diagnose(DiagnosisRequest(alert=_make_alert()))

        event_types = [e.event_type for e in bus.published_events]
        assert EventTypes.SEVERITY_ASSIGNED in event_types

    async def test_all_four_events_emitted_in_sequence(self):
        """All 4 phase-2 events are emitted in the correct lifecycle order."""
        bus = InMemoryEventBus()
        pipeline = _make_pipeline(event_bus=bus)

        await pipeline.diagnose(DiagnosisRequest(alert=_make_alert()))

        event_types = [e.event_type for e in bus.published_events]
        expected = [
            EventTypes.INCIDENT_DETECTED,
            EventTypes.DIAGNOSIS_GENERATED,
            EventTypes.SECOND_OPINION_COMPLETED,
            EventTypes.SEVERITY_ASSIGNED,
        ]
        for et in expected:
            assert et in event_types

        # Ordering: INCIDENT_DETECTED before DIAGNOSIS_GENERATED, etc.
        idx = {et: event_types.index(et) for et in expected}
        assert idx[EventTypes.INCIDENT_DETECTED] < idx[EventTypes.DIAGNOSIS_GENERATED]
        assert idx[EventTypes.DIAGNOSIS_GENERATED] < idx[EventTypes.SECOND_OPINION_COMPLETED]
        assert idx[EventTypes.SECOND_OPINION_COMPLETED] < idx[EventTypes.SEVERITY_ASSIGNED]

    async def test_events_persisted_to_event_store(self):
        """Events are appended to the EventStore for immutable audit logging."""
        store = InMemoryEventStore()
        pipeline = _make_pipeline(event_store=store)
        alert = _make_alert()

        await pipeline.diagnose(DiagnosisRequest(alert=alert))

        stored = await store.get_events(str(alert.alert_id))
        event_types = [e.event_type for e in stored]
        assert EventTypes.INCIDENT_DETECTED in event_types
        assert EventTypes.SEVERITY_ASSIGNED in event_types

    async def test_events_carry_alert_aggregate_id(self):
        """All events share the alert's alert_id as aggregate_id."""
        bus = InMemoryEventBus()
        pipeline = _make_pipeline(event_bus=bus)
        alert = _make_alert()

        await pipeline.diagnose(DiagnosisRequest(alert=alert))

        for event in bus.published_events:
            assert event.aggregate_id == alert.alert_id, (
                f"Event {event.event_type} has wrong aggregate_id: {event.aggregate_id}"
            )

    async def test_pipeline_works_without_event_bus_or_store(self):
        """Pipeline completes successfully when no event bus/store is wired."""
        pipeline = _make_pipeline(event_bus=None, event_store=None)
        result = await pipeline.diagnose(DiagnosisRequest(alert=_make_alert()))

        assert result.root_cause == "Memory leak in checkout-service"

    async def test_event_emission_failure_does_not_abort_pipeline(self):
        """If the event bus raises, the pipeline still returns a DiagnosisResult."""
        bus = MagicMock()
        bus.publish = AsyncMock(side_effect=RuntimeError("Kafka unavailable"))
        pipeline = _make_pipeline(event_bus=bus)

        # Should not raise — fire-and-forget semantics
        result = await pipeline.diagnose(DiagnosisRequest(alert=_make_alert()))
        assert result.root_cause == "Memory leak in checkout-service"

    async def test_novel_incident_emits_incident_detected(self):
        """Novel incidents (no search results) still emit INCIDENT_DETECTED."""
        bus = InMemoryEventBus()
        pipeline = _make_pipeline(event_bus=bus, search_results=[])

        await pipeline.diagnose(DiagnosisRequest(alert=_make_alert()))

        event_types = [e.event_type for e in bus.published_events]
        assert EventTypes.INCIDENT_DETECTED in event_types

    async def test_incident_detected_payload_contains_service(self):
        """INCIDENT_DETECTED payload includes service name and anomaly type."""
        bus = InMemoryEventBus()
        pipeline = _make_pipeline(event_bus=bus)
        alert = _make_alert()

        await pipeline.diagnose(DiagnosisRequest(alert=alert))

        detected = next(
            e for e in bus.published_events
            if e.event_type == EventTypes.INCIDENT_DETECTED
        )
        assert detected.payload["service"] == "checkout-service"
        assert "anomaly_type" in detected.payload

    async def test_severity_assigned_payload_contains_severity(self):
        """SEVERITY_ASSIGNED payload includes the assigned severity name."""
        bus = InMemoryEventBus()
        pipeline = _make_pipeline(event_bus=bus)

        await pipeline.diagnose(DiagnosisRequest(alert=_make_alert()))

        assigned = next(
            e for e in bus.published_events
            if e.event_type == EventTypes.SEVERITY_ASSIGNED
        )
        assert "severity" in assigned.payload
        assert assigned.payload["severity"] in ("SEV1", "SEV2", "SEV3", "SEV4")
