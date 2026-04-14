"""PostgreSQL diagnosis result store adapter.

Implements DiagnosisStorePort using the ``diagnosis_results`` table from
migration 001.

Each successful RAG diagnostic pipeline run persists a record here, linked
to the parent incident via ``incident_id``.  Multiple diagnoses per incident
are supported (re-diagnosis after new evidence, for example).

Implements: DiagnosisStorePort (src/sre_agent/ports/persistence.py)
Phase 4.0 — Persistence Architecture Reconciliation
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import structlog

from sre_agent.ports.persistence import DiagnosisResultRecord, DiagnosisStorePort

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# SQL statements
# ---------------------------------------------------------------------------

_INSERT_DIAGNOSIS = """
INSERT INTO diagnosis_results
    (diagnosis_id, incident_id, diagnosis_summary, confidence_score,
     evidence_refs, generated_at, model_name)
VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7)
"""

_SELECT_BY_INCIDENT = """
SELECT diagnosis_id, incident_id, diagnosis_summary, confidence_score,
       evidence_refs, generated_at, model_name
FROM diagnosis_results
WHERE incident_id = $1
ORDER BY generated_at DESC
"""

_SELECT_BY_ID = """
SELECT diagnosis_id, incident_id, diagnosis_summary, confidence_score,
       evidence_refs, generated_at, model_name
FROM diagnosis_results
WHERE diagnosis_id = $1
"""


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class PostgresDiagnosisStore(DiagnosisStorePort):
    """PostgreSQL-backed diagnosis result store.

    Requires an asyncpg connection pool injected at construction time.
    """

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def save_diagnosis(self, record: DiagnosisResultRecord) -> None:
        """Persist a diagnosis result row."""
        evidence_str = json.dumps(record.evidence_refs)

        async with self._pool.acquire() as conn:
            await conn.execute(
                _INSERT_DIAGNOSIS,
                record.diagnosis_id,
                record.incident_id,
                record.diagnosis_summary,
                record.confidence_score,
                evidence_str,
                record.generated_at,
                record.model_name,
            )

        logger.info(
            "diagnosis_store.saved",
            diagnosis_id=str(record.diagnosis_id),
            incident_id=str(record.incident_id),
        )

    async def get_by_incident(
        self,
        incident_id: UUID,
    ) -> list[DiagnosisResultRecord]:
        """Retrieve all diagnoses for an incident, newest first."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(_SELECT_BY_INCIDENT, incident_id)

        return [self._row_to_record(row) for row in rows]

    async def get_by_id(self, diagnosis_id: UUID) -> DiagnosisResultRecord | None:
        """Retrieve a single diagnosis by ID."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(_SELECT_BY_ID, diagnosis_id)

        if row is None:
            return None
        return self._row_to_record(row)

    @staticmethod
    def _row_to_record(row: Any) -> DiagnosisResultRecord:
        evidence = row["evidence_refs"]
        if isinstance(evidence, str):
            evidence = json.loads(evidence)
        elif not isinstance(evidence, list):
            evidence = list(evidence) if evidence else []

        return DiagnosisResultRecord(
            diagnosis_id=row["diagnosis_id"],
            incident_id=row["incident_id"],
            diagnosis_summary=row["diagnosis_summary"],
            confidence_score=float(row["confidence_score"]),
            evidence_refs=evidence,
            generated_at=row["generated_at"],
            model_name=row["model_name"],
        )
