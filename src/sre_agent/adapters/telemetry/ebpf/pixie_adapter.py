"""
Pixie eBPF Adapter — queries Pixie for kernel-level telemetry.

Implements the eBPFQuery port using Pixie's PxL (Pixie Language) scripts
via the Pixie API. Pixie runs as a DaemonSet on every Kubernetes node and
captures syscall activity, network flows, and process behavior via eBPF.

Implements: Task 1.3 — eBPF programs for kernel-level telemetry
Validates: AC-2.2.1 (syscall capture), AC-2.2.3 (network flows),
           AC-2.2.4 (uninstrumented services)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
import structlog

from sre_agent.domain.models.canonical import (
    CanonicalEvent,
    DataQuality,
    ServiceLabels,
)
from sre_agent.ports.telemetry import eBPFQuery

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# PxL Scripts — Pixie query language scripts for each data type
# ---------------------------------------------------------------------------

PXL_SYSCALL_ACTIVITY = """
import px

# AC-2.2.1: Syscall activity per pod
df = px.DataFrame(table='process_stats', start_time=__start_time__)
df = df[df.ctx['pod'] == '__pod__']
df = df[df.ctx['namespace'] == '__namespace__']
df.timestamp = df.time_
df.pod = df.ctx['pod']
df.container = df.ctx['container_name']
df.pid = df.upid
df.cmdline = df.cmd
df.cpu_ns = df.cpu_utime_ns + df.cpu_ktime_ns
df.rss_bytes = df.rss_bytes
df.read_bytes = df.read_bytes
df.write_bytes = df.write_bytes
px.display(df[['timestamp', 'pod', 'container', 'pid', 'cmdline',
               'cpu_ns', 'rss_bytes', 'read_bytes', 'write_bytes']])
"""

PXL_NETWORK_FLOWS = """
import px

# AC-2.2.3: Network flow data including encrypted service mesh traffic
df = px.DataFrame(table='conn_stats', start_time=__start_time__)
df = df[df.ctx['namespace'] == '__namespace__']
df.timestamp = df.time_
df.source_pod = df.ctx['pod']
df.source_service = df.ctx['service']
df.remote_addr = df.remote_addr
df.remote_port = df.remote_port
df.protocol = px.select(df.is_ssl, 'tls', 'tcp')
df.bytes_sent = df.bytes_sent
df.bytes_recv = df.bytes_recv
df.conn_open = df.conn_open
df.conn_close = df.conn_close
px.display(df[['timestamp', 'source_pod', 'source_service', 'remote_addr',
               'remote_port', 'protocol', 'bytes_sent', 'bytes_recv',
               'conn_open', 'conn_close']])
"""

PXL_PROCESS_ACTIVITY = """
import px

df = px.DataFrame(table='exec_snoop', start_time=__start_time__)
df = df[df.ctx['pod'] == '__pod__']
df = df[df.ctx['namespace'] == '__namespace__']
df.timestamp = df.time_
df.pod = df.ctx['pod']
df.container = df.ctx['container_name']
df.pid = df.pid
df.filename = df.filename
df.args = df.args
df.retval = df.retval
px.display(df[['timestamp', 'pod', 'container', 'pid',
               'filename', 'args', 'retval']])
"""

PXL_NODE_STATUS = """
import px

