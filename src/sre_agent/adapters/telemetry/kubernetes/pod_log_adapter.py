"""
Kubernetes Pod Log Adapter — direct log retrieval via Kubernetes API.

Implements the LogQuery port using ``CoreV1Api.read_namespaced_pod_log()``
from the ``kubernetes`` Python client. Provides pod log access without
depending on external log aggregation infrastructure (Grafana Loki).

All synchronous Kubernetes client calls are wrapped in
``anyio.to_thread.run_sync()`` to maintain the async-first contract
and avoid blocking the event loop.

Implements: Phase 2.9B — Kubernetes Log Fallback Adapter
Validates: AC-LF-4.1, AC-LF-4.2
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

import anyio
import structlog

from sre_agent.domain.models.canonical import (
    CanonicalLogEntry,
    ComputeMechanism,
    DataQuality,
    ServiceLabels,
)
from sre_agent.ports.telemetry import LogQuery

logger = structlog.get_logger(__name__)

# Maximum number of pods to query — bounds latency and memory.
_MAX_PODS = 5

# Severity keywords for inference from unstructured log text.
_SEVERITY_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?:\b(?:ERROR|FATAL|CRITICAL)\b|EXCEPTION)", re.IGNORECASE), "ERROR"),
    (re.compile(r"\b(WARN|WARNING)\b", re.IGNORECASE), "WARNING"),
    (re.compile(r"\b(DEBUG)\b", re.IGNORECASE), "DEBUG"),
]

# Trace ID patterns for client-side filtering.
_TRACE_ID_PATTERNS = [
    re.compile(r"trace_id=(\S+)"),
    re.compile(r"traceID=(\S+)"),
    re.compile(r'"trace_id"\s*:\s*"([^"]+)"'),
]


def _infer_severity(line: str) -> str:
    """Infer log severity from text content via keyword matching."""
    for pattern, severity in _SEVERITY_PATTERNS:
        if pattern.search(line):
            return severity
    return "INFO"


def _line_matches_trace_id(line: str, trace_id: str) -> bool:
    """Check if a log line contains the given trace ID."""
    for pattern in _TRACE_ID_PATTERNS:
        match = pattern.search(line)
        if match and match.group(1) == trace_id:
            return True
    return False


class KubernetesLogAdapter(LogQuery):
    """LogQuery implementation using the Kubernetes API for pod log retrieval.

    Retrieves logs directly from pod stdout/stderr via the Kubernetes API
    server, without depending on external log aggregation (Grafana Loki).

    Args:
        core_v1_api: Kubernetes ``CoreV1Api`` client instance.
        namespace: Default namespace for pod queries.
    """

    def __init__(
        self,
        core_v1_api: Any,
        namespace: str = "default",
    ) -> None:
        self._api = core_v1_api
        self._namespace = namespace

    async def query_logs(
        self,
        service: str,
        start_time: datetime,
        end_time: datetime,
        severity: str | None = None,
        trace_id: str | None = None,
        search_text: str | None = None,
        limit: int = 1000,
    ) -> list[CanonicalLogEntry]:
        """Query pod logs for a service by label selector.

        Lists pods matching ``app={service}`` and reads logs from up
        to 5 pods. Parses unstructured text lines into CanonicalLogEntry
        with severity inference.
        """
        since_seconds = max(1, int((end_time - start_time).total_seconds()))
        label_selector = f"app={service}" if service else None
        try:
            pods = await anyio.to_thread.run_sync(
                lambda: self._api.list_namespaced_pod(
                    namespace=self._namespace,
                    label_selector=label_selector,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "kubernetes_pod_list_failed",
                service=service,
                namespace=self._namespace,
                error=str(exc),
            )
            return []

        pod_names = [pod.metadata.name for pod in pods.items[:_MAX_PODS]]
        pod_service_names: dict[str, str] = {
            pod.metadata.name: (
                service
                or ((pod.metadata.labels or {}).get("app", "unknown-service"))
            )
            for pod in pods.items[:_MAX_PODS]
        }

        entries: list[CanonicalLogEntry] = []
        pod_logs: dict[str, str] = {}

        async def _read_pod_log(pod_name: str) -> None:
            try:
                log_text: str = await anyio.to_thread.run_sync(
                    lambda name=pod_name: self._api.read_namespaced_pod_log(
                        name=name,
                        namespace=self._namespace,
                        since_seconds=since_seconds,
                        tail_lines=limit,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "kubernetes_pod_log_read_failed",
                    pod=pod_name,
                    service=service,
                    error=str(exc),
                )
                return

            if log_text:
                pod_logs[pod_name] = log_text

        async with anyio.create_task_group() as tg:
            for pod_name in pod_names:
                tg.start_soon(_read_pod_log, pod_name)

        for pod_name in pod_names:
            log_text = pod_logs.get(pod_name)
            if not log_text:
                continue

            source_service = pod_service_names.get(pod_name, service or "unknown-service")
            now = datetime.now(UTC)
            for line in log_text.strip().splitlines():
                line = line.strip()
                if not line:
                    continue

                entry_severity = _infer_severity(line)

                # Apply severity filter if specified
                if severity and entry_severity != severity.upper():
                    continue

                # Apply text search filter if specified
                if search_text and search_text.lower() not in line.lower():
                    continue

                # Apply trace ID filter if specified
                if trace_id and not _line_matches_trace_id(line, trace_id):
                    continue

                entries.append(
                    CanonicalLogEntry(
                        timestamp=now,
                        message=line,
                        severity=entry_severity,
                        labels=ServiceLabels(
                            service=source_service,
                            namespace=self._namespace,
                            compute_mechanism=ComputeMechanism.KUBERNETES,
                            pod=pod_name,
                        ),
                        provider_source="kubernetes",
                        quality=DataQuality.LOW,
                        ingestion_timestamp=now,
                    )
                )

        return entries[:limit]

    async def query_by_trace_id(
        self,
        trace_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[CanonicalLogEntry]:
        """Retrieve log entries matching a trace ID via client-side filtering.

        Reads recent pod logs and filters for lines containing the
        trace ID in common formats: ``trace_id=``, ``traceID=``,
        ``"trace_id":``. When service is unknown, queries all pods in
        the configured namespace.
        """
        now = datetime.now(UTC)
        s = start_time or now - timedelta(hours=1)
        e = end_time or now
        # Delegate to query_logs with trace_id filter
        return await self.query_logs(
            service="",  # Empty service — list all pods
            start_time=s,
            end_time=e,
            trace_id=trace_id,
        )

    async def health_check(self) -> bool:
        """Verify Kubernetes API server connectivity.

        Calls ``list_namespace(limit=1)`` as a lightweight connectivity probe.
        """
        try:
            await anyio.to_thread.run_sync(
                lambda: self._api.list_namespace(limit=1)
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "kubernetes_health_check_failed",
                error=str(exc),
            )
            return False

    async def close(self) -> None:
        """No-op — Kubernetes client manages its own lifecycle."""
