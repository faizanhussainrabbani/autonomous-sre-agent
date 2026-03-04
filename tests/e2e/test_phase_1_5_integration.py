"""
E2E Integration Test — Phase 1.5 Full Pipeline Validation.

Tests the complete pipeline using REAL (LocalStack Pro) external mocks: 
Ingest → Correlate (degraded) → Detect (cold-start suppressed) → 
Registry Resolve → Operator Execute → LocalStack Assertion.
"""

from __future__ import annotations

import io
import zipfile
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest

from sre_agent.domain.models.canonical import (
    AnomalyType,
    CanonicalMetric,
    ComputeMechanism,
    ServiceLabels,
)
from sre_agent.domain.models.detection_config import DetectionConfig
from sre_agent.domain.detection.anomaly_detector import AnomalyDetector
from sre_agent.domain.detection.cloud_operator_registry import CloudOperatorRegistry
from sre_agent.ports.telemetry import BaselineQuery, eBPFQuery

from sre_agent.adapters.cloud.aws.ecs_operator import ECSOperator
from sre_agent.adapters.cloud.aws.lambda_operator import LambdaOperator
from sre_agent.adapters.cloud.azure.app_service_operator import AppServiceOperator
from sre_agent.adapters.cloud.azure.functions_operator import FunctionsOperator
from sre_agent.adapters.cloud.aws.ec2_asg_operator import EC2ASGOperator
from sre_agent.adapters.cloud.resilience import RetryConfig


# ---------------------------------------------------------------------------
# Test Doubles (Domain level)
# ---------------------------------------------------------------------------

@dataclass
class MockBaseline:
    mean: float = 1.0
    std: float = 0.3
    is_established: bool = True


class MockBaselineService(BaselineQuery):
    def __init__(self, sigma=5.0, mean=1.0):
        self._sigma = sigma
        self._baseline = MockBaseline(mean=mean)

    def get_baseline(self, service, metric, timestamp=None):
        return self._baseline

    def compute_deviation(self, service, metric, value, timestamp=None):
        return (self._sigma, self._baseline)

    async def ingest(self, service, metric, value, timestamp):
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_dummy_lambda_zip() -> bytes:
    zip_output = io.BytesIO()
    with zipfile.ZipFile(zip_output, 'w') as zip_file:
        zip_file.writestr('lambda_function.py', 'def handler(event, context): return "OK"\n')
    return zip_output.getvalue()


# ---------------------------------------------------------------------------
# E2E Pipeline: Serverless Lambda (cold start → detect → remediate)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_serverless_pipeline(lambda_client):
    """Full pipeline: Lambda cold start → degraded eBPF → cold-start suppressed
    → latency fires after window → registry resolves LambdaOperator → scale.
    """
    # 0. Seed real resource in LocalStack
    # We create a function so we can scale it.
    func_name = "payment-handler-e2e"
    resp = lambda_client.create_function(
        FunctionName=func_name,
        Runtime="python3.9",
        Role="arn:aws:iam::000000000000:role/dummy",
        Handler="lambda_function.handler",
        Code={"ZipFile": _create_dummy_lambda_zip()},
    )
    func_arn = resp["FunctionArn"]
    
    # Assert base concurrency is absent
    conc_base = lambda_client.get_function_concurrency(FunctionName=func_name)
    assert "ReservedConcurrentExecutions" not in conc_base

    # 1. Setup Agent Engine
    baseline_svc = MockBaselineService(sigma=5.0)
    config = DetectionConfig(
        cold_start_suppression_window_seconds=0.5,
        latency_duration_minutes=0,
    )
    detector = AnomalyDetector(baseline_service=baseline_svc, config=config)
    fast_retry = RetryConfig(max_retries=0)

    registry = CloudOperatorRegistry()
    registry.register(LambdaOperator(lambda_client=lambda_client, retry_config=fast_retry))

    init_time = datetime.now(timezone.utc)

    # 2. Cold-start suppression check
    metric_cold = CanonicalMetric(
        name="http_request_duration_seconds",
        value=8.5,
        timestamp=datetime.now(timezone.utc),
        labels=ServiceLabels(
            service=func_name,
            compute_mechanism=ComputeMechanism.SERVERLESS,
            resource_id=func_arn,
        ),
    )
    result_cold = await detector.detect(
        func_name, [metric_cold],
        compute_mechanism=ComputeMechanism.SERVERLESS,
    )
    assert len(result_cold.alerts) == 0, "Cold-start should suppress"

    # 3. Post-window latency triggers alert
    await asyncio.sleep(0.6)  # physically wait out the 0.5s cold-start window
    
    metric_post1 = CanonicalMetric(
        name="http_request_duration_seconds",
        value=8.5,
        timestamp=datetime.now(timezone.utc),
        labels=metric_cold.labels,
    )
    result1 = await detector.detect(
        func_name, [metric_post1],
        compute_mechanism=ComputeMechanism.SERVERLESS,
    )
    print(f"DEBUG: result1 alerts = {result1.alerts}")

    metric_post2 = CanonicalMetric(
        name="http_request_duration_seconds",
        value=8.5,
        timestamp=datetime.now(timezone.utc) + timedelta(seconds=1),
        labels=metric_cold.labels,
    )
    result_fire = await detector.detect(
        func_name, [metric_post2],
        compute_mechanism=ComputeMechanism.SERVERLESS,
    )
    print(f"DEBUG: result_fire alerts = {result_fire.alerts}")
    assert len(result_fire.alerts) >= 1, "Alert should fire after cold-start window"

    # 4. Registry resolves Operator
    op = registry.get_operator("aws", ComputeMechanism.SERVERLESS)
    assert isinstance(op, LambdaOperator)

    # 5. Execute Action (Remediation)
    result = await op.scale_capacity(
        resource_id=func_arn,
        desired_count=10,
    )
    assert result["action"] == "put_function_concurrency"

    # 6. Verify State in LocalStack 
    conc_resp = lambda_client.get_function_concurrency(FunctionName=func_name)
    assert conc_resp["ReservedConcurrentExecutions"] == 10


