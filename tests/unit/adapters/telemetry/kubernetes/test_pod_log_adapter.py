"""
Unit tests for KubernetesLogAdapter.

Tests pod log retrieval, severity inference, pod cap enforcement,
graceful degradation, trace ID filtering, and health check.

Validates: AC-LF-4.1, AC-LF-4.2
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from sre_agent.adapters.telemetry.kubernetes.pod_log_adapter import (
    KubernetesLogAdapter,
    _infer_severity,
    _line_matches_trace_id,
)
from sre_agent.domain.models.canonical import CanonicalLogEntry, DataQuality
from sre_agent.ports.telemetry import LogQuery


def _make_pod(name: str) -> MagicMock:
    """Create a mock Kubernetes pod object."""
    pod = MagicMock()
    pod.metadata.name = name
    return pod


def _make_api(pods: list[str] | None = None, log_text: str = "") -> MagicMock:
    """Create a mock CoreV1Api."""
    api = MagicMock()
    pod_list = MagicMock()
    pod_list.items = [_make_pod(name) for name in (pods or ["pod-1"])]
    api.list_namespaced_pod.return_value = pod_list
    api.read_namespaced_pod_log.return_value = log_text
    return api


class TestKubernetesLogAdapterInterface:
    """Verify the adapter implements LogQuery port."""

    def test_is_subclass_of_log_query(self):
        assert issubclass(KubernetesLogAdapter, LogQuery)


class TestQueryLogs:
    """Tests for KubernetesLogAdapter.query_logs()."""

    @pytest.mark.asyncio
    async def test_returns_canonical_log_entries(self):
        """query_logs must return list[CanonicalLogEntry] with correct provider_source."""
        api = _make_api(
            pods=["pod-1"],
            log_text="2024-01-01 ERROR: Connection refused\nINFO: Service started",
        )
        adapter = KubernetesLogAdapter(core_v1_api=api, namespace="prod")
        now = datetime.now(timezone.utc)

        result = await adapter.query_logs(
            service="checkout-service",
            start_time=now - timedelta(hours=1),
            end_time=now,
        )

        assert len(result) == 2
        for entry in result:
            assert isinstance(entry, CanonicalLogEntry)
            assert entry.provider_source == "kubernetes"
            assert entry.quality == DataQuality.LOW
            assert entry.labels.service == "checkout-service"
            assert entry.labels.namespace == "prod"

    @pytest.mark.asyncio
    async def test_caps_at_five_pods(self):
        """At most 5 pods should be queried even when 10+ match."""
        pods = [f"pod-{i}" for i in range(10)]
        api = _make_api(pods=pods, log_text="some log line")
        adapter = KubernetesLogAdapter(core_v1_api=api)
        now = datetime.now(timezone.utc)

        await adapter.query_logs(
            service="svc",
            start_time=now - timedelta(hours=1),
            end_time=now,
        )

        # read_namespaced_pod_log should have been called at most 5 times
        assert api.read_namespaced_pod_log.call_count == 5

    @pytest.mark.asyncio
    async def test_returns_empty_on_api_error(self):
        """query_logs must return [] on Kubernetes API error — no exception."""
        api = MagicMock()
        api.list_namespaced_pod.side_effect = Exception("API unreachable")
        adapter = KubernetesLogAdapter(core_v1_api=api)
        now = datetime.now(timezone.utc)

        result = await adapter.query_logs(
            service="svc",
            start_time=now - timedelta(hours=1),
            end_time=now,
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_severity_inference_error(self):
        """Log lines with ERROR keyword should get severity=ERROR."""
        api = _make_api(
            pods=["pod-1"],
            log_text="ERROR: Database connection failed",
        )
        adapter = KubernetesLogAdapter(core_v1_api=api)
        now = datetime.now(timezone.utc)

        result = await adapter.query_logs(
            service="svc",
            start_time=now - timedelta(hours=1),
            end_time=now,
        )

        assert len(result) == 1
        assert result[0].severity == "ERROR"

    @pytest.mark.asyncio
    async def test_severity_inference_warn(self):
        """Log lines with WARN keyword should get severity=WARNING."""
        api = _make_api(pods=["pod-1"], log_text="WARN: High memory usage")
        adapter = KubernetesLogAdapter(core_v1_api=api)
        now = datetime.now(timezone.utc)

        result = await adapter.query_logs(
            service="svc",
            start_time=now - timedelta(hours=1),
            end_time=now,
        )

        assert result[0].severity == "WARNING"

    @pytest.mark.asyncio
    async def test_severity_inference_default_info(self):
        """Log lines without severity keywords should default to INFO."""
        api = _make_api(pods=["pod-1"], log_text="Service started successfully")
        adapter = KubernetesLogAdapter(core_v1_api=api)
        now = datetime.now(timezone.utc)

        result = await adapter.query_logs(
            service="svc",
            start_time=now - timedelta(hours=1),
            end_time=now,
        )

        assert result[0].severity == "INFO"

    @pytest.mark.asyncio
    async def test_returns_empty_for_zero_pods(self):
        """Service with zero matching pods should return []."""
        api = _make_api(pods=[], log_text="")
        adapter = KubernetesLogAdapter(core_v1_api=api)
        now = datetime.now(timezone.utc)

        result = await adapter.query_logs(
            service="nonexistent",
            start_time=now - timedelta(hours=1),
            end_time=now,
        )

        assert result == []


class TestQueryByTraceId:
    """Tests for trace ID filtering."""

    @pytest.mark.asyncio
    async def test_filters_by_trace_id(self):
        """query_by_trace_id filters client-side for trace ID patterns."""
        api = _make_api(
            pods=["pod-1"],
            log_text='trace_id=abc123 ERROR: timeout\nno trace here\ntraceID=abc123 INFO: started',
        )
        adapter = KubernetesLogAdapter(core_v1_api=api)

        result = await adapter.query_by_trace_id(trace_id="abc123")

        assert len(result) == 2
        for entry in result:
            assert "abc123" in entry.message


class TestHealthCheck:
    """Tests for health_check()."""

    @pytest.mark.asyncio
    async def test_returns_true_on_connectivity(self):
        """health_check returns True when API server is reachable."""
        api = MagicMock()
        api.list_namespace.return_value = MagicMock()
        adapter = KubernetesLogAdapter(core_v1_api=api)

        assert await adapter.health_check() is True

    @pytest.mark.asyncio
    async def test_returns_false_on_error(self):
        """health_check returns False when API server is unreachable."""
        api = MagicMock()
        api.list_namespace.side_effect = Exception("unreachable")
        adapter = KubernetesLogAdapter(core_v1_api=api)

        assert await adapter.health_check() is False


class TestSeverityHelpers:
    """Tests for module-level helper functions."""

    def test_infer_severity_exception(self):
        assert _infer_severity("java.lang.NullPointerException") == "ERROR"

    def test_infer_severity_warning(self):
        assert _infer_severity("WARNING: disk 80% full") == "WARNING"

    def test_infer_severity_info_default(self):
        assert _infer_severity("just a normal log line") == "INFO"

    def test_line_matches_trace_id_format_1(self):
        assert _line_matches_trace_id("trace_id=abc123 something", "abc123")

    def test_line_matches_trace_id_format_2(self):
        assert _line_matches_trace_id("traceID=xyz789 something", "xyz789")

    def test_line_matches_trace_id_format_3(self):
        assert _line_matches_trace_id('"trace_id": "def456"', "def456")

    def test_line_no_match(self):
        assert not _line_matches_trace_id("no trace here", "abc123")
