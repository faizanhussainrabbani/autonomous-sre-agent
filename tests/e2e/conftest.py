"""
E2E specific shared fixtures for testing against LocalStack Pro pipelines.
"""

import json
import os
import shutil
import subprocess
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

def _get_localstack_auth_token() -> str:
    """Resolve LOCALSTACK_AUTH_TOKEN from env var or ~/.localstack/auth.json."""
    token = os.environ.get("LOCALSTACK_AUTH_TOKEN", "")
    if not token:
        auth_file = os.path.expanduser("~/.localstack/auth.json")
        if os.path.exists(auth_file):
            with open(auth_file) as f:
                data = json.load(f)
                token = data.get("LOCALSTACK_AUTH_TOKEN", "")
    return token

_AUTH_TOKEN = _get_localstack_auth_token()

# Skip E2E tests if docker is not running.
pytestmark = pytest.mark.skipif(
    not _is_docker_daemon_running(),
    reason="Docker daemon is not running. E2E tests require Testcontainers.",
)

boto3 = pytest.importorskip("boto3")
testcontainers_localstack = pytest.importorskip("testcontainers.localstack")
LocalStackContainer = testcontainers_localstack.LocalStackContainer

# ---------------------------------------------------------------------------
# LocalStack Pro Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def localstack():
    """Start a LocalStack Pro container with autoscaling, ecs, and lambda services."""
    container = (
        LocalStackContainer(image="localstack/localstack-pro:latest")
        .with_env("SERVICES", "autoscaling,ecs,lambda")
        .with_env("LOCALSTACK_AUTH_TOKEN", _AUTH_TOKEN)
        .with_env("AWS_DEFAULT_REGION", "us-east-1")
        .with_env("DOCKER_HOST", "unix:///var/run/docker.sock")
        .with_volume_mapping("/var/run/docker.sock", "/var/run/docker.sock", "rw")
    )
    with container as c:
        yield c

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
