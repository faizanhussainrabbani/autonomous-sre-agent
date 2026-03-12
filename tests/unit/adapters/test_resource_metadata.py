"""
Unit tests for AWS Resource Metadata Fetcher.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from sre_agent.adapters.cloud.aws.resource_metadata import AWSResourceMetadataFetcher


def _client_error(code="ResourceNotFoundException"):
    return ClientError(
        error_response={"Error": {"Code": code, "Message": "not found"}},
        operation_name="Op",
    )


# ── fetch_lambda_context() ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_lambda_context_success():
    client = MagicMock()
    client.get_function_configuration.return_value = {
        "MemorySize": 512,
        "Timeout": 30,
        "Runtime": "python3.11",
        "Handler": "main.handler",
        "CodeSize": 1024,
        "LastModified": "2024-01-01T00:00:00Z",
        "Layers": [{"Arn": "arn:aws:lambda:us-east-1:123:layer:layer1:1"}],
    }
    fetcher = AWSResourceMetadataFetcher(lambda_client=client)

    result = await fetcher.fetch_lambda_context("payment-handler")
    assert result["memory_mb"] == 512
    assert result["timeout_s"] == 30
    assert result["runtime"] == "python3.11"
    assert result["handler"] == "main.handler"
    assert result["code_size_bytes"] == 1024
    assert len(result["layers"]) == 1


@pytest.mark.asyncio
async def test_fetch_lambda_context_with_concurrency():
    client = MagicMock()
    client.get_function_configuration.return_value = {
        "MemorySize": 256,
        "Timeout": 10,
        "Runtime": "nodejs18.x",
        "Handler": "index.handler",
        "CodeSize": 512,
        "LastModified": "2024-01-01T00:00:00Z",
        "Layers": [],
    }
    client.get_function_concurrency.return_value = {
        "ReservedConcurrentExecutions": 100,
    }
    fetcher = AWSResourceMetadataFetcher(lambda_client=client)
    result = await fetcher.fetch_lambda_context("payment-handler")
    assert result["reserved_concurrency"] == 100


@pytest.mark.asyncio
async def test_fetch_lambda_context_not_found():
    client = MagicMock()
    client.get_function_configuration.side_effect = _client_error()
    fetcher = AWSResourceMetadataFetcher(lambda_client=client)
    result = await fetcher.fetch_lambda_context("missing-fn")
    assert result == {}


@pytest.mark.asyncio
async def test_fetch_lambda_context_no_client():
    fetcher = AWSResourceMetadataFetcher()
    result = await fetcher.fetch_lambda_context("fn")
    assert result == {}


# ── fetch_ecs_context() ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_ecs_context_success():
    client = MagicMock()
    client.describe_services.return_value = {
        "services": [
            {
                "desiredCount": 3,
                "runningCount": 3,
                "pendingCount": 0,
                "taskDefinition": "arn:task-def",
                "launchType": "FARGATE",
                "deployments": [{"status": "PRIMARY"}],
            }
        ]
    }
    fetcher = AWSResourceMetadataFetcher(ecs_client=client)
    result = await fetcher.fetch_ecs_context(cluster="my-cluster", service="my-service")
    assert result["desired_count"] == 3
    assert result["running_count"] == 3
    assert result["launch_type"] == "FARGATE"


@pytest.mark.asyncio
async def test_fetch_ecs_context_no_client():
    fetcher = AWSResourceMetadataFetcher()
    result = await fetcher.fetch_ecs_context("default", "svc")
    assert result == {}


@pytest.mark.asyncio
async def test_fetch_ecs_context_no_services():
    client = MagicMock()
    client.describe_services.return_value = {"services": []}
    fetcher = AWSResourceMetadataFetcher(ecs_client=client)
    result = await fetcher.fetch_ecs_context("default", "missing-svc")
    assert result == {}


# ── fetch_ec2_asg_context() ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_ec2_asg_context_success():
    client = MagicMock()
    client.describe_auto_scaling_groups.return_value = {
        "AutoScalingGroups": [
            {
                "DesiredCapacity": 5,
                "MinSize": 2,
                "MaxSize": 10,
                "Instances": [
                    {"HealthStatus": "Healthy"},
                    {"HealthStatus": "Healthy"},
                    {"HealthStatus": "Unhealthy"},
                    {"HealthStatus": "Healthy"},
                    {"HealthStatus": "Healthy"},
                ],
            }
        ]
    }
    fetcher = AWSResourceMetadataFetcher(autoscaling_client=client)
    result = await fetcher.fetch_ec2_asg_context("my-asg")
    assert result["desired_capacity"] == 5
    assert result["instance_count"] == 5
    assert result["healthy_count"] == 4
    assert result["unhealthy_count"] == 1


@pytest.mark.asyncio
async def test_fetch_ec2_asg_context_no_client():
    fetcher = AWSResourceMetadataFetcher()
    result = await fetcher.fetch_ec2_asg_context("asg")
    assert result == {}
