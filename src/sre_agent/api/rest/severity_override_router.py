"""
Severity Override REST Router — FastAPI HTTP endpoints for human severity overrides.

Implements Task 9.4: "Implement human severity override API with real-time
reclassification", exposing a production-ready REST interface for operators
to override auto-classified severities and halt in-progress autonomous actions.

Endpoints:
  POST   /api/v1/incidents/{alert_id}/severity-override  — Apply override
  GET    /api/v1/incidents/{alert_id}/severity-override  — Get current override
  DELETE /api/v1/incidents/{alert_id}/severity-override  — Revoke override

Engineering Standards §6.1 (REST API Conventions):
  - Versioned URL: /api/v1/...
  - Structured JSON envelope
  - Proper HTTP status codes (201, 204, 400, 404)

Phase 2: Intelligence Layer — Gap C closure
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from sre_agent.api.severity_override import SeverityOverride, SeverityOverrideService
from sre_agent.domain.models.canonical import Severity

# ---------------------------------------------------------------------------
# Module-level singleton service
# Replaced during testing via the override_service dependency.
# ---------------------------------------------------------------------------
_service: SeverityOverrideService = SeverityOverrideService()


def get_override_service() -> SeverityOverrideService:
    """FastAPI dependency — returns the active SeverityOverrideService."""
    return _service


router = APIRouter(
    prefix="/api/v1/incidents",
    tags=["Severity Override"],
)


# ---------------------------------------------------------------------------
# Request / response schemas (Pydantic v2)
# ---------------------------------------------------------------------------


class SeverityOverrideRequest(BaseModel):
    """Payload for applying or updating a severity override."""

    original_severity: str
    override_severity: str
    operator: str
    reason: str = ""


class SeverityOverrideResponse(BaseModel):
    """JSON representation of a SeverityOverride record."""

    alert_id: str
    original_severity: str
    override_severity: str
    operator: str
    reason: str
    halts_pipeline: bool
    applied_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_severity(value: str) -> Severity:
    """Convert a string like 'SEV1' to the Severity enum.

    Raises:
        HTTPException: 400 if the value is not a valid severity name.
    """
    try:
        return Severity[value.upper()]
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid severity '{value}'. Expected one of: SEV1, SEV2, SEV3, SEV4.",
        )


def _to_response(alert_id: str, override: SeverityOverride) -> SeverityOverrideResponse:
    return SeverityOverrideResponse(
        alert_id=alert_id,
        original_severity=override.original_severity.name,
        override_severity=override.override_severity.name,
        operator=override.operator,
        reason=override.reason,
        halts_pipeline=override.halts_pipeline,
        applied_at=override.applied_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/{alert_id}/severity-override",
    status_code=status.HTTP_201_CREATED,
    summary="Apply a human severity override",
    description=(
        "Override the auto-classified severity for an alert. "
        "Sev 1 and Sev 2 overrides set `halts_pipeline=true`, blocking "
        "all autonomous remediation actions for the incident."
    ),
)
async def apply_severity_override(
    alert_id: UUID,
    body: SeverityOverrideRequest,
    service: SeverityOverrideService = Depends(get_override_service),
) -> SeverityOverrideResponse:
    """Apply a human severity override with real-time reclassification."""
    original = _parse_severity(body.original_severity)
    override_sev = _parse_severity(body.override_severity)

    result = service.apply_override(
        alert_id=alert_id,
        original_severity=original,
        override_severity=override_sev,
        operator=body.operator,
        reason=body.reason,
    )
    return _to_response(str(alert_id), result)


@router.get(
    "/{alert_id}/severity-override",
    summary="Retrieve the current severity override",
)
async def get_severity_override(
    alert_id: UUID,
    service: SeverityOverrideService = Depends(get_override_service),
) -> SeverityOverrideResponse:
    """Fetch the active severity override for an alert."""
    override = service.get_override(alert_id)
    if override is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No severity override found for alert {alert_id}.",
        )
    return _to_response(str(alert_id), override)


@router.delete(
    "/{alert_id}/severity-override",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a severity override",
    description=(
        "Remove the active severity override, restoring auto-classified severity. "
        "Pipeline halt is lifted; autonomous remediation may resume."
    ),
)
async def revoke_severity_override(
    alert_id: UUID,
    service: SeverityOverrideService = Depends(get_override_service),
) -> None:
    """Revoke an existing severity override."""
    removed = service.revoke_override(alert_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active override found for alert {alert_id}.",
        )
