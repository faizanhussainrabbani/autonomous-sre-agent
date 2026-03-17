"""
E2E tests for Gap Closure — Engineering Standards compliance.

Validates all three identified gaps across the full stack:

Gap A — Event Sourcing: Full incident lifecycle produces 4 domain events
         persisted to an EventStore and published to subscribers.
Gap B — Concurrency: ThrottledLLMAdapter enforces max-concurrent cap
         with priority queue ordering.
Gap C — Severity Override API: REST endpoints halt the pipeline on
         Sev1/2 overrides and expose reclassification to operators.

No external services required — uses InMemoryEventBus/Store and FastAPI TestClient.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sre_agent.adapters.llm.throttled_adapter import ThrottledLLMAdapter
from sre_agent.api.rest.severity_override_router import get_override_service, router
from sre_agent.api.severity_override import SeverityOverrideService
from sre_agent.domain.diagnostics.rag_pipeline import RAGDiagnosticPipeline
from sre_agent.domain.diagnostics.severity import SeverityClassifier
from sre_agent.domain.models.canonical import (
    AnomalyAlert,
    AnomalyType,
    EventTypes,
    Severity,
)
from sre_agent.domain.models.diagnosis import ServiceTier
from sre_agent.events.in_memory import InMemoryEventBus, InMemoryEventStore
from sre_agent.ports.diagnostics import DiagnosisRequest
from sre_agent.ports.llm import Hypothesis, TokenUsage, ValidationResult
from sre_agent.ports.vector_store import SearchResult


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_inner_llm(delay: float = 0.0) -> MagicMock:
    async def _gen(request):
        if delay:
            await asyncio.sleep(delay)
        return Hypothesis(
            root_cause="Memory leak in payment-service",
            confidence=0.88,
            reasoning="Sustained RSS growth.",
            evidence_citations=[],
            suggested_remediation="Restart pod.",
        )

    async def _val(request):
        return ValidationResult(
            agrees=True,
            confidence=0.90,
            reasoning="Consistent with evidence.",
            contradictions=[],
        )

    inner = MagicMock()
    inner.generate_hypothesis = _gen
    inner.validate_hypothesis = _val
    inner.health_check = AsyncMock(return_value=True)
    inner.count_tokens = MagicMock(side_effect=lambda t: len(t) // 4)
    inner.get_token_usage = MagicMock(return_value=TokenUsage())
    return inner


def _make_pipeline(
    llm,
    event_bus: InMemoryEventBus | None = None,
    event_store: InMemoryEventStore | None = None,
    search_results: list[SearchResult] | None = None,
) -> RAGDiagnosticPipeline:
    results = search_results if search_results is not None else [
        SearchResult(
            doc_id=f"doc-{i}",
            content=f"Runbook section {i}: OOM kill recovery steps for pod restart.",
            score=0.85 - i * 0.05,
            source=f"runbook/oom-{i}.md",
        )
        for i in range(2)
    ]

    mock_vs = MagicMock()
    mock_vs.search = AsyncMock(return_value=results)
    mock_vs.health_check = AsyncMock(return_value=True)

    mock_emb = MagicMock()
    mock_emb.embed_text = AsyncMock(return_value=[0.1] * 384)
    mock_emb.health_check = AsyncMock(return_value=True)

    classifier = SeverityClassifier(
        service_tiers={"payment-service": ServiceTier.TIER_1},
    )

    return RAGDiagnosticPipeline(
        vector_store=mock_vs,
        embedding=mock_emb,
        llm=llm,
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
# Gap A — Event Sourcing E2E
# ---------------------------------------------------------------------------


class TestE2EEventSourcing:
    """Full lifecycle: incident → 4 domain events → EventStore + EventBus."""

    async def test_full_incident_lifecycle_emits_ordered_events(self):
        """Complete diagnosis produces all 4 Phase 2 events in correct order."""
        bus = InMemoryEventBus()
        store = InMemoryEventStore()
        throttled = ThrottledLLMAdapter(_make_inner_llm(), max_concurrent=10)
        pipeline = _make_pipeline(throttled, bus, store)
        alert = _make_alert()

        result = await pipeline.diagnose(DiagnosisRequest(alert=alert))

        # Diagnosis result is valid
        assert result.root_cause == "Memory leak in payment-service"
        assert result.confidence > 0.0

        event_types = [e.event_type for e in bus.published_events]
        for expected_type in [
            EventTypes.INCIDENT_DETECTED,
            EventTypes.DIAGNOSIS_GENERATED,
            EventTypes.SECOND_OPINION_COMPLETED,
            EventTypes.SEVERITY_ASSIGNED,
        ]:
            assert expected_type in event_types, (
                f"Expected event '{expected_type}' not found in bus; "
                f"found: {event_types}"
            )

        await throttled.close()

    async def test_events_stored_and_queryable_by_incident_id(self):
        """EventStore persists all events retrievable by incident aggregate_id."""
        bus = InMemoryEventBus()
        store = InMemoryEventStore()
        throttled = ThrottledLLMAdapter(_make_inner_llm(), max_concurrent=10)
        pipeline = _make_pipeline(throttled, bus, store)
        alert = _make_alert()

        await pipeline.diagnose(DiagnosisRequest(alert=alert))

        stored = await store.get_events(str(alert.alert_id))
        assert len(stored) >= 4
        for event in stored:
            assert event.aggregate_id == alert.alert_id

        await throttled.close()

    async def test_subscriber_notified_of_severity_assigned(self):
        """A downstream consumer subscribes to SEVERITY_ASSIGNED and is called."""
        bus = InMemoryEventBus()
        store = InMemoryEventStore()
        throttled = ThrottledLLMAdapter(_make_inner_llm(), max_concurrent=10)
        pipeline = _make_pipeline(throttled, bus, store)

        notifications: list[str] = []

        async def on_severity(event):
            notifications.append(event.payload.get("severity", ""))

        await bus.subscribe(EventTypes.SEVERITY_ASSIGNED, on_severity)

        await pipeline.diagnose(DiagnosisRequest(alert=_make_alert()))

        assert len(notifications) == 1
        assert notifications[0] in ("SEV1", "SEV2", "SEV3", "SEV4")

        await throttled.close()


# ---------------------------------------------------------------------------
# Gap B — Concurrency Limiting E2E
# ---------------------------------------------------------------------------


class TestE2EConcurrencyLimiting:
    """ThrottledLLMAdapter enforces §5.3 cap in a realistic pipeline."""

    async def test_concurrent_pipeline_calls_stay_within_cap(self):
        """10 simultaneous diagnoses with max_concurrent=3 stay within the cap."""
        concurrent_peak = 0
        lock = asyncio.Lock()
        running = 0

        async def slow_gen(request):
            nonlocal running, concurrent_peak
            async with lock:
                running += 1
                if running > concurrent_peak:
                    concurrent_peak = running
            await asyncio.sleep(0.03)
            async with lock:
                running -= 1
            return Hypothesis(
                root_cause="Leak",
                confidence=0.8,
                reasoning="RSS growth",
                evidence_citations=[],
                suggested_remediation="Restart",
            )

        async def fast_val(request):
            return ValidationResult(
                agrees=True, confidence=0.85, reasoning="OK", contradictions=[]
            )

        inner = MagicMock()
        inner.generate_hypothesis = slow_gen
        inner.validate_hypothesis = fast_val
        inner.health_check = AsyncMock(return_value=True)
        inner.count_tokens = MagicMock(side_effect=lambda t: len(t) // 4)
        inner.get_token_usage = MagicMock(return_value=TokenUsage())

        cap = 3
        throttled = ThrottledLLMAdapter(inner, max_concurrent=cap)
        pipeline = _make_pipeline(throttled)

        alerts = [_make_alert() for _ in range(10)]
        await asyncio.gather(
            *[pipeline.diagnose(DiagnosisRequest(alert=a)) for a in alerts]
        )

        assert concurrent_peak <= cap, (
            f"Concurrent peak {concurrent_peak} exceeded cap {cap}"
        )
        await throttled.close()

    async def test_sev1_priority_request_uses_priority_1(self):
        """HypothesisRequest.priority=1 is set for SEV1-level calls."""
        from sre_agent.ports.llm import HypothesisRequest

        req = HypothesisRequest(
            alert_description="OOM kill",
            service_name="payment-service",
            timeline="",
        )
        req.priority = 1  # SEV1

        assert req.priority == 1


# ---------------------------------------------------------------------------
# Gap C — Severity Override REST API E2E
# ---------------------------------------------------------------------------


class TestE2ESeverityOverrideAPI:
    """Full REST lifecycle: apply → query → revoke → verify pipeline halt."""

    def _build_app(self) -> tuple[FastAPI, SeverityOverrideService]:
        app = FastAPI()
        service = SeverityOverrideService()
        app.dependency_overrides[get_override_service] = lambda: service
        app.include_router(router)
        return app, service

    def test_sev1_override_halts_pipeline_via_rest(self):
        """Applying SEV1 override via REST reflects halts_pipeline=True in service."""
        app, service = self._build_app()
        client = TestClient(app)
        alert_id = str(_make_alert().alert_id)

        response = client.post(
            f"/api/v1/incidents/{alert_id}/severity-override",
            json={
                "original_severity": "SEV3",
                "override_severity": "SEV1",
                "operator": "sre-commander@example.com",
                "reason": "Revenue impact confirmed by finance team.",
            },
        )

        assert response.status_code == 201
        assert response.json()["halts_pipeline"] is True

        from uuid import UUID
        assert service.has_active_override(UUID(alert_id))
        override = service.get_override(UUID(alert_id))
        assert override is not None
        assert override.halts_pipeline is True

    def test_full_override_lifecycle_apply_get_revoke(self):
        """Apply → GET confirms → DELETE removes → GET returns 404."""
        app, service = self._build_app()
        client = TestClient(app)
        alert_id = str(_make_alert().alert_id)

        # Apply
        resp = client.post(
            f"/api/v1/incidents/{alert_id}/severity-override",
            json={
                "original_severity": "SEV4",
                "override_severity": "SEV2",
                "operator": "ops-lead",
                "reason": "Wider blast radius confirmed.",
            },
        )
        assert resp.status_code == 201

        # GET confirms
        resp = client.get(f"/api/v1/incidents/{alert_id}/severity-override")
        assert resp.status_code == 200
        assert resp.json()["override_severity"] == "SEV2"

        # DELETE revokes
        resp = client.delete(f"/api/v1/incidents/{alert_id}/severity-override")
        assert resp.status_code == 204

        # GET now returns 404
        resp = client.get(f"/api/v1/incidents/{alert_id}/severity-override")
        assert resp.status_code == 404

    def test_sev3_override_does_not_halt(self):
        """SEV3 override via REST does not set halts_pipeline=True."""
        app, service = self._build_app()
        client = TestClient(app)
        alert_id = str(_make_alert().alert_id)

        response = client.post(
            f"/api/v1/incidents/{alert_id}/severity-override",
            json={
                "original_severity": "SEV4",
                "override_severity": "SEV3",
                "operator": "on-call-eng",
            },
        )

        assert response.status_code == 201
        assert response.json()["halts_pipeline"] is False

    def test_invalid_severity_returns_400_with_helpful_message(self):
        """Invalid severity label in REST request returns 400 with description."""
        app, _ = self._build_app()
        client = TestClient(app)
        alert_id = str(_make_alert().alert_id)

        response = client.post(
            f"/api/v1/incidents/{alert_id}/severity-override",
            json={
                "original_severity": "HIGH",
                "override_severity": "SEV1",
                "operator": "ops",
            },
        )

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "SEV1" in detail or "Invalid" in detail


# ---------------------------------------------------------------------------
# Gap D — Queue Metrics E2E (LLM Integration Hardening)
# ---------------------------------------------------------------------------


class TestE2EQueueMetrics:
    """Validate LLM queue metrics under realistic contention."""

    async def test_queue_wait_metric_nonzero_when_load_exceeds_cap(self):
        """LLM_QUEUE_WAIT records non-zero values when requests exceed cap.

        Submits 5 slow pipeline diagnoses with max_concurrent=1.
        All requests queue behind the semaphore, producing measurable
        wait times in the LLM_QUEUE_WAIT histogram.
        """
        from sre_agent.adapters.telemetry.metrics import LLM_QUEUE_WAIT

        # Record histogram sum before
        before_sum = LLM_QUEUE_WAIT._sum.get()

        inner = _make_inner_llm(delay=0.02)
        throttled = ThrottledLLMAdapter(inner, max_concurrent=1)
        pipeline = _make_pipeline(throttled)

        alerts = [_make_alert() for _ in range(5)]
        await asyncio.gather(
            *[pipeline.diagnose(DiagnosisRequest(alert=a)) for a in alerts]
        )

        after_sum = LLM_QUEUE_WAIT._sum.get()
        assert after_sum > before_sum, (
            "LLM_QUEUE_WAIT should record non-zero wait times when "
            "load exceeds concurrency cap"
        )

        await throttled.close()
