"""
Unit tests for EventBridge Events Router.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sre_agent.api.rest.events_router import (
    SUPPORTED_SOURCES,
    _classify_event,
    _extract_service,
    _parse_event,
    _recent_events,
    router,
    AWSEventPayload,
)


@pytest.fixture(autouse=True)
def clear_event_store():
    """Clear the in-memory event store before each test."""
    _recent_events.clear()
    yield
    _recent_events.clear()


@pytest.fixture
def client():
    """Create a test client with just the events router."""
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# ── SUPPORTED_SOURCES ─────────────────────────────────────────────────────────

def test_supported_sources_includes_lambda():
    assert "aws.lambda" in SUPPORTED_SOURCES


def test_supported_sources_includes_ecs():
    assert "aws.ecs" in SUPPORTED_SOURCES


def test_supported_sources_includes_rds():
    assert "aws.rds" in SUPPORTED_SOURCES


def test_supported_sources_includes_iam():
    assert "aws.iam" in SUPPORTED_SOURCES


def test_supported_sources_includes_autoscaling():
    assert "aws.autoscaling" in SUPPORTED_SOURCES


# ── POST /api/v1/events/aws ──────────────────────────────────────────────────

def test_receive_lambda_event(client):
    resp = client.post("/api/v1/events/aws", json={
        "source": "aws.lambda",
        "detail-type": "Lambda Function Updated",
        "account": "123456789012",
        "time": "2024-01-01T00:00:00Z",
        "region": "us-east-1",
        "resources": ["arn:aws:lambda:us-east-1:123:function:payment-handler"],
        "detail": {},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "accepted"
    assert data["event_type"] == "lambda_deployment"
    assert data["source"] == "aws.lambda"


def test_receive_ecs_task_event(client):
    resp = client.post("/api/v1/events/aws", json={
        "source": "aws.ecs",
        "detail-type": "ECS Task State Change",
        "detail": {"group": "service:checkout-service"},
    })
    assert resp.status_code == 200
    assert resp.json()["event_type"] == "ecs_task_state_change"


def test_receive_iam_event(client):
    resp = client.post("/api/v1/events/aws", json={
        "source": "aws.iam",
        "detail-type": "AWS API Call via CloudTrail",
        "detail": {"eventName": "PutRolePolicy"},
    })
    assert resp.status_code == 200
    assert resp.json()["event_type"] == "iam_change"


def test_reject_unsupported_source(client):
    resp = client.post("/api/v1/events/aws", json={
        "source": "aws.unknown",
        "detail-type": "SomeEvent",
        "detail": {},
    })
    assert resp.status_code == 422


def test_event_stored_in_memory(client):
    client.post("/api/v1/events/aws", json={
        "source": "aws.lambda",
        "detail-type": "Lambda Function Updated",
        "resources": ["arn:aws:lambda:us-east-1:123:function:payment-handler"],
        "detail": {},
    })
    assert len(_recent_events) == 1
    assert _recent_events[0].event_type == "lambda_deployment"
    assert _recent_events[0].provider_source == "eventbridge"


# ── GET /api/v1/events/aws/recent ────────────────────────────────────────────

def test_get_recent_events_empty(client):
    resp = client.get("/api/v1/events/aws/recent")
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


def test_get_recent_events_with_data(client):
    # Post an event first
    client.post("/api/v1/events/aws", json={
        "source": "aws.lambda",
        "detail-type": "Lambda Function Updated",
        "resources": ["arn:aws:lambda:us-east-1:123:function:payment-handler"],
        "detail": {},
    })
    resp = client.get("/api/v1/events/aws/recent")
    assert resp.json()["count"] == 1


def test_get_recent_events_filter_by_source(client):
    client.post("/api/v1/events/aws", json={
        "source": "aws.lambda",
        "detail-type": "Lambda Function Updated",
        "detail": {},
    })
    client.post("/api/v1/events/aws", json={
        "source": "aws.ecs",
        "detail-type": "ECS Task State Change",
        "detail": {},
    })
    resp = client.get("/api/v1/events/aws/recent?source=aws.lambda")
    assert resp.json()["count"] == 1


# ── _classify_event() ────────────────────────────────────────────────────────

def test_classify_lambda_deployment():
    assert _classify_event("aws.lambda", "Lambda Function Updated", {}) == "lambda_deployment"


def test_classify_lambda_code_update():
    assert _classify_event(
        "aws.lambda",
        "AWS API Call via CloudTrail",
        {"eventName": "UpdateFunctionCode20150331v2"},
    ) == "lambda_deployment"


def test_classify_lambda_config_change():
    assert _classify_event(
        "aws.lambda",
        "AWS API Call via CloudTrail",
        {"eventName": "UpdateFunctionConfiguration20150331v2"},
    ) == "lambda_config_change"


def test_classify_ecs_task_state():
    assert _classify_event("aws.ecs", "ECS Task State Change", {}) == "ecs_task_state_change"


def test_classify_ecs_deployment():
    assert _classify_event("aws.ecs", "ECS Deployment State Change", {}) == "ecs_deployment"


def test_classify_rds():
    assert _classify_event("aws.rds", "RDS DB Instance Event", {}) == "rds_event"


def test_classify_asg_scale_out():
    assert _classify_event(
        "aws.autoscaling",
        "EC2 Instance Launch Successful",
        {},
    ) == "asg_scale_out"


def test_classify_asg_scale_in():
    assert _classify_event(
        "aws.autoscaling",
        "EC2 Instance Terminate Successful",
        {},
    ) == "asg_scale_in"


# ── _extract_service() ───────────────────────────────────────────────────────

def test_extract_service_from_lambda_arn():
    payload = AWSEventPayload(
        source="aws.lambda",
        resources=["arn:aws:lambda:us-east-1:123:function:payment-handler"],
        detail={},
    )
    assert _extract_service(payload) == "payment-handler"


def test_extract_service_from_detail():
    payload = AWSEventPayload(
        source="aws.lambda",
        resources=[],
        detail={"functionName": "payment-handler"},
    )
    assert _extract_service(payload) == "payment-handler"


def test_extract_service_from_ecs_group():
    payload = AWSEventPayload(
        source="aws.ecs",
        resources=[],
        detail={"group": "service:checkout-service"},
    )
    assert _extract_service(payload) == "checkout-service"


def test_extract_service_empty():
    payload = AWSEventPayload(
        source="aws.iam",
        resources=[],
        detail={},
    )
    assert _extract_service(payload) == ""
