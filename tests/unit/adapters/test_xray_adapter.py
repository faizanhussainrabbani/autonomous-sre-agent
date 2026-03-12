"""
Unit tests for X-Ray Trace Adapter.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from sre_agent.adapters.telemetry.cloudwatch.xray_adapter import XRayTraceAdapter


def _make_client(batch_result=None, summaries_result=None):
    """Create a mock X-Ray client."""
    client = MagicMock()
    client.batch_get_traces.return_value = {
        "Traces": batch_result or [],
    }
    client.get_trace_summaries.return_value = {
        "TraceSummaries": summaries_result or [],
    }
    return client


def _make_adapter(client=None):
    return XRayTraceAdapter(client or _make_client())


def _make_xray_trace(trace_id="1-abc-def", segments=None):
    """Create a minimal X-Ray trace response."""
    import json
    if segments is None:
        segments = [
            {
                "Id": "seg-1",
                "Document": json.dumps({
                    "name": "payment-handler",
                    "id": "seg-1",
                    "trace_id": trace_id,
                    "start_time": 1704067200.0,
                    "end_time": 1704067200.5,
                    "http": {"response": {"status": 200}},
                    "subsegments": [],
                }),
            }
        ]
    return {"Id": trace_id, "Duration": 0.5, "Segments": segments}


# ── get_trace() ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_trace_returns_canonical_trace():
    """get_trace() should parse an X-Ray trace into a CanonicalTrace."""
    trace = _make_xray_trace()
    client = _make_client(batch_result=[trace])
    adapter = _make_adapter(client)

    result = await adapter.get_trace("1-abc-def")
    assert result is not None
    assert result.trace_id == "1-abc-def"
    assert result.provider_source == "cloudwatch"
    assert len(result.spans) >= 1


@pytest.mark.asyncio
async def test_get_trace_not_found():
    """get_trace() returns None when trace is not found."""
    client = _make_client(batch_result=[])
    adapter = _make_adapter(client)
    result = await adapter.get_trace("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_get_trace_handles_api_error():
    """get_trace() returns None on boto3 exception."""
    from botocore.exceptions import ClientError

    client = MagicMock()
    client.batch_get_traces.side_effect = ClientError(
        error_response={"Error": {"Code": "InvalidRequestException", "Message": "bad"}},
        operation_name="BatchGetTraces",
    )
    adapter = _make_adapter(client)
    result = await adapter.get_trace("1-abc-def")
    assert result is None


# ── query_traces() ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_query_traces_uses_filter_expression():
    """query_traces() should build filter expression from parameters."""
    trace = _make_xray_trace()
    client = _make_client(
        summaries_result=[{"Id": "1-abc-def"}],
        batch_result=[trace],
    )
    adapter = _make_adapter(client)
    now = datetime.now(timezone.utc)

    results = await adapter.query_traces(
        service="payment-handler",
        start=now,
        end=now,
    )
    assert isinstance(results, list)
    client.get_trace_summaries.assert_called_once()


@pytest.mark.asyncio
async def test_query_traces_empty_summaries():
    """query_traces() returns empty list when no summaries found."""
    client = _make_client(summaries_result=[])
    adapter = _make_adapter(client)
    now = datetime.now(timezone.utc)

    results = await adapter.query_traces(service="svc", start_time=now, end_time=now)
    assert results == []


# ── _parse_segment() ─────────────────────────────────────────────────────────

def test_parse_segment_fault_status():
    """Segment with fault=True should map to 500 status."""
    import json
    adapter = _make_adapter()
    doc = {
        "name": "svc",
        "id": "seg-1",
        "trace_id": "1-abc",
        "start_time": 1704067200.0,
        "end_time": 1704067200.5,
        "fault": True,
        "cause": {"message": "OOM"},
    }
    span = adapter._parse_segment(doc, parent_span_id=None)
    assert span.status_code == 500
    assert "OOM" in str(span.error or "")


def test_parse_segment_throttle_status():
    """Segment with throttle=True should map to 429 status."""
    adapter = _make_adapter()
    doc = {
        "name": "svc",
        "id": "seg-2",
        "trace_id": "1-abc",
        "start_time": 1704067200.0,
        "end_time": 1704067200.3,
        "throttle": True,
    }
    span = adapter._parse_segment(doc, parent_span_id=None)
    assert span.status_code == 429


# ── health_check() ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_check_ok():
    adapter = _make_adapter()
    assert await adapter.health_check() is True


@pytest.mark.asyncio
async def test_health_check_fail():
    client = MagicMock()
    client.get_trace_summaries.side_effect = Exception("fail")
    adapter = _make_adapter(client)
    assert await adapter.health_check() is False
