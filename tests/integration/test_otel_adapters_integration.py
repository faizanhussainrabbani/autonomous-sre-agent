"""
Integration tests for OTel adapters using Testcontainers.

Spins up ephemeral Prometheus, Loki, and Jaeger containers to verify
the adapters can successfully connect to real endpoints over HTTP.

Note: Requires Docker daemon to be running.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import pytest
from datetime import datetime, timezone

# We skip all tests in this module if Docker is not available
def _is_docker_daemon_running() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        subprocess.run(["docker", "info"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False

pytestmark = pytest.mark.skipif(
    not _is_docker_daemon_running(),
    reason="Docker daemon is not running. Integration tests require Testcontainers.",
)

httpx = pytest.importorskip("httpx")
testcontainers_core_container = pytest.importorskip("testcontainers.core.container")
testcontainers_core_waiting_utils = pytest.importorskip("testcontainers.core.waiting_utils")
DockerContainer = testcontainers_core_container.DockerContainer
wait_container_is_ready = testcontainers_core_waiting_utils.wait_container_is_ready


from sre_agent.adapters.telemetry.otel.prometheus_adapter import PrometheusMetricsAdapter
from sre_agent.adapters.telemetry.otel.loki_adapter import LokiLogAdapter
from sre_agent.adapters.telemetry.otel.jaeger_adapter import JaegerTraceAdapter

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def prometheus():
    with DockerContainer("prom/prometheus:latest").with_exposed_ports(9090).with_command(
        "--config.file=/etc/prometheus/prometheus.yml"
    ) as container:
        # Prometheus health endpoint
        @wait_container_is_ready(httpx.HTTPError, httpx.RequestError, EOFError)
        def _wait():
            port = container.get_exposed_port(9090)
            host = container.get_container_host_ip()
            resp = httpx.get(f"http://{host}:{port}/-/healthy")
            resp.raise_for_status()

        _wait()
        yield container

@pytest.fixture(scope="module")
def loki():
    with DockerContainer("grafana/loki:latest").with_exposed_ports(3100) as container:
        @wait_container_is_ready(httpx.HTTPError, httpx.RequestError, EOFError)
        def _wait():
            port = container.get_exposed_port(3100)
            host = container.get_container_host_ip()
            resp = httpx.get(f"http://{host}:{port}/ready")
            resp.raise_for_status()

        _wait()
        yield container

@pytest.fixture(scope="module")
def jaeger():
    with DockerContainer("jaegertracing/all-in-one:latest").with_exposed_ports(16686).with_env(
        "COLLECTOR_ZIPKIN_HOST_PORT", ":9411"
    ) as container:
        @wait_container_is_ready(httpx.HTTPError, httpx.RequestError, EOFError)
        def _wait():
            port = container.get_exposed_port(16686)
            host = container.get_container_host_ip()
            resp = httpx.get(f"http://{host}:{port}/")
            resp.raise_for_status()

        _wait()
        yield container


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_prometheus_integration(prometheus):
    host = prometheus.get_container_host_ip()
    port = prometheus.get_exposed_port(9090)
    base_url = f"http://{host}:{port}"
    
    adapter = PrometheusMetricsAdapter(base_url)
    
    # 1. Test health check
    is_healthy = await adapter.health_check()
    assert is_healthy is True

    # 2. Test a basic instant query (e.g. up metric which prometheus scrapes of itself)
    metrics = await adapter.query_instant("prometheus", "up")
    assert metrics is None or isinstance(metrics.value, float)
    
    await adapter.close()


@pytest.mark.asyncio
async def test_loki_integration(loki):
    host = loki.get_container_host_ip()
    port = loki.get_exposed_port(3100)
    base_url = f"http://{host}:{port}"
    
    adapter = LokiLogAdapter(base_url)
    
    # 1. Test health check
    is_healthy = await adapter.health_check()
    assert is_healthy is True

    # 2. Query logs (should be empty but shouldn't error)
    now = datetime.now(timezone.utc)
    logs = await adapter.query_logs("svc", now, now)
    assert isinstance(logs, list)

    await adapter.close()


@pytest.mark.asyncio
async def test_jaeger_integration(jaeger):
    host = jaeger.get_container_host_ip()
    port = jaeger.get_exposed_port(16686)
    base_url = f"http://{host}:{port}"
    
    adapter = JaegerTraceAdapter(base_url)
    
    # 1. Test health check
    is_healthy = await adapter.health_check()
    assert is_healthy is True

    # 2. Query empty trace
    trace = await adapter.get_trace("1234")
    assert trace is None

    await adapter.close()
