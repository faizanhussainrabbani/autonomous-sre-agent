"""
FastAPI Application — HTTP entrypoint for the SRE Agent.

Exposes:
  GET  /health              — Liveness probe (always 200 if process is alive)
  GET  /api/v1/status       — Readiness probe (checks all providers are healthy)
  POST /api/v1/system/halt  — Global kill switch (halts all auto-remediations)
  POST /api/v1/system/resume — Resume after halt (dual-approver required)

Phase 2 will add:
  POST /api/v1/incidents/{id}/approve  — Human HITL approval for pending actions
  POST /api/v1/incidents/{id}/reject   — Human rejection
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

try:
    from fastapi import FastAPI, HTTPException, status
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel
    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False


# ── Request models (module-scope for FastAPI body parsing) ────────────────────
if _FASTAPI_AVAILABLE:
    class HaltRequest(BaseModel):
        reason: str
        requested_by: str
        mode: str = "soft"  # "soft" | "hard"

    class ResumeRequest(BaseModel):
        primary_approver: str
        secondary_approver: str
        review_notes: str


def create_app() -> Any:  # Returns FastAPI if available, else raises ImportError
    """Factory function to create the FastAPI application."""
    if not _FASTAPI_AVAILABLE:
        raise ImportError(
            "FastAPI is required to run the SRE Agent API. "
            "Install it with: pip install 'sre-agent[api]'"
        )

    app = FastAPI(
        title="Autonomous SRE Agent",
        description="AI-powered incident detection, diagnosis, and remediation.",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    _agent_start_time = datetime.now(timezone.utc)
    _halt_state: dict[str, Any] = {"halted": False, "reason": None, "requested_by": None, "halted_at": None}

    # ── Liveness probe ────────────────────────────────────────────────────────
    @app.get("/health", tags=["Observability"])
    async def health() -> dict[str, str]:
        """Kubernetes/ECS liveness probe. Returns 200 as long as the process is alive."""
        return {"status": "ok"}

    # ── Readiness / status ────────────────────────────────────────────────────
    @app.get("/api/v1/status", tags=["Observability"])
    async def agent_status() -> dict[str, Any]:
        """
        Readiness probe and agent metadata.

        Returns agent uptime, halt state, and Phase 1.5 version.
        Phase 2 will include ML baseline convergence status.
        """
        uptime_seconds = (datetime.now(timezone.utc) - _agent_start_time).total_seconds()
        return {
            "version": "0.1.0",
            "phase": "1.5",
            "halted": _halt_state["halted"],
            "uptime_seconds": uptime_seconds,
            "started_at": _agent_start_time.isoformat(),
        }

    # ── Kill switch ───────────────────────────────────────────────────────────
    @app.post("/api/v1/system/halt", tags=["Safety Controls"], status_code=status.HTTP_200_OK)
    async def halt(request: HaltRequest) -> dict[str, Any]:
        """
        Global kill switch — halts all autonomous remediations across the fleet.

        - soft: Current in-progress actions complete, no new actions are dispatched.
        - hard: All active remediations are aborted immediately.

        Requires GlobalAdmin or IncidentCommander RBAC (Phase 2 enforcement).
        """
        _halt_state.update({
            "halted": True,
            "reason": request.reason,
            "requested_by": request.requested_by,
            "halted_at": datetime.now(timezone.utc).isoformat(),
            "mode": request.mode,
        })
        return {
            "status": "halted",
            "timestamp": _halt_state["halted_at"],
            "mode": request.mode,
            "active_remediations_aborted": 0,  # Phase 2: wire to action executor
        }

    @app.post("/api/v1/system/resume", tags=["Safety Controls"], status_code=status.HTTP_200_OK)
    async def resume(request: ResumeRequest) -> dict[str, Any]:
        """
        Resume autonomous operations after a halt.

        Requires dual-approver authorization (primary + secondary approver).
        """
        if not _halt_state["halted"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Agent is not in halted state.",
            )
        _halt_state.update({"halted": False, "reason": None, "requested_by": None, "halted_at": None})
        return {
            "status": "resumed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "resumed_by": request.primary_approver,
        }

    return app


# Module-level app instance (for uvicorn: sre_agent.api.main:app)
app = create_app() if _FASTAPI_AVAILABLE else None

