"""Shared LocalStack Pro standards for integration tests."""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any, Iterable

import pytest

LOCALSTACK_PRO_IMAGE = "localstack/localstack-pro:latest"
LOCALSTACK_DEFAULT_REGION = "us-east-1"
LOCALSTACK_REQUIRED_SERVICE_LIST = [
    "autoscaling",
    "cloudwatch",
    "ec2",
    "ecs",
    "events",
    "iam",
    "lambda",
    "logs",
    "s3",
    "secretsmanager",
    "sns",
    "sts",
]
LOCALSTACK_REQUIRED_SERVICES = ",".join(LOCALSTACK_REQUIRED_SERVICE_LIST)
LOCALSTACK_HEALTH_ENDPOINT = "http://localhost:4566/_localstack/health"


def is_docker_daemon_running() -> bool:
    """Return True when docker is installed and the daemon is reachable."""
    if not shutil.which("docker"):
        return False
    try:
        subprocess.run(
            ["docker", "info"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def resolve_localstack_auth_token() -> tuple[str, str]:
    """Resolve token from LOCALSTACK_AUTH_TOKEN environment variable."""
    env_token = (os.environ.get("LOCALSTACK_AUTH_TOKEN") or "").strip()
    if env_token:
        return env_token, "environment variable"
    return "", "missing"


def require_localstack_auth_token() -> str:
    """Return token or skip test when token resolution fails."""
    token, _ = resolve_localstack_auth_token()
    if token:
        return token

    pytest.skip(
        "LOCALSTACK_AUTH_TOKEN is missing. Set it in .env or export it in your shell."
    )


def build_services(extra_services: Iterable[str] | None = None) -> str:
    """Return canonical service list with optional extras appended once."""
    ordered = list(LOCALSTACK_REQUIRED_SERVICE_LIST)
    if extra_services:
        for service in extra_services:
            service_name = service.strip()
            if service_name and service_name not in ordered:
                ordered.append(service_name)
    return ",".join(ordered)


def build_localstack_pro_container(
    LocalStackContainer: Any,
    *,
    extra_services: Iterable[str] | None = None,
    extra_env: dict[str, str] | None = None,
) -> Any:
    """Create a testcontainers LocalStack Pro container using canonical settings."""
    token = require_localstack_auth_token()
    container = (
        LocalStackContainer(image=LOCALSTACK_PRO_IMAGE)
        .with_env("SERVICES", build_services(extra_services))
        .with_env("LOCALSTACK_AUTH_TOKEN", token)
        .with_env("DEFAULT_REGION", LOCALSTACK_DEFAULT_REGION)
        .with_env("AWS_DEFAULT_REGION", LOCALSTACK_DEFAULT_REGION)
        .with_env("LAMBDA_RUNTIME_ENVIRONMENT_TIMEOUT", "120")
        .with_env("EAGER_SERVICE_LOADING", "1")
    )
    for key, value in (extra_env or {}).items():
        container = container.with_env(key, value)
    return container
