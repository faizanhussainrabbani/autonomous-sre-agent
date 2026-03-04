"""
Tests for Phase 1.5 — AWS Cloud Operator Adapters.

Validates: AC-1.5.6 (AWS Adapters)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from sre_agent.domain.models.canonical import ComputeMechanism
from sre_agent.adapters.cloud.aws.ecs_operator import ECSOperator
from sre_agent.adapters.cloud.aws.ec2_asg_operator import EC2ASGOperator
from sre_agent.adapters.cloud.aws.lambda_operator import LambdaOperator


# ---------------------------------------------------------------------------
# ECS Operator — AC-1.5.6.1, AC-1.5.6.2
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ecs_restart_calls_stop_task():
    """AC-1.5.6.1: restart_compute_unit calls ecs.stop_task."""
    mock_ecs = MagicMock()
    mock_ecs.stop_task.return_value = {"task": {"taskArn": "arn:task"}}
    op = ECSOperator(ecs_client=mock_ecs)

    result = await op.restart_compute_unit(
        resource_id="arn:aws:ecs:us-east-1:123456789:task/cluster/task-id",
        metadata={"cluster": "prod-cluster"},
    )

    mock_ecs.stop_task.assert_called_once_with(
        cluster="prod-cluster",
        task="arn:aws:ecs:us-east-1:123456789:task/cluster/task-id",
    )
    assert result["action"] == "stop_task"


@pytest.mark.asyncio
async def test_ecs_scale_calls_update_service():
    """AC-1.5.6.2: scale_capacity calls ecs.update_service."""
    mock_ecs = MagicMock()
    mock_ecs.update_service.return_value = {"service": {"serviceName": "svc"}}
    op = ECSOperator(ecs_client=mock_ecs)

    await op.scale_capacity(
        resource_id="my-service",
        desired_count=5,
        metadata={"cluster": "prod-cluster"},
    )

    mock_ecs.update_service.assert_called_once_with(
        cluster="prod-cluster", service="my-service", desiredCount=5,
    )


# ---------------------------------------------------------------------------
# EC2 ASG Operator — AC-1.5.6.3
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ec2_asg_scale_calls_set_desired_capacity():
    """AC-1.5.6.3: scale_capacity calls autoscaling.set_desired_capacity."""
    mock_asg = MagicMock()
    op = EC2ASGOperator(autoscaling_client=mock_asg)

    await op.scale_capacity(resource_id="my-asg", desired_count=3)

    mock_asg.set_desired_capacity.assert_called_once_with(
        AutoScalingGroupName="my-asg", DesiredCapacity=3,
    )


@pytest.mark.asyncio
async def test_ec2_asg_restart_raises():
    """EC2 ASG does not support individual instance restart."""
    mock_asg = MagicMock()
    op = EC2ASGOperator(autoscaling_client=mock_asg)

    with pytest.raises(NotImplementedError):
        await op.restart_compute_unit(resource_id="i-abc123")


# ---------------------------------------------------------------------------
# Lambda Operator — AC-1.5.6.4
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_lambda_scale_calls_put_concurrency():
    """AC-1.5.6.4: scale_capacity calls lambda.put_function_concurrency."""
    mock_lambda = MagicMock()
    op = LambdaOperator(lambda_client=mock_lambda)

    await op.scale_capacity(
        resource_id="arn:aws:lambda:us-east-1:123456789:function:my-fn",
        desired_count=50,
    )

    mock_lambda.put_function_concurrency.assert_called_once_with(
        FunctionName="arn:aws:lambda:us-east-1:123456789:function:my-fn",
        ReservedConcurrentExecutions=50,
    )


@pytest.mark.asyncio
async def test_lambda_restart_raises():
    """Lambda does not support restart."""
    mock_lambda = MagicMock()
    op = LambdaOperator(lambda_client=mock_lambda)

    with pytest.raises(NotImplementedError):
        await op.restart_compute_unit(resource_id="my-fn")


def test_lambda_restart_not_supported():
    """is_action_supported('restart') returns False for Lambda."""
    mock_lambda = MagicMock()
    op = LambdaOperator(lambda_client=mock_lambda)

    assert op.is_action_supported("restart", ComputeMechanism.SERVERLESS) is False
    assert op.is_action_supported("scale", ComputeMechanism.SERVERLESS) is True
