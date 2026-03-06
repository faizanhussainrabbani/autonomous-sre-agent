"""
Unit tests for the Severity Override REST router.

Tests POST / GET / DELETE endpoints, HTTP status codes, request validation,
and pipeline-halt behaviour for Sev1/2 overrides.

Uses FastAPI TestClient (HTTPX-backed) — no network I/O.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sre_agent.api.rest.severity_override_router import (
    get_override_service,
    router,
)
from sre_agent.api.severity_override import SeverityOverrideService


def _build_app() -> tuple[FastAPI, SeverityOverrideService]:
    """Create an isolated FastAPI app with a fresh service for each test."""
    app = FastAPI()
    service = SeverityOverrideService()

    # Override dependency to inject the fresh service
    app.dependency_overrides[get_override_service] = lambda: service
    app.include_router(router)
    return app, service


class TestApplyOverrideEndpoint:
    """POST /api/v1/incidents/{alert_id}/severity-override"""

    def test_apply_override_returns_201(self):
        """Valid override request returns 201 Created with the override record."""
        app, _ = _build_app()
        client = TestClient(app)
        alert_id = uuid4()

        response = client.post(
            f"/api/v1/incidents/{alert_id}/severity-override",
            json={
                "original_severity": "SEV3",
                "override_severity": "SEV1",
                "operator": "sre-lead@example.com",
                "reason": "Wider blast radius than initially assessed.",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["alert_id"] == str(alert_id)
        assert data["override_severity"] == "SEV1"
        assert data["operator"] == "sre-lead@example.com"
        assert data["halts_pipeline"] is True

    def test_apply_sev1_override_halts_pipeline(self):
        """SEV1 override sets halts_pipeline=True."""
        app, _ = _build_app()
        client = TestClient(app)
        alert_id = uuid4()

        response = client.post(
            f"/api/v1/incidents/{alert_id}/severity-override",
            json={
                "original_severity": "SEV4",
                "override_severity": "SEV1",
                "operator": "ops-lead",
            },
        )

        assert response.json()["halts_pipeline"] is True

    def test_apply_sev2_override_halts_pipeline(self):
        """SEV2 override also sets halts_pipeline=True."""
        app, _ = _build_app()
        client = TestClient(app)
        alert_id = uuid4()

        response = client.post(
            f"/api/v1/incidents/{alert_id}/severity-override",
            json={
                "original_severity": "SEV4",
                "override_severity": "SEV2",
                "operator": "ops-lead",
            },
        )

        assert response.json()["halts_pipeline"] is True

    def test_apply_sev3_override_does_not_halt(self):
        """SEV3 override keeps halts_pipeline=False."""
        app, _ = _build_app()
        client = TestClient(app)
        alert_id = uuid4()

        response = client.post(
            f"/api/v1/incidents/{alert_id}/severity-override",
            json={
                "original_severity": "SEV4",
                "override_severity": "SEV3",
                "operator": "junior-sre",
            },
        )

        assert response.json()["halts_pipeline"] is False

    def test_apply_sev4_override_does_not_halt(self):
        """SEV4 override keeps halts_pipeline=False."""
        app, _ = _build_app()
        client = TestClient(app)
        alert_id = uuid4()

        response = client.post(
            f"/api/v1/incidents/{alert_id}/severity-override",
            json={
                "original_severity": "SEV3",
                "override_severity": "SEV4",
                "operator": "oncall-eng",
            },
        )

        assert response.json()["halts_pipeline"] is False

    def test_apply_invalid_original_severity_returns_400(self):
        """Invalid severity string returns 400 Bad Request."""
        app, _ = _build_app()
        client = TestClient(app)
        alert_id = uuid4()

        response = client.post(
            f"/api/v1/incidents/{alert_id}/severity-override",
            json={
                "original_severity": "CRITICAL",
                "override_severity": "SEV1",
                "operator": "ops",
            },
        )

        assert response.status_code == 400
        assert "Invalid severity" in response.json()["detail"]

    def test_apply_invalid_override_severity_returns_400(self):
        """Invalid override severity string returns 400."""
        app, _ = _build_app()
        client = TestClient(app)
        alert_id = uuid4()

        response = client.post(
            f"/api/v1/incidents/{alert_id}/severity-override",
            json={
                "original_severity": "SEV3",
                "override_severity": "P1",
                "operator": "ops",
            },
        )

        assert response.status_code == 400

    def test_response_includes_applied_at_timestamp(self):
        """Response includes ISO 8601 applied_at timestamp."""
        app, _ = _build_app()
        client = TestClient(app)
        alert_id = uuid4()

        response = client.post(
            f"/api/v1/incidents/{alert_id}/severity-override",
            json={
                "original_severity": "SEV3",
                "override_severity": "SEV2",
                "operator": "ops",
            },
        )

        data = response.json()
        assert "applied_at" in data
        # Should be parseable as ISO 8601
        from datetime import datetime
        datetime.fromisoformat(data["applied_at"])


class TestGetOverrideEndpoint:
    """GET /api/v1/incidents/{alert_id}/severity-override"""

    def test_get_existing_override_returns_200(self):
        """GET returns the override when one exists."""
        app, service = _build_app()
        client = TestClient(app)
        alert_id = uuid4()

        from sre_agent.domain.models.canonical import Severity
        service.apply_override(
            alert_id=alert_id,
            original_severity=Severity.SEV3,
            override_severity=Severity.SEV1,
            operator="ops-lead",
            reason="Critical impact",
        )

        response = client.get(f"/api/v1/incidents/{alert_id}/severity-override")

        assert response.status_code == 200
        data = response.json()
        assert data["override_severity"] == "SEV1"
        assert data["operator"] == "ops-lead"

    def test_get_nonexistent_override_returns_404(self):
        """GET returns 404 when no override exists for the alert."""
        app, _ = _build_app()
        client = TestClient(app)

        response = client.get(f"/api/v1/incidents/{uuid4()}/severity-override")

        assert response.status_code == 404
        assert "No severity override found" in response.json()["detail"]


class TestRevokeOverrideEndpoint:
    """DELETE /api/v1/incidents/{alert_id}/severity-override"""

    def test_revoke_existing_override_returns_204(self):
        """DELETE returns 204 No Content and removes the override."""
        app, service = _build_app()
        client = TestClient(app)
        alert_id = uuid4()

        from sre_agent.domain.models.canonical import Severity
        service.apply_override(
            alert_id=alert_id,
            original_severity=Severity.SEV4,
            override_severity=Severity.SEV1,
            operator="ops",
        )

        response = client.delete(f"/api/v1/incidents/{alert_id}/severity-override")

        assert response.status_code == 204
        assert not service.has_active_override(alert_id)

    def test_revoke_nonexistent_override_returns_404(self):
        """DELETE returns 404 when no override exists."""
        app, _ = _build_app()
        client = TestClient(app)

        response = client.delete(f"/api/v1/incidents/{uuid4()}/severity-override")

        assert response.status_code == 404

    def test_revoke_then_reapply_succeeds(self):
        """Override can be re-applied after revocation."""
        app, service = _build_app()
        client = TestClient(app)
        alert_id = uuid4()

        # Apply
        client.post(
            f"/api/v1/incidents/{alert_id}/severity-override",
            json={
                "original_severity": "SEV3",
                "override_severity": "SEV1",
                "operator": "ops",
            },
        )

        # Revoke
        client.delete(f"/api/v1/incidents/{alert_id}/severity-override")
        assert not service.has_active_override(alert_id)

        # Re-apply with different severity
        response = client.post(
            f"/api/v1/incidents/{alert_id}/severity-override",
            json={
                "original_severity": "SEV3",
                "override_severity": "SEV2",
                "operator": "second-ops",
            },
        )
        assert response.status_code == 201
        assert service.has_active_override(alert_id)
