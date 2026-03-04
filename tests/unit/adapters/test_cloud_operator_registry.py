"""
Tests for Phase 1.5 — CloudOperatorRegistry integration.

Validates: Task 7.3 — registry correctly resolves operators by provider + mechanism.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from sre_agent.domain.models.canonical import ComputeMechanism
from sre_agent.domain.detection.cloud_operator_registry import CloudOperatorRegistry
from sre_agent.adapters.cloud.aws.ecs_operator import ECSOperator
from sre_agent.adapters.cloud.aws.ec2_asg_operator import EC2ASGOperator
from sre_agent.adapters.cloud.aws.lambda_operator import LambdaOperator
from sre_agent.adapters.cloud.azure.app_service_operator import AppServiceOperator
from sre_agent.adapters.cloud.azure.functions_operator import FunctionsOperator


def _build_registry() -> CloudOperatorRegistry:
    """Build a registry with all mock operators registered."""
    registry = CloudOperatorRegistry()
    registry.register(ECSOperator(ecs_client=MagicMock()))
    registry.register(EC2ASGOperator(autoscaling_client=MagicMock()))
    registry.register(LambdaOperator(lambda_client=MagicMock()))
    registry.register(AppServiceOperator(web_client=MagicMock()))
    registry.register(FunctionsOperator(web_client=MagicMock()))
    return registry


# ---------------------------------------------------------------------------
# Resolution tests
# ---------------------------------------------------------------------------

def test_container_instance_aws_returns_ecs():
    """Given CONTAINER_INSTANCE on AWS, registry returns ECSOperator."""
    registry = _build_registry()
    op = registry.get_operator("aws", ComputeMechanism.CONTAINER_INSTANCE)

    assert op is not None
    assert isinstance(op, ECSOperator)


def test_virtual_machine_aws_returns_ec2_asg():
    """Given VIRTUAL_MACHINE on AWS, registry returns EC2ASGOperator."""
    registry = _build_registry()
    op = registry.get_operator("aws", ComputeMechanism.VIRTUAL_MACHINE)

    assert op is not None
    assert isinstance(op, EC2ASGOperator)


def test_serverless_aws_returns_lambda():
    """Given SERVERLESS on AWS, registry returns LambdaOperator."""
    registry = _build_registry()
    op = registry.get_operator("aws", ComputeMechanism.SERVERLESS)

    assert op is not None
    assert isinstance(op, LambdaOperator)


def test_serverless_azure_returns_functions():
    """Given SERVERLESS on Azure, registry returns FunctionsOperator."""
    registry = _build_registry()
    op = registry.get_operator("azure", ComputeMechanism.SERVERLESS)

    assert op is not None
    assert isinstance(op, FunctionsOperator)


def test_unknown_provider_returns_none():
    """Unknown provider returns None."""
    registry = _build_registry()
    assert registry.get_operator("gcp", ComputeMechanism.KUBERNETES) is None


def test_list_operators_by_provider():
    """list_operators filters by provider."""
    registry = _build_registry()

    aws_ops = registry.list_operators("aws")
    assert len(aws_ops) == 3

    azure_ops = registry.list_operators("azure")
    assert len(azure_ops) == 2


@pytest.mark.asyncio
async def test_health_check_all():
    """health_check_all runs health checks on all unique operators."""
    registry = _build_registry()
    results = await registry.health_check_all()

    # All mock operators should return True (MagicMock doesn't raise)
    assert len(results) == 5
    assert all(v is True for v in results.values())
