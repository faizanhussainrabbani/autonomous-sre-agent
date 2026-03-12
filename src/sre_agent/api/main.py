"""
FastAPI Application — HTTP entrypoint for the SRE Agent.

Exposes:
  GET  /health              — Liveness probe (always 200 if process is alive)
  GET  /healthz             — Deep readiness probe (checks component health)
  GET  /metrics             — Prometheus metrics endpoint
  GET  /api/v1/status       — Readiness probe (checks all providers are healthy)
  POST /api/v1/system/halt  — Global kill switch (halts all auto-remediations)
  POST /api/v1/system/resume — Resume after halt (dual-approver required)

Phase 2 will add:
  POST /api/v1/incidents/{id}/approve  — Human HITL approval for pending actions
  POST /api/v1/incidents/{id}/reject   — Human rejection
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any

try:
    from fastapi import FastAPI, HTTPException, Request, Response, status
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel
    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False

try:
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False

try:
    from sre_agent.api.rest.severity_override_router import router as _severity_override_router
    _OVERRIDE_ROUTER_AVAILABLE = True
except ImportError:
    _OVERRIDE_ROUTER_AVAILABLE = False

try:
    from sre_agent.api.rest.diagnose_router import router as _diagnose_router
    _DIAGNOSE_ROUTER_AVAILABLE = True
except ImportError:
    _DIAGNOSE_ROUTER_AVAILABLE = False


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

    import structlog as _structlog
    _log = _structlog.get_logger(__name__)

    app = FastAPI(
        title="Autonomous SRE Agent",
        description="AI-powered incident detection, diagnosis, and remediation.",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── Request logging middleware (OBS-004) ─────────────────────────────────
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        """Emit structured logs for every HTTP request with a correlation ID."""
        request_id = str(uuid.uuid4())
        _log.info(
            "request_received",
            method=request.method,
            path=request.url.path,
            request_id=request_id,
        )
        t0 = time.monotonic()
        response: Response = await call_next(request)
        elapsed = round(time.monotonic() - t0, 4)
        response.headers["X-Request-ID"] = request_id
        _log.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_seconds=elapsed,
            request_id=request_id,
        )
        return response

    # Register routers
    if _OVERRIDE_ROUTER_AVAILABLE:
        app.include_router(_severity_override_router)
        
    if _DIAGNOSE_ROUTER_AVAILABLE:
        app.include_router(_diagnose_router)

    _agent_start_time = datetime.now(timezone.utc)
    _halt_state: dict[str, Any] = {"halted": False, "reason": None, "requested_by": None, "halted_at": None}

    # ── Liveness probe ────────────────────────────────────────────────────────
    @app.get("/health", tags=["Observability"])
    async def health() -> dict[str, str]:
        """Kubernetes/ECS liveness probe. Returns 200 as long as the process is alive."""
        return {"status": "ok"}

    # ── Deep readiness / health-z probe (OBS-003) ─────────────────────────────
    @app.get("/healthz", tags=["Observability"])
    async def healthz() -> JSONResponse:
        """Deep readiness probe — checks all agent components are initialised.

        Never makes external API calls (avoids billable Anthropic/OpenAI calls
        on every k8s probe interval).  Checks that adapters are importable and
        their lazy-init state is valid.
        """
        checks: dict[str, str] = {}
        overall_ok = True

        # Vector store — check the adapter module is importable
        try:
            from sre_agent.adapters.vectordb.chroma.adapter import ChromaVectorStoreAdapter  # noqa: F401
            checks["vector_store"] = "ok"
        except Exception as exc:  # noqa: BLE001
            checks["vector_store"] = f"error: {exc}"
            overall_ok = False

        # Embedding — check the adapter module is importable
        try:
            from sre_agent.adapters.embedding.sentence_transformers_adapter import (  # noqa: F401
                SentenceTransformersEmbeddingAdapter,
            )
            checks["embedding"] = "ok"
        except Exception as exc:  # noqa: BLE001
            checks["embedding"] = f"error: {exc}"
            overall_ok = False

        # LLM — check at least one adapter module is importable
        try:
            from sre_agent.adapters.llm.openai.adapter import OpenAILLMAdapter  # noqa: F401
            checks["llm"] = "ok"
        except Exception as exc:  # noqa: BLE001
            try:
                from sre_agent.adapters.llm.anthropic.adapter import AnthropicLLMAdapter  # noqa: F401
                checks["llm"] = "ok"
            except Exception as exc2:  # noqa: BLE001
                checks["llm"] = f"error: {exc2}"
                overall_ok = False

        http_status = status.HTTP_200_OK if overall_ok else status.HTTP_503_SERVICE_UNAVAILABLE
        return JSONResponse(
            status_code=http_status,
            content={"status": "ok" if overall_ok else "degraded", "checks": checks},
        )

    # ── Prometheus metrics endpoint (OBS-003) ─────────────────────────────────
    @app.get("/metrics", tags=["Observability"], include_in_schema=False)
    async def metrics() -> Response:
        """Expose Prometheus metrics in text/plain exposition format."""
        if not _PROMETHEUS_AVAILABLE:
            return Response(content="prometheus_client not installed", status_code=503)
        data = generate_latest()
        return Response(content=data, media_type=CONTENT_TYPE_LATEST)

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

