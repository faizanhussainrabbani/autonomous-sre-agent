"""
Integration tests for real AWS CloudWatch Metric generation and querying using LocalStack.

Spins up an ephemeral LocalStack container to verify the CloudWatchMetricsAdapter
can successfully query actually-published metrics.

Requires:
- Docker daemon to be running.
- localstack/localstack:latest image available.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from datetime import datetime, timedelta, timezone
import pytest

# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------

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

boto3 = pytest.importorskip("boto3")
testcontainers_localstack = pytest.importorskip("testcontainers.localstack")
LocalStackContainer = testcontainers_localstack.LocalStackContainer

from sre_agent.adapters.telemetry.cloudwatch.metrics_adapter import CloudWatchMetricsAdapter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def localstack():
    """Start a LocalStack container with cloudwatch service."""
    container = (
        LocalStackContainer(image="localstack/localstack:latest")
        .with_env("SERVICES", "cloudwatch")
        .with_env("AWS_DEFAULT_REGION", "us-east-1")
    )
    with container as c:
        yield c

@pytest.fixture(scope="module")
def cloudwatch_client(localstack):
    return boto3.client(
        "cloudwatch",
        region_name="us-east-1",
        endpoint_url=localstack.get_url(),
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cloudwatch_metrics_end_to_end(cloudwatch_client):
    """
    End-to-end test publishing a metric to LocalStack CloudWatch,
    then retrieving it via the CloudWatchMetricsAdapter.
    """
    adapter = CloudWatchMetricsAdapter(cloudwatch_client)

    # 1. Health check ensures Localstack CloudWatch responds
    is_healthy = await adapter.health_check()
    assert is_healthy is True

    # 2. Publish a metric point
    service_name = "integration-test-service"
    namespace = "AWS/Lambda"
    metric_name = "Errors"
    value = 42.0
    now = datetime.now(timezone.utc)

    # Note: AWS/Lambda uses 'FunctionName' as dimension for service name in our adapter
    cloudwatch_client.put_metric_data(
        Namespace=namespace,
        MetricData=[
            {
                'MetricName': metric_name,
                'Dimensions': [
                    {
                        'Name': 'FunctionName',
                        'Value': service_name
                    },
                ],
                'Timestamp': now,
                'Value': value,
                'Unit': 'Count'
            },
        ]
    )

    # Localstack is usually instant, but let's give it a tiny sleep to be safe
    time.sleep(1)

    # 3. Query the metric via the adapter
    window_start = now - timedelta(minutes=5)
    window_end = now + timedelta(minutes=5)
    
    # query expects the canonical name for our mapped metrics
    # "lambda_errors" maps to AWS/Lambda -> Errors
    metrics_result = await adapter.query(
        service=service_name,
        metric="lambda_errors",
        start_time=window_start,
        end_time=window_end,
    )

    # 4. Verify results
    assert len(metrics_result) >= 1, "Expected to retrieve the published metric."
    
    # Expect the one relating to our mapping
    found_metric = None
    for m in metrics_result:
        if m.name == "lambda_errors" and m.labels.service == service_name:
            found_metric = m
            break
            
    assert found_metric is not None, "Did not find the canonical metric mapped back from CloudWatch."
    assert found_metric.provider_source == "cloudwatch"
    assert found_metric.value == value
