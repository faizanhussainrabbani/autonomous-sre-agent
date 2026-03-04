"""
Unit tests for the FastAPI application (api/main.py).

Validates: health endpoint, status endpoint, halt/resume kill switch,
and error handling using httpx AsyncClient.
"""

from __future__ import annotations

import pytest
from unittest.mock import patch

try:
    from httpx import AsyncClient, ASGITransport
    from sre_agent.api.main import create_app
    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False


pytestmark = pytest.mark.skipif(
    not _FASTAPI_AVAILABLE,
    reason="FastAPI/httpx not installed",
)


@pytest.fixture
def app():
    """Create a fresh FastAPI app for each test."""
    return create_app()


@pytest.fixture
async def client(app):
    """Async HTTP client bound to the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.unit
class TestHealthEndpoint:
    """GET /health — Liveness probe."""

    @pytest.mark.asyncio
    async def test_health_returns_200(self, client: AsyncClient) -> None:
        """Health endpoint returns 200 with status ok."""
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


@pytest.mark.unit
class TestStatusEndpoint:
    """GET /api/v1/status — Readiness probe."""

    @pytest.mark.asyncio
    async def test_status_contains_version(self, client: AsyncClient) -> None:
        """Status response includes version."""
        resp = await client.get("/api/v1/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == "0.1.0"

    @pytest.mark.asyncio
    async def test_status_contains_phase(self, client: AsyncClient) -> None:
        """Status response includes current phase."""
        resp = await client.get("/api/v1/status")
        data = resp.json()
        assert data["phase"] == "1.5"

    @pytest.mark.asyncio
    async def test_status_not_halted_initially(self, client: AsyncClient) -> None:
        """Agent is not halted on fresh startup."""
        resp = await client.get("/api/v1/status")
        assert resp.json()["halted"] is False

    @pytest.mark.asyncio
    async def test_status_includes_uptime(self, client: AsyncClient) -> None:
        """Status includes uptime_seconds field."""
        resp = await client.get("/api/v1/status")
        assert "uptime_seconds" in resp.json()


@pytest.mark.unit
class TestHaltEndpoint:
    """POST /api/v1/system/halt — Kill switch."""

    @pytest.mark.asyncio
    async def test_halt_sets_halted_state(self, client: AsyncClient) -> None:
        """Halt sets agent into halted state."""
        resp = await client.post(
            "/api/v1/system/halt",
            json={"reason": "maintenance", "requested_by": "admin", "mode": "soft"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "halted"

    @pytest.mark.asyncio
    async def test_halt_reflects_in_status(self, client: AsyncClient) -> None:
        """After halt, status endpoint shows halted=True."""
        await client.post(
            "/api/v1/system/halt",
            json={"reason": "test", "requested_by": "admin"},
        )
        status_resp = await client.get("/api/v1/status")
        assert status_resp.json()["halted"] is True


@pytest.mark.unit
class TestResumeEndpoint:
    """POST /api/v1/system/resume — Resume operations."""

    @pytest.mark.asyncio
    async def test_resume_after_halt_succeeds(self, client: AsyncClient) -> None:
        """Resume after halt restores operations."""
        await client.post(
            "/api/v1/system/halt",
            json={"reason": "test", "requested_by": "admin"},
        )
        resp = await client.post(
            "/api/v1/system/resume",
            json={
                "primary_approver": "lead1",
                "secondary_approver": "lead2",
                "review_notes": "All clear",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "resumed"

    @pytest.mark.asyncio
    async def test_resume_without_halt_returns_409(self, client: AsyncClient) -> None:
        """Resume when not halted returns 409 Conflict."""
        resp = await client.post(
            "/api/v1/system/resume",
            json={
                "primary_approver": "lead1",
                "secondary_approver": "lead2",
                "review_notes": "N/A",
            },
        )
        assert resp.status_code == 409
