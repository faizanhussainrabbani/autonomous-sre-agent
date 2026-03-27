from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from sre_agent.adapters.cloud.kubernetes.operator import KubernetesOperator
from sre_agent.domain.models.canonical import ComputeMechanism


def _operator() -> KubernetesOperator:
    return KubernetesOperator(
        apps_api=MagicMock(),
        core_api=MagicMock(),
        version_api=MagicMock(),
    )


def test_provider_identity_and_supported_mechanism() -> None:
    operator = _operator()

    assert operator.provider_name == "kubernetes"
    assert operator.supported_mechanisms == [ComputeMechanism.KUBERNETES]


@pytest.mark.asyncio
async def test_restart_deployment_calls_patch() -> None:
    operator = _operator()

    result = await operator.restart_compute_unit(
        "deployment/checkout",
        metadata={"namespace": "prod"},
    )

    assert result["action"] == "restart"
    operator._apps.patch_namespaced_deployment.assert_called_once()


@pytest.mark.asyncio
async def test_restart_statefulset_calls_patch() -> None:
    operator = _operator()

    result = await operator.restart_compute_unit(
        "statefulset/orders-db",
        metadata={"namespace": "prod"},
    )

    assert result["resource_type"] == "statefulset"
    operator._apps.patch_namespaced_stateful_set.assert_called_once()


@pytest.mark.asyncio
async def test_scale_deployment_calls_patch_scale() -> None:
    operator = _operator()

    result = await operator.scale_capacity(
        "deployment/checkout",
        desired_count=8,
        metadata={"namespace": "prod"},
    )

    assert result["action"] == "scale"
    assert result["desired_count"] == 8
    operator._apps.patch_namespaced_deployment_scale.assert_called_once()


@pytest.mark.asyncio
async def test_unsupported_scale_target_raises_value_error() -> None:
    operator = _operator()

    with pytest.raises(ValueError, match="unsupported_kubernetes_scale_target"):
        await operator.scale_capacity("pod/checkout-0", desired_count=2, metadata={"namespace": "prod"})


@pytest.mark.asyncio
async def test_health_check_success_and_failure() -> None:
    operator = _operator()
    assert await operator.health_check() is True

    operator._version.get_code.side_effect = RuntimeError("boom")
    assert await operator.health_check() is False