df = px.DataFrame(table='ebpf_stats')
df.node = df.ctx['node']
df.kernel = df.ctx['kernel_version']
df.cpu_pct = df.overhead_pct
df.loaded = df.programs_loaded
px.display(df[['node', 'kernel', 'cpu_pct', 'loaded']])
"""

# Maximum acceptable CPU overhead per AC-2.2.2
MAX_CPU_OVERHEAD_PERCENT = 2.0


class PixieAdapter(eBPFQuery):
    """Queries Pixie API for eBPF kernel-level telemetry.

    Pixie deploys as a DaemonSet (Vizier) on every node. This adapter
    communicates with the Pixie Cloud API or local Vizier to run PxL
    scripts and return results as CanonicalEvent objects.

    Architecture:
        SRE Agent → PixieAdapter → Pixie Cloud/Vizier API → eBPF programs → kernel
    """

    def __init__(
        self,
        api_url: str = "https://work.withpixie.ai",
        cluster_id: str = "",
        api_key: str = "",
        timeout: float = 30.0,
    ) -> None:
        self._api_url = api_url.rstrip("/")
        self._cluster_id = cluster_id
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=self._api_url,
            timeout=timeout,
            headers={
                "Content-Type": "application/json",
                **({"px-api-key": api_key} if api_key else {}),
            },
        )
        self._healthy = False

    async def get_syscall_activity(
        self,
        pod: str,
        namespace: str,
        start_time: datetime,
        end_time: datetime,
        syscall_types: list[str] | None = None,
    ) -> list[CanonicalEvent]:
        """AC-2.2.1: Capture syscall activity per pod."""
        script = PXL_SYSCALL_ACTIVITY.replace(
            "__pod__", pod
        ).replace(
            "__namespace__", namespace
        ).replace(
            "__start_time__", f"'-{int((end_time - start_time).total_seconds())}s'"
        )

        results = await self._execute_pxl(script)
        if not results:
            return []

        events: list[CanonicalEvent] = []
        for row in results:
            events.append(CanonicalEvent(
                event_type="syscall_activity",
                source="ebpf",
                timestamp=self._parse_timestamp(row.get("timestamp", "")),
                metadata={
                    "pod": row.get("pod", pod),
                    "container": row.get("container", ""),
                    "pid": row.get("pid", ""),
                    "cmdline": row.get("cmdline", ""),
                    "cpu_ns": row.get("cpu_ns", 0),
                    "rss_bytes": row.get("rss_bytes", 0),
                    "read_bytes": row.get("read_bytes", 0),
                    "write_bytes": row.get("write_bytes", 0),
                },
                labels=ServiceLabels(service=pod, namespace=namespace),
                quality=DataQuality.HIGH,
                provider_source="pixie",
            ))

        logger.info(
            "ebpf_syscall_activity_fetched",
            pod=pod,
            namespace=namespace,
            count=len(events),
        )
        return events

    async def get_network_flows(
        self,
        service: str,
        namespace: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[CanonicalEvent]:
        """AC-2.2.3: Network flow data within encrypted service mesh."""
        script = PXL_NETWORK_FLOWS.replace(
            "__namespace__", namespace
        ).replace(
            "__start_time__", f"'-{int((end_time - start_time).total_seconds())}s'"
        )

        results = await self._execute_pxl(script)
        if not results:
            return []

        events: list[CanonicalEvent] = []
        for row in results:
            events.append(CanonicalEvent(
                event_type="network_flow",
                source="ebpf",
                timestamp=self._parse_timestamp(row.get("timestamp", "")),
                metadata={
                    "source_pod": row.get("source_pod", ""),
                    "source_service": row.get("source_service", service),
                    "remote_addr": row.get("remote_addr", ""),
                    "remote_port": row.get("remote_port", 0),
                    "protocol": row.get("protocol", "tcp"),
                    "bytes_sent": row.get("bytes_sent", 0),
                    "bytes_recv": row.get("bytes_recv", 0),
                },
                labels=ServiceLabels(service=service, namespace=namespace),
                quality=DataQuality.HIGH,
                provider_source="pixie",
            ))

        logger.info(
            "ebpf_network_flows_fetched",
            service=service,
            namespace=namespace,
            count=len(events),
        )
        return events

    async def get_process_activity(
        self,
        pod: str,
        namespace: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[CanonicalEvent]:
        """Capture process starts, exits, and execution."""
        script = PXL_PROCESS_ACTIVITY.replace(
            "__pod__", pod
        ).replace(
            "__namespace__", namespace
        ).replace(
            "__start_time__", f"'-{int((end_time - start_time).total_seconds())}s'"
        )

        results = await self._execute_pxl(script)
        if not results:
            return []

        events: list[CanonicalEvent] = []
        for row in results:
            events.append(CanonicalEvent(
                event_type="process_exec",
                source="ebpf",
                timestamp=self._parse_timestamp(row.get("timestamp", "")),
                metadata={
                    "pod": row.get("pod", pod),
                    "container": row.get("container", ""),
                    "pid": row.get("pid", ""),
                    "filename": row.get("filename", ""),
                    "args": row.get("args", ""),
                    "retval": row.get("retval", 0),
                },
                labels=ServiceLabels(service=pod, namespace=namespace),
                quality=DataQuality.HIGH,
                provider_source="pixie",
            ))

        return events

    async def health_check(self) -> bool:
        """Check if Pixie Vizier is reachable and collecting data."""
        try:
            response = await self._client.get(
                f"/api/v1/clusters/{self._cluster_id}/health"
            )
            self._healthy = response.status_code == 200
            return self._healthy
        except httpx.HTTPError as exc:
            logger.warning("pixie_health_check_failed", error=str(exc))
            self._healthy = False
            return False

    async def get_node_status(self) -> list[dict[str, Any]]:
        """Get eBPF program status per node (AC-2.2.2 overhead check)."""
        results = await self._execute_pxl(PXL_NODE_STATUS)
        if not results:
            return []

        nodes = []
        for row in results:
            cpu_overhead = float(row.get("cpu_pct", 0))
            nodes.append({
                "node": row.get("node", "unknown"),
                "kernel_version": row.get("kernel", "unknown"),
                "ebpf_loaded": bool(row.get("loaded", False)),
                "cpu_overhead_percent": cpu_overhead,
                "within_budget": cpu_overhead <= MAX_CPU_OVERHEAD_PERCENT,
            })

            if cpu_overhead > MAX_CPU_OVERHEAD_PERCENT:
                logger.warning(
                    "ebpf_cpu_overhead_exceeded",
                    node=row.get("node"),
                    cpu_pct=cpu_overhead,
                    limit=MAX_CPU_OVERHEAD_PERCENT,
                )

        return nodes

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    async def _execute_pxl(self, script: str) -> list[dict[str, Any]]:
        """Execute a PxL script via the Pixie API.

        Pixie API endpoint: POST /api/v1/clusters/{cluster_id}/exec
        Body: { "pxl_script": "..." }
        """
        try:
            response = await self._client.post(
                f"/api/v1/clusters/{self._cluster_id}/exec",
                json={"pxl_script": script},
            )
            response.raise_for_status()
            data = response.json()
            return data.get("results", [])
        except httpx.HTTPStatusError as exc:
            logger.error(
                "pixie_pxl_execution_failed",
                status=exc.response.status_code,
                error=str(exc),
            )
            return []
        except httpx.HTTPError as exc:
            logger.error("pixie_connection_failed", error=str(exc))
            return []

    @staticmethod
    def _parse_timestamp(ts_str: str) -> datetime:
        """Parse a Pixie timestamp string to datetime."""
        try:
            if isinstance(ts_str, (int, float)):
                return datetime.fromtimestamp(ts_str / 1e9, tz=timezone.utc)
            return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return datetime.now(timezone.utc)
