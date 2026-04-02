"""Unit tests for diagnose router ingestion and diagnosis wiring."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sre_agent.api.rest.diagnose_router import (
    DiagnoseRequestPayload,
    IngestRequestPayload,
    ingest_document,
    trigger_diagnosis,
)
from sre_agent.domain.models.canonical import AnomalyAlert, AnomalyType, Severity
from sre_agent.ports.diagnostics import DiagnosisResult


@pytest.mark.unit
class TestDiagnoseRouterIngest:
    """Tests for POST /api/v1/diagnose/ingest behavior."""

    @pytest.mark.asyncio
    async def test_ingest_document_uses_chunked_ingestion_pipeline(self) -> None:
        pipeline = MagicMock()
        pipeline._vector_store = MagicMock()
        pipeline._embedding = MagicMock()

        payload = IngestRequestPayload(
            source="runbook/oom.md",
            content="# OOM Recovery\nsteps",
            metadata={"type": "runbook"},
        )

        with patch(
            "sre_agent.api.rest.diagnose_router.DocumentIngestionPipeline.ingest",
            new=AsyncMock(return_value=3),
        ) as ingest_mock:
            result = await ingest_document(payload, pipeline)

        ingest_mock.assert_awaited_once_with(
            content=payload.content,
            source=payload.source,
            metadata=payload.metadata,
        )
        assert result["status"] == "success"
        assert result["chunks"] == 3
        assert result["doc_id"] is None

    @pytest.mark.asyncio
    async def test_ingest_document_returns_doc_id_for_single_chunk(self) -> None:
        pipeline = MagicMock()
        pipeline._vector_store = MagicMock()
        pipeline._embedding = MagicMock()

        payload = IngestRequestPayload(
            source="runbook/single.md",
            content="single chunk content",
            metadata={},
        )

        with patch(
            "sre_agent.api.rest.diagnose_router.DocumentIngestionPipeline.ingest",
            new=AsyncMock(return_value=1),
        ):
            result = await ingest_document(payload, pipeline)

        assert result["doc_id"] == "runbook/single.md::chunk-0"


@pytest.mark.unit
class TestDiagnoseRouterDiagnose:
    """Tests for POST /api/v1/diagnose behavior."""

    @pytest.mark.asyncio
    async def test_trigger_diagnosis_maps_pipeline_result(self) -> None:
        alert = AnomalyAlert(
            service="checkout-service",
            anomaly_type=AnomalyType.MEMORY_PRESSURE,
            description="OOM kill detected",
            severity=Severity.SEV2,
        )
        payload = DiagnoseRequestPayload(alert=alert)

        pipeline = MagicMock()
        pipeline.diagnose = AsyncMock(return_value=DiagnosisResult(
            root_cause="Memory leak",
            confidence=0.82,
            severity=Severity.SEV1,
            reasoning="reasoning",
            is_novel=False,
            requires_human_approval=True,
        ))

        response = await trigger_diagnosis(payload, pipeline)

        assert response["status"] == "success"
        assert response["root_cause"] == "Memory leak"
        assert response["confidence"] == 0.82
        assert response["severity"] == "SEV1"
