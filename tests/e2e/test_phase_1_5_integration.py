"""
E2E Integration Test — Phase 1.5 Full Pipeline Validation.

Tests the complete pipeline: Ingest → Correlate (degraded) → Detect
(cold-start suppressed) → Registry Resolve → Operator Execute.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

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
# Test Doubles
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
# E2E Pipeline: Serverless Lambda (cold start → detect → remediate)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_serverless_pipeline():
    """Full pipeline: Lambda cold start → degraded eBPF → cold-start suppressed
    → latency fires after window → registry resolves LambdaOperator → scale.
    """
    # 1. Setup
    baseline_svc = MockBaselineService(sigma=5.0)
    config = DetectionConfig(
        cold_start_suppression_window_seconds=15,
        latency_duration_minutes=0,
    )
    detector = AnomalyDetector(baseline_service=baseline_svc, config=config)

    mock_lambda = MagicMock()
    mock_lambda.put_function_concurrency.return_value = {}
    fast_retry = RetryConfig(max_retries=0)

    registry = CloudOperatorRegistry()
    registry.register(LambdaOperator(lambda_client=mock_lambda, retry_config=fast_retry))

    init_time = datetime.now(timezone.utc)

    # 2. eBPF degradation check — is_supported is concrete, call unbound
    assert eBPFQuery.is_supported(None, ComputeMechanism.SERVERLESS) is False

    # 3. Cold-start suppression: metric at T+5s → suppressed
    metric_cold = CanonicalMetric(
        name="http_request_duration_seconds",
        value=8.5,
        timestamp=init_time + timedelta(seconds=5),
        labels=ServiceLabels(
            service="payment-handler",
            compute_mechanism=ComputeMechanism.SERVERLESS,
            resource_id="arn:aws:lambda:us-east-1:123:function:payment-handler",
        ),
    )
    result_cold = await detector.detect(
        "payment-handler",
        [metric_cold],
        compute_mechanism=ComputeMechanism.SERVERLESS,
    )
    assert len(result_cold.alerts) == 0, "Cold-start should suppress"

    # 4. Post-window latency: T+22s starts timer (elapsed from init at T+5 = 17s > 15s), T+26s fires
    metric_post1 = CanonicalMetric(
        name="http_request_duration_seconds",
        value=8.5,
        timestamp=init_time + timedelta(seconds=22),
        labels=metric_cold.labels,
    )
    await detector.detect(
        "payment-handler", [metric_post1],
        compute_mechanism=ComputeMechanism.SERVERLESS,
    )

    metric_post2 = CanonicalMetric(
        name="http_request_duration_seconds",
        value=8.5,
        timestamp=init_time + timedelta(seconds=26),
        labels=metric_cold.labels,
    )
    result_fire = await detector.detect(
        "payment-handler", [metric_post2],
        compute_mechanism=ComputeMechanism.SERVERLESS,
    )
    assert len(result_fire.alerts) >= 1, "Alert should fire after cold-start window"

    # 5. Registry resolves LambdaOperator
    op = registry.get_operator("aws", ComputeMechanism.SERVERLESS)
    assert op is not None
    assert isinstance(op, LambdaOperator)

    # 6. Scale via operator (remediation)
    result = await op.scale_capacity(
        resource_id="arn:aws:lambda:us-east-1:123:function:payment-handler",
        desired_count=10,
    )
    mock_lambda.put_function_concurrency.assert_called_once()
    assert result["action"] == "put_function_concurrency"


# ---------------------------------------------------------------------------
# E2E Pipeline: ECS Container Instance (OOM exempt → error surge)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_container_instance_pipeline():
    """Pipeline: ECS target → memory exempted for containers (K8s path) → error
    detected → registry resolves ECSOperator → restart.
    """
    baseline_svc = MockBaselineService(sigma=5.0, mean=10.0)
    config = DetectionConfig()
    detector = AnomalyDetector(baseline_service=baseline_svc, config=config)

    mock_ecs = MagicMock()
    mock_ecs.stop_task.return_value = {}
    fast_retry = RetryConfig(max_retries=0)

    registry = CloudOperatorRegistry()
    registry.register(ECSOperator(ecs_client=mock_ecs, retry_config=fast_retry))

    # InvocationError surge
    metric = CanonicalMetric(
        name="invocation_error_count",
        value=35.0,
        timestamp=datetime.now(timezone.utc),
        labels=ServiceLabels(
            service="order-processor",
            compute_mechanism=ComputeMechanism.CONTAINER_INSTANCE,
            resource_id="arn:aws:ecs:us-east-1:123:task/cluster/task-id",
        ),
    )
    result = await detector.detect(
        "order-processor", [metric],
        compute_mechanism=ComputeMechanism.CONTAINER_INSTANCE,
    )
    assert len(result.alerts) >= 1

    # Registry resolves ECSOperator
    op = registry.get_operator("aws", ComputeMechanism.CONTAINER_INSTANCE)
    assert isinstance(op, ECSOperator)

    # Restart via operator
    await op.restart_compute_unit(
        resource_id="arn:aws:ecs:us-east-1:123:task/cluster/task-id",
        metadata={"cluster": "prod-cluster"},
    )
    mock_ecs.stop_task.assert_called_once()


# ---------------------------------------------------------------------------
# E2E: Multi-provider registry resolves correctly
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_multi_provider_registry_resolution():
    """Verify registry correctly resolves across all provider+mechanism combos."""
    fast_retry = RetryConfig(max_retries=0)
    registry = CloudOperatorRegistry()
    registry.register(ECSOperator(MagicMock(), retry_config=fast_retry))
    registry.register(EC2ASGOperator(MagicMock(), retry_config=fast_retry))
    registry.register(LambdaOperator(MagicMock(), retry_config=fast_retry))
    registry.register(AppServiceOperator(MagicMock(), retry_config=fast_retry))
    registry.register(FunctionsOperator(MagicMock(), retry_config=fast_retry))

    # All provider + mechanism combinations
    assert isinstance(
        registry.get_operator("aws", ComputeMechanism.CONTAINER_INSTANCE), ECSOperator
    )
    assert isinstance(
        registry.get_operator("aws", ComputeMechanism.VIRTUAL_MACHINE), EC2ASGOperator
    )
    assert isinstance(
        registry.get_operator("aws", ComputeMechanism.SERVERLESS), LambdaOperator
    )
    assert isinstance(
        registry.get_operator("azure", ComputeMechanism.SERVERLESS), FunctionsOperator
    )

    # Unknown combos return None
    assert registry.get_operator("gcp", ComputeMechanism.KUBERNETES) is None
    assert registry.get_operator("aws", ComputeMechanism.KUBERNETES) is None


# ---------------------------------------------------------------------------
# E2E: Health check across all operators
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_health_check_all_operators():
    """All registered operators return healthy status."""
    fast_retry = RetryConfig(max_retries=0)
    registry = CloudOperatorRegistry()
    registry.register(ECSOperator(MagicMock(), retry_config=fast_retry))
    registry.register(LambdaOperator(MagicMock(), retry_config=fast_retry))
    registry.register(AppServiceOperator(MagicMock(), retry_config=fast_retry))

    results = await registry.health_check_all()
    assert len(results) == 3
    assert all(v is True for v in results.values())
