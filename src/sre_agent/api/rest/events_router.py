"""
EventBridge Events Router — receives AWS infrastructure change events.

Provides an HTTP endpoint for EventBridge rules to deliver infrastructure
change events (Lambda deployments, ECS task state changes, IAM modifications)
that may correlate with active incidents.

Implements: Area 7 — EventBridge Integration
Validates: AC-CW-8.1 through AC-CW-8.4
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from sre_agent.domain.models.canonical import (
    CanonicalEvent,
    DataQuality,
    ServiceLabels,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/events", tags=["Events"])

# In-memory event store for correlation (Phase 2 will use EventStore port)
_recent_events: List[CanonicalEvent] = []
_MAX_EVENTS = 1000

# Supported event sources and their detail-type mappings
SUPPORTED_SOURCES: dict[str, set[str]] = {
    "aws.lambda": {
        "AWS API Call via CloudTrail",
        "Lambda Function Updated",
        "Lambda Function Configuration Change",
    },
    "aws.ecs": {
        "ECS Task State Change",
        "ECS Deployment State Change",
        "ECS Service Action",
    },
    "aws.rds": {
        "RDS DB Instance Event",
        "RDS DB Cluster Event",
    },
    "aws.iam": {
        "AWS API Call via CloudTrail",
    },
    "aws.autoscaling": {
        "EC2 Instance Launch Successful",
        "EC2 Instance Launch Unsuccessful",
        "EC2 Instance Terminate Successful",
    },
}


class AWSEventPayload(BaseModel):
    """EventBridge event payload structure."""

    version: str = "0"
    id: str = Field(default_factory=lambda: str(uuid4()))
    source: str
    detail_type: str = Field(alias="detail-type", default="")
    account: str = ""
    time: str = ""
    region: str = ""
    resources: List[str] = Field(default_factory=list)
    detail: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


@router.post("/aws", status_code=200)
async def receive_aws_event(payload: AWSEventPayload) -> Dict[str, Any]:
    """Receive an AWS EventBridge event and store for correlation.

    Accepts events from aws.lambda, aws.ecs, aws.rds, aws.iam,
    and aws.autoscaling sources.
    """
    source = payload.source

    # Validate source is supported
    if source not in SUPPORTED_SOURCES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported event source: {source}. "
            f"Supported: {list(SUPPORTED_SOURCES.keys())}",
        )

    # Parse event into canonical format
    event = _parse_event(payload)

    # Store for correlation
    _recent_events.append(event)
    if len(_recent_events) > _MAX_EVENTS:
        _recent_events.pop(0)  # FIFO eviction

    logger.info(
        "aws_event_received",
        source=source,
        detail_type=payload.detail_type,
        event_type=event.event_type,
        resource_count=len(payload.resources),
    )

    return {
        "status": "accepted",
        "event_id": str(event.metadata.get("event_id", "")),
        "event_type": event.event_type,
        "source": source,
    }


@router.get("/aws/recent", status_code=200)
async def get_recent_events(
    source: str | None = None,
    service: str | None = None,
    limit: int = 50,
) -> Dict[str, Any]:
    """Retrieve recent AWS events for correlation.

    Optional filters by source and service name.
    """
    events = _recent_events[-limit:]

    if source:
        events = [e for e in events if e.source == source]
    if service:
        events = [
            e for e in events if e.labels and e.labels.service == service
        ]

    return {
        "count": len(events),
        "events": [
            {
                "event_type": e.event_type,
                "source": e.source,
                "timestamp": e.timestamp.isoformat(),
                "metadata": e.metadata,
            }
            for e in events
        ],
    }


def get_correlated_events(
    service: str,
    window_start: datetime,
    window_end: datetime,
) -> list[CanonicalEvent]:
    """Get events correlated with a service within a time window.

    Used by the diagnostic pipeline for change correlation.
    """
    return [
        e
        for e in _recent_events
        if e.labels
        and e.labels.service == service
        and window_start <= e.timestamp <= window_end
    ]


def _parse_event(payload: AWSEventPayload) -> CanonicalEvent:
    """Parse an EventBridge payload into a CanonicalEvent."""
    # Determine event type from source and detail-type
    event_type = _classify_event(payload.source, payload.detail_type, payload.detail)

    # Extract service name from resources or detail
    service = _extract_service(payload)

    # Parse timestamp
    try:
        timestamp = datetime.fromisoformat(
            payload.time.replace("Z", "+00:00")
        ) if payload.time else datetime.now(timezone.utc)
    except (ValueError, AttributeError):
        timestamp = datetime.now(timezone.utc)

    return CanonicalEvent(
        event_type=event_type,
        source=payload.source,
        timestamp=timestamp,
        metadata={
            "event_id": payload.id,
            "account": payload.account,
            "region": payload.region,
            "resources": payload.resources,
            "detail_type": payload.detail_type,
            "detail": payload.detail,
        },
        labels=ServiceLabels(service=service) if service else None,
        quality=DataQuality.HIGH,
        provider_source="eventbridge",
    )


def _classify_event(source: str, detail_type: str, detail: dict[str, Any]) -> str:
    """Classify an EventBridge event into a canonical event type."""
    if source == "aws.lambda":
        if "Updated" in detail_type or "Configuration Change" in detail_type:
            return "lambda_deployment"
        api_name = detail.get("eventName", "")
        if "UpdateFunctionCode" in api_name:
            return "lambda_deployment"
        if "UpdateFunctionConfiguration" in api_name:
            return "lambda_config_change"
        return "lambda_api_call"

    if source == "aws.ecs":
        if "Task State Change" in detail_type:
            return "ecs_task_state_change"
        if "Deployment" in detail_type:
            return "ecs_deployment"
        return "ecs_service_action"

    if source == "aws.rds":
        return "rds_event"

    if source == "aws.iam":
        return "iam_change"

    if source == "aws.autoscaling":
        if "Launch Successful" in detail_type:
            return "asg_scale_out"
        if "Terminate" in detail_type:
            return "asg_scale_in"
        return "asg_event"

    return "unknown_aws_event"


def _extract_service(payload: AWSEventPayload) -> str:
    """Extract the affected service name from an EventBridge event."""
    # Try resources ARN first
    for arn in payload.resources:
        parts = arn.split(":")
        if len(parts) >= 7:
            resource = parts[-1]
            # Lambda: function:name or function/name
            if "function" in resource:
                return resource.split("/")[-1].split(":")[-1]
            return resource.split("/")[-1]

    # Try detail fields
    detail = payload.detail
    if "functionName" in detail:
        return detail["functionName"]
    if "group" in detail:
        group = detail["group"]
        # ECS group names are like "service:my-service" — strip the prefix
        if ":" in group:
            return group.split(":", maxsplit=1)[-1]
        return group.split("/")[-1]
    if "serviceName" in detail:
        return detail["serviceName"]

    # Try request parameters in CloudTrail events
    request_params = detail.get("requestParameters", {})
    if "functionName" in request_params:
        return request_params["functionName"]

    return ""
