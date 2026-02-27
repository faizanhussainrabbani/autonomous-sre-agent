"""
Unit Tests — Pixie eBPF Adapter.

Tests the PixieAdapter with mocked HTTP responses.
Validates: AC-2.2.1 (syscall), AC-2.2.3 (network), AC-2.2.4 (uninstrumented)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from sre_agent.adapters.telemetry.ebpf.pixie_adapter import (
    MAX_CPU_OVERHEAD_PERCENT,
    PixieAdapter,
)
from sre_agent.domain.models.canonical import CanonicalEvent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def adapter() -> PixieAdapter:
    return PixieAdapter(
        api_url="http://localhost:9999",
        cluster_id="test-cluster",
        api_key="test-key",
    )


def mock_pxl_response(results: list[dict]) -> httpx.Response:
    """Create a mock httpx Response with PxL results."""
    return httpx.Response(
        status_code=200,
        json={"results": results},
        request=httpx.Request("POST", "http://test/exec"),
    )


# ===========================================================================
# AC-2.2.1: Syscall Activity
# ===========================================================================

class TestSyscallActivity:
    """AC-2.2.1: Capture syscall activity per pod."""

    async def test_get_syscall_activity_returns_canonical_events(self, adapter):
        """Syscall data is mapped to CanonicalEvent objects."""
        mock_results = [
            {
                "timestamp": "2026-02-25T14:00:00Z",
                "pod": "svc-a-abc123",
                "container": "app",
                "pid": "12345",
                "cmdline": "/usr/bin/python main.py",
                "cpu_ns": 50000000,
                "rss_bytes": 104857600,
                "read_bytes": 1024000,
                "write_bytes": 512000,
            },
        ]

        with patch.object(adapter._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_pxl_response(mock_results)
            now = datetime.now(timezone.utc)
            events = await adapter.get_syscall_activity(
                pod="svc-a-abc123",
                namespace="default",
                start_time=now - timedelta(minutes=5),
                end_time=now,
            )

        assert len(events) == 1
        assert isinstance(events[0], CanonicalEvent)
        assert events[0].event_type == "syscall_activity"
        assert events[0].source == "ebpf"
        assert events[0].metadata["pid"] == "12345"
        assert events[0].metadata["read_bytes"] == 1024000

    async def test_syscall_activity_empty_on_failure(self, adapter):
        """Returns empty list when Pixie API fails."""
        with patch.object(adapter._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.ConnectError("connection refused")
            events = await adapter.get_syscall_activity(
                pod="svc-a", namespace="default",
                start_time=datetime.now(timezone.utc) - timedelta(minutes=5),
                end_time=datetime.now(timezone.utc),
            )

        assert events == []


# ===========================================================================
# AC-2.2.3: Network Flows
# ===========================================================================

class TestNetworkFlows:
    """AC-2.2.3: Network flow data within service mesh."""

    async def test_get_network_flows_returns_canonical_events(self, adapter):
        """Network flows are mapped correctly."""
        mock_results = [
            {
                "timestamp": "2026-02-25T14:00:00Z",
                "source_pod": "svc-a-abc123",
                "source_service": "svc-a",
                "remote_addr": "10.0.1.5",
                "remote_port": 8080,
                "protocol": "tls",
                "bytes_sent": 2048,
                "bytes_recv": 8192,
            },
        ]

        with patch.object(adapter._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_pxl_response(mock_results)
            events = await adapter.get_network_flows(
                service="svc-a", namespace="default",
                start_time=datetime.now(timezone.utc) - timedelta(minutes=5),
                end_time=datetime.now(timezone.utc),
            )

        assert len(events) == 1
        assert events[0].event_type == "network_flow"
        assert events[0].metadata["protocol"] == "tls"
        assert events[0].metadata["bytes_sent"] == 2048


# ===========================================================================
# AC-2.2.2: CPU Overhead Check
# ===========================================================================

class TestNodeStatus:
    """AC-2.2.2: eBPF overhead SHALL NOT exceed 2% CPU."""

    async def test_node_status_within_budget(self, adapter):
        """Nodes within 2% CPU are flagged as within_budget."""
        mock_results = [
            {"node": "node-1", "kernel": "5.15.0", "cpu_pct": 1.2, "loaded": True},
        ]

        with patch.object(adapter._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_pxl_response(mock_results)
            nodes = await adapter.get_node_status()

        assert len(nodes) == 1
        assert nodes[0]["within_budget"] is True
        assert nodes[0]["cpu_overhead_percent"] == 1.2

    async def test_node_over_cpu_budget_flagged(self, adapter):
        """Nodes exceeding 2% CPU are flagged."""
        mock_results = [
            {"node": "node-2", "kernel": "5.10.0", "cpu_pct": 3.5, "loaded": True},
        ]

        with patch.object(adapter._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_pxl_response(mock_results)
            nodes = await adapter.get_node_status()

        assert nodes[0]["within_budget"] is False


# ===========================================================================
# Health Check
# ===========================================================================

class TestHealthCheck:
    """Pixie connectivity verification."""

    async def test_health_check_success(self, adapter):
        """Returns True when Pixie responds 200."""
        with patch.object(adapter._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = httpx.Response(
                200,
                request=httpx.Request("GET", "http://test/health"),
            )
            assert await adapter.health_check() is True
            assert adapter._healthy is True

    async def test_health_check_failure(self, adapter):
        """Returns False when Pixie is unreachable."""
        with patch.object(adapter._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.ConnectError("connection refused")
            assert await adapter.health_check() is False
            assert adapter._healthy is False
