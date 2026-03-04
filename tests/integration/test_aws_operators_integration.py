"""
Integration tests for AWS Cloud Operators using LocalStack.

Spins up an ephemeral LocalStack container to verify the operators can
successfully bind arguments to boto3 and invoke AWS APIs.

Note: Requires Docker daemon to be running.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import pytest

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


from sre_agent.adapters.cloud.aws.ec2_asg_operator import EC2ASGOperator
from sre_agent.adapters.cloud.aws.ecs_operator import ECSOperator
from sre_agent.adapters.cloud.aws.lambda_operator import LambdaOperator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def localstack():
    # Only load services we use to speed up boot
    with LocalStackContainer(image="localstack/localstack:latest").with_env("SERVICES", "autoscaling,ecs,lambda") as container:
        yield container

@pytest.fixture(scope="module")
def asg_client(localstack):
    return boto3.client(
        "autoscaling",
        region_name="us-east-1",
        endpoint_url=localstack.get_url(),
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )

@pytest.fixture(scope="module")
def ecs_client(localstack):
    return boto3.client(
        "ecs",
        region_name="us-east-1",
        endpoint_url=localstack.get_url(),
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )

@pytest.fixture(scope="module")
def lambda_client(localstack):
    return boto3.client(
        "lambda",
        region_name="us-east-1",
        endpoint_url=localstack.get_url(),
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ec2_asg_operator_integration(asg_client):
    operator = EC2ASGOperator(asg_client)
    
    # Test health check against live (localstack) API
    is_healthy = await operator.health_check()
    assert is_healthy is True

@pytest.mark.asyncio
async def test_ecs_operator_integration(ecs_client):
    operator = ECSOperator(ecs_client)
    
    is_healthy = await operator.health_check()
    assert is_healthy is True

@pytest.mark.asyncio
async def test_lambda_operator_integration(lambda_client):
    operator = LambdaOperator(lambda_client)
    
    is_healthy = await operator.health_check()
    assert is_healthy is True