# ---------------------------------------------------------------------------
# E2E Pipeline: ECS Container Instance (OOM exempt → error surge)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_container_instance_pipeline(ecs_client):
    """Pipeline: ECS target → error detected → registry resolves ECSOperator → restart.
    Verifies that the task actually transitions to STOPPED in LocalStack.
    """
    cluster_name = "e2e-prod-cluster"
    # Seed LocalStack cluster & task
    ecs_client.create_cluster(clusterName=cluster_name)
    ecs_client.register_task_definition(
        family="order-processor-task",
        containerDefinitions=[{"name": "worker", "image": "nginx", "memory": 128}],
        cpu="256",
        memory="512"
    )
    
    # We must create a subnet/vpc in localstack or just use EC2 launch type instead of FARGATE 
    # to avoid needing subnets and security groups for run_task. So let's stick to simple EC2 compat.
    # For simple localstack EC2 tasks, we can just run it
    run_resp = ecs_client.run_task(
        cluster=cluster_name,
        taskDefinition="order-processor-task"
    )
    task_arn = run_resp["tasks"][0]["taskArn"]
    
    # 1. Setup Agent Engine
    baseline_svc = MockBaselineService(sigma=5.0, mean=10.0)
    config = DetectionConfig()
    detector = AnomalyDetector(baseline_service=baseline_svc, config=config)
    fast_retry = RetryConfig(max_retries=0)

    registry = CloudOperatorRegistry()
    registry.register(ECSOperator(ecs_client=ecs_client, retry_config=fast_retry))

    # 2. Anomaly Ingestion
    metric = CanonicalMetric(
        name="invocation_error_count",
        value=35.0,
        timestamp=datetime.now(timezone.utc),
        labels=ServiceLabels(
            service="order-processor",
            compute_mechanism=ComputeMechanism.CONTAINER_INSTANCE,
            resource_id=task_arn,
        ),
    )
    result = await detector.detect(
        "order-processor", [metric],
        compute_mechanism=ComputeMechanism.CONTAINER_INSTANCE,
    )
    assert len(result.alerts) >= 1

    # 3. Resolution & Action
    op = registry.get_operator("aws", ComputeMechanism.CONTAINER_INSTANCE)
    assert isinstance(op, ECSOperator)

    await op.restart_compute_unit(
        resource_id=task_arn,
        metadata={"cluster": cluster_name},
    )

    # 4. Verify LocalStack State
    desc_resp = ecs_client.describe_tasks(cluster=cluster_name, tasks=[task_arn])
    status = desc_resp["tasks"][0]["lastStatus"]
    assert status in ("STOPPING", "STOPPED"), f"Task status should be terminating, got {status}"


# ---------------------------------------------------------------------------
# E2E: Registry Integration 
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_multi_provider_registry_resolution():
    """Verify registry correctly resolves across all provider+mechanism combos."""
    # (Leaving Mock dependencies here since this purely tests the Registry Dict matching hash logic)
    fast_retry = RetryConfig(max_retries=0)
    registry = CloudOperatorRegistry()
    registry.register(ECSOperator(MagicMock(), retry_config=fast_retry))
    registry.register(EC2ASGOperator(MagicMock(), retry_config=fast_retry))
    registry.register(LambdaOperator(MagicMock(), retry_config=fast_retry))
    registry.register(AppServiceOperator(MagicMock(), retry_config=fast_retry))
    registry.register(FunctionsOperator(MagicMock(), retry_config=fast_retry))

    assert isinstance(registry.get_operator("aws", ComputeMechanism.CONTAINER_INSTANCE), ECSOperator)
    assert isinstance(registry.get_operator("aws", ComputeMechanism.VIRTUAL_MACHINE), EC2ASGOperator)
    assert isinstance(registry.get_operator("aws", ComputeMechanism.SERVERLESS), LambdaOperator)
    assert isinstance(registry.get_operator("azure", ComputeMechanism.SERVERLESS), FunctionsOperator)

    # Unknown combos return None
    assert registry.get_operator("gcp", ComputeMechanism.KUBERNETES) is None
    assert registry.get_operator("aws", ComputeMechanism.KUBERNETES) is None


@pytest.mark.asyncio
async def test_e2e_health_check_all_operators(asg_client, ecs_client, lambda_client):
    """All registered operators return healthy status when connected to LocalStack."""
    fast_retry = RetryConfig(max_retries=0)
    registry = CloudOperatorRegistry()
    registry.register(EC2ASGOperator(asg_client, retry_config=fast_retry))
    registry.register(ECSOperator(ecs_client, retry_config=fast_retry))
    registry.register(LambdaOperator(lambda_client, retry_config=fast_retry))
    # Still mock Azure
    registry.register(AppServiceOperator(MagicMock(), retry_config=fast_retry))

    results = await registry.health_check_all()
    assert len(results) == 4
    # Check that EC2, ECS, and Lambda keys exist in the output dict and are True
    assert results.get("aws:EC2ASGOperator", False) is True
    assert results.get("aws:ECSOperator", False) is True
    assert results.get("aws:LambdaOperator", False) is True
