"""
Unit tests for the FastAPI application (api/main.py).

Validates: health endpoint, status endpoint, halt/resume kill switch,
and error handling using httpx AsyncClient.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

try:
    from httpx import ASGITransport, AsyncClient

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


@pytest.mark.unit
class TestLifespanWorkers:
    """Application lifespan worker orchestration tests."""

    @pytest.mark.asyncio
    async def test_lifespan_starts_and_stops_relay_and_retention(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Lifespan should start both workers and stop both on shutdown."""
        import anyio

        import sre_agent.adapters.bootstrap as bootstrap_module
        import sre_agent.adapters.persistence.outbox_relay as relay_module

        class _FakePool:
            def __init__(self) -> None:
                self.close_called = False

            async def close(self) -> None:
                self.close_called = True

        class _Worker:
            def __init__(self) -> None:
                self.run_started = False
                self.stop_called = False

            async def run(self) -> None:
                self.run_started = True
                while not self.stop_called:
                    await anyio.sleep(0)

            def stop(self) -> None:
                self.stop_called = True

        fake_pool = _FakePool()
        fake_relay_worker = _Worker()
        fake_retention_worker = _Worker()

        monkeypatch.setattr(
            bootstrap_module,
            "bootstrap_asyncpg_pool",
            AsyncMock(return_value=fake_pool),
        )
        monkeypatch.setattr(bootstrap_module, "bootstrap_incident_store", lambda _pool: object())
        monkeypatch.setattr(bootstrap_module, "bootstrap_outbox_store", lambda _pool: object())
        monkeypatch.setattr(bootstrap_module, "bootstrap_diagnosis_store", lambda _pool: None)
        monkeypatch.setattr(bootstrap_module, "bootstrap_reasoning_trace_store", lambda _pool: None)
        monkeypatch.setattr(bootstrap_module, "bootstrap_remediation_store", lambda _pool: None)
        monkeypatch.setattr(
            bootstrap_module,
            "bootstrap_retention_executor",
            lambda _pool, _config: fake_retention_worker,
        )
        monkeypatch.setattr(bootstrap_module, "bootstrap_event_bus", lambda _config: object())

        class _FakeOutboxRelay:
            def __init__(self, **_: object) -> None:
                pass

            async def run(self) -> None:
                await fake_relay_worker.run()

            def stop(self) -> None:
                fake_relay_worker.stop()

        monkeypatch.setattr(relay_module, "OutboxRelay", _FakeOutboxRelay)

        app = create_app()
        async with app.router.lifespan_context(app):
            with anyio.fail_after(1):
                while not (fake_relay_worker.run_started and fake_retention_worker.run_started):
                    await anyio.sleep(0.01)

        assert fake_relay_worker.stop_called is True
        assert fake_retention_worker.stop_called is True
        assert fake_pool.close_called is True
