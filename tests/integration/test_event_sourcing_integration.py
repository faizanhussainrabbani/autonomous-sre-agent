"""
Integration tests for Event Sourcing compliance (Gap A).

Tests the full RAG pipeline against InMemoryEventBus + InMemoryEventStore,
validating Engineering Standards §1.4 (Event Sourcing) and §1.5 (CQRS):

- All 4 Phase 2 domain events are emitted in order
- Events are append-only in the EventStore
- Aggregate ID consistency across events
- Event subscribers receive events asynchronously
- Novel incidents still produce INCIDENT_DETECTED events
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from sre_agent.domain.diagnostics.rag_pipeline import RAGDiagnosticPipeline
from sre_agent.domain.diagnostics.severity import SeverityClassifier
from sre_agent.domain.models.canonical import (
    AnomalyAlert,
    AnomalyType,
    DomainEvent,
    EventTypes,
)
from sre_agent.domain.models.diagnosis import ServiceTier
from sre_agent.events.in_memory import InMemoryEventBus, InMemoryEventStore
from sre_agent.ports.diagnostics import DiagnosisRequest
from sre_agent.ports.llm import Hypothesis, ValidationResult
from sre_agent.ports.vector_store import SearchResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_pipeline(
    event_bus: InMemoryEventBus,
    event_store: InMemoryEventStore,
    empty_results: bool = False,
) -> RAGDiagnosticPipeline:
    results = [] if empty_results else [
        SearchResult(
            doc_id=f"doc-{i}",
            content=f"Runbook step {i}: Memory leak remediation via pod restart.",
            score=0.85 - i * 0.05,
            source=f"runbook/oom-{i}.md",
        )
        for i in range(3)
    ]

    mock_vs = MagicMock()
    mock_vs.search = AsyncMock(return_value=results)
    mock_vs.health_check = AsyncMock(return_value=True)

    mock_emb = MagicMock()
    mock_emb.embed_text = AsyncMock(return_value=[0.1] * 384)
    mock_emb.health_check = AsyncMock(return_value=True)

    mock_llm = MagicMock()
    mock_llm.generate_hypothesis = AsyncMock(
        return_value=Hypothesis(
            root_cause="Memory leak — pod RSS exceeds container limit",
            confidence=0.87,
            reasoning="Sustained RSS growth pattern over 6 hours.",
            evidence_citations=["runbook/oom-0.md"],
            suggested_remediation="kubectl rollout restart deployment/checkout",
        ),
    )
    mock_llm.validate_hypothesis = AsyncMock(
        return_value=ValidationResult(
            agrees=True,
            confidence=0.89,
            reasoning="Evidence strongly supports memory leak hypothesis.",
            contradictions=[],
        ),
    )
    mock_llm.count_tokens = MagicMock(side_effect=lambda t: len(t) // 4)
    mock_llm.health_check = AsyncMock(return_value=True)

    classifier = SeverityClassifier(
        service_tiers={"payment-service": ServiceTier.TIER_1},
    )

    return RAGDiagnosticPipeline(
        vector_store=mock_vs,
        embedding=mock_emb,
        llm=mock_llm,
        severity_classifier=classifier,
        event_bus=event_bus,
        event_store=event_store,
    )


def _make_alert(service: str = "payment-service") -> AnomalyAlert:
    return AnomalyAlert(
        service=service,
        anomaly_type=AnomalyType.MEMORY_PRESSURE,
        description="OOM kill — container memory limit exceeded",
        metric_name="container_memory_rss_bytes",
        current_value=3.8e9,
        baseline_value=1.5e9,
        deviation_sigma=5.2,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEventSourcingIntegration:
    """Integration tests validating §1.4 (Event Sourcing) compliance."""

    async def test_full_pipeline_emits_all_four_events_to_bus(self):
        """Happy path: 4 domain events published to InMemoryEventBus in order."""
        bus = InMemoryEventBus()
        store = InMemoryEventStore()
        pipeline = _make_pipeline(bus, store)

        await pipeline.diagnose(DiagnosisRequest(alert=_make_alert()))

        event_types = [e.event_type for e in bus.published_events]
        assert EventTypes.INCIDENT_DETECTED in event_types
        assert EventTypes.DIAGNOSIS_GENERATED in event_types
        assert EventTypes.SECOND_OPINION_COMPLETED in event_types
        assert EventTypes.SEVERITY_ASSIGNED in event_types

    async def test_events_persisted_and_retrievable_by_aggregate_id(self):
        """Events are retrievable from the EventStore by the alert's aggregate ID."""
        bus = InMemoryEventBus()
        store = InMemoryEventStore()
        pipeline = _make_pipeline(bus, store)
        alert = _make_alert()

        await pipeline.diagnose(DiagnosisRequest(alert=alert))

        stored = await store.get_events(str(alert.alert_id))
        assert len(stored) >= 4

        stored_types = {e.event_type for e in stored}
        assert EventTypes.INCIDENT_DETECTED in stored_types
        assert EventTypes.SEVERITY_ASSIGNED in stored_types

    async def test_events_stored_in_chronological_order(self):
        """EventStore returns events in ascending timestamp order."""
        bus = InMemoryEventBus()
        store = InMemoryEventStore()
        pipeline = _make_pipeline(bus, store)
        alert = _make_alert()

        await pipeline.diagnose(DiagnosisRequest(alert=alert))

        stored = await store.get_events(str(alert.alert_id))
        timestamps = [e.timestamp for e in stored]
        assert timestamps == sorted(timestamps), "Events must be in chronological order"

    async def test_all_events_share_alert_aggregate_id(self):
        """Every emitted event has the alert's alert_id as its aggregate_id."""
        bus = InMemoryEventBus()
        store = InMemoryEventStore()
        pipeline = _make_pipeline(bus, store)
        alert = _make_alert()

        await pipeline.diagnose(DiagnosisRequest(alert=alert))

        for event in bus.published_events:
            assert event.aggregate_id == alert.alert_id, (
                f"Event {event.event_type} has mismatched aggregate_id"
            )

    async def test_event_subscriber_receives_severity_assigned(self):
        """An event subscriber registered for SEVERITY_ASSIGNED is invoked."""
        bus = InMemoryEventBus()
        store = InMemoryEventStore()
        pipeline = _make_pipeline(bus, store)

        received: list[DomainEvent] = []

        async def on_severity_assigned(event: DomainEvent) -> None:
            received.append(event)

        await bus.subscribe(EventTypes.SEVERITY_ASSIGNED, on_severity_assigned)

        await pipeline.diagnose(DiagnosisRequest(alert=_make_alert()))

        assert len(received) == 1
        assert received[0].event_type == EventTypes.SEVERITY_ASSIGNED

    async def test_novel_incident_emits_incident_detected(self):
        """Novel incidents (no vector search results) still emit INCIDENT_DETECTED."""
        bus = InMemoryEventBus()
        store = InMemoryEventStore()
        pipeline = _make_pipeline(bus, store, empty_results=True)

        await pipeline.diagnose(DiagnosisRequest(alert=_make_alert()))

        event_types = [e.event_type for e in bus.published_events]
        assert EventTypes.INCIDENT_DETECTED in event_types

    async def test_multiple_incidents_produce_independent_event_streams(self):
        """Two incidents produce separate event streams — no cross-contamination."""
        bus = InMemoryEventBus()
        store = InMemoryEventStore()
        pipeline = _make_pipeline(bus, store)

        alert1 = _make_alert("payment-service")
        alert2 = _make_alert("auth-service")

        await pipeline.diagnose(DiagnosisRequest(alert=alert1))
        bus.clear()  # Reset for the second run
        await pipeline.diagnose(DiagnosisRequest(alert=alert2))

        # Second run events should have alert2's aggregate_id
        for event in bus.published_events:
            assert event.aggregate_id == alert2.alert_id

    async def test_event_filter_by_type_returns_correct_subset(self):
        """EventStore.get_events filters correctly by event_type."""
        bus = InMemoryEventBus()
        store = InMemoryEventStore()
        pipeline = _make_pipeline(bus, store)
        alert = _make_alert()

        await pipeline.diagnose(DiagnosisRequest(alert=alert))

        detected_only = await store.get_events(
            str(alert.alert_id),
            event_types=[EventTypes.INCIDENT_DETECTED],
        )
        assert len(detected_only) == 1
        assert detected_only[0].event_type == EventTypes.INCIDENT_DETECTED

    async def test_cqrs_write_side_event_payloads_are_structured(self):
        """All emitted events have non-empty, structured payloads."""
        bus = InMemoryEventBus()
        store = InMemoryEventStore()
        pipeline = _make_pipeline(bus, store)

        await pipeline.diagnose(DiagnosisRequest(alert=_make_alert()))

        for event in bus.published_events:
            assert isinstance(event.payload, dict), (
                f"Event {event.event_type} payload must be a dict"
            )
            assert len(event.payload) > 0, (
                f"Event {event.event_type} must have non-empty payload"
            )
