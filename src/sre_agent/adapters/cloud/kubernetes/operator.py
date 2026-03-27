"""Kubernetes cloud operator adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog

try:
    from kubernetes import client as kube_client
    from kubernetes.client import ApiClient
    from kubernetes.client.exceptions import ApiException
except ImportError:
    kube_client = None  # type: ignore[assignment]
    ApiClient = object  # type: ignore[assignment,misc]
    ApiException = Exception  # type: ignore[assignment,misc]

from sre_agent.adapters.cloud.resilience import CircuitBreaker, RetryConfig, retry_with_backoff
from sre_agent.domain.models.canonical import ComputeMechanism
from sre_agent.ports.cloud_operator import CloudOperatorPort

logger = structlog.get_logger(__name__)


class KubernetesOperator(CloudOperatorPort):
    """CloudOperatorPort adapter for Kubernetes remediation actions."""

    def __init__(
        self,
        apps_api: Any | None = None,
        core_api: Any | None = None,
        version_api: Any | None = None,
        retry_config: RetryConfig | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        if apps_api is None and kube_client is not None:
            apps_api = kube_client.AppsV1Api(ApiClient())
        if core_api is None and kube_client is not None:
            core_api = kube_client.CoreV1Api(ApiClient())
        if version_api is None and kube_client is not None:
            version_api = kube_client.VersionApi(ApiClient())

        self._apps = apps_api
        self._core = core_api
        self._version = version_api
        self._retry_config = retry_config or RetryConfig()
        self._circuit_breaker = circuit_breaker or CircuitBreaker(name="kubernetes")

    @property
    def provider_name(self) -> str:
        return "kubernetes"

    @property
    def supported_mechanisms(self) -> list[ComputeMechanism]:
        return [ComputeMechanism.KUBERNETES]

    async def restart_compute_unit(
        self,
        resource_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        meta = metadata or {}
        namespace = meta.get("namespace", "default")
        resource_type, resource_name = _split_resource(resource_id)

        async def _do_restart() -> dict[str, Any]:
            logger.info(
                "kubernetes_restart",
                resource_type=resource_type,
                resource_name=resource_name,
                namespace=namespace,
            )
            if resource_type == "deployment":
                body = {
                    "spec": {
                        "template": {
                            "metadata": {
                                "annotations": {
                                    "kubectl.kubernetes.io/restartedAt": datetime.now(
                                        timezone.utc,
                                    ).isoformat(),
                                },
                            },
                        },
                    },
                }
                self._apps.patch_namespaced_deployment(
                    name=resource_name,
                    namespace=namespace,
                    body=body,
                )
            elif resource_type == "statefulset":
                body = {
                    "spec": {
                        "template": {
                            "metadata": {
                                "annotations": {
                                    "kubectl.kubernetes.io/restartedAt": datetime.now(
                                        timezone.utc,
                                    ).isoformat(),
                                },
                            },
                        },
                    },
                }
                self._apps.patch_namespaced_stateful_set(
                    name=resource_name,
                    namespace=namespace,
                    body=body,
                )
            elif resource_type == "pod":
                self._core.delete_namespaced_pod(
                    name=resource_name,
                    namespace=namespace,
                )
            else:
                raise ValueError(f"unsupported_kubernetes_restart_target:{resource_type}")

            return {
                "action": "restart",
                "resource_type": resource_type,
                "resource_name": resource_name,
                "namespace": namespace,
            }

        return await retry_with_backoff(
            _do_restart,
            config=self._retry_config,
            circuit_breaker=self._circuit_breaker,
        )

    async def scale_capacity(
        self,
        resource_id: str,
        desired_count: int,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        meta = metadata or {}
        namespace = meta.get("namespace", "default")
        resource_type, resource_name = _split_resource(resource_id)
        body = {"spec": {"replicas": desired_count}}

        async def _do_scale() -> dict[str, Any]:
            logger.info(
                "kubernetes_scale",
                resource_type=resource_type,
                resource_name=resource_name,
                namespace=namespace,
                desired_count=desired_count,
            )
            if resource_type == "deployment":
                self._apps.patch_namespaced_deployment_scale(
                    name=resource_name,
                    namespace=namespace,
                    body=body,
                )
            elif resource_type == "statefulset":
                self._apps.patch_namespaced_stateful_set_scale(
                    name=resource_name,
                    namespace=namespace,
                    body=body,
                )
            else:
                raise ValueError(f"unsupported_kubernetes_scale_target:{resource_type}")

            return {
                "action": "scale",
                "resource_type": resource_type,
                "resource_name": resource_name,
                "namespace": namespace,
                "desired_count": desired_count,
            }

        return await retry_with_backoff(
            _do_scale,
            config=self._retry_config,
            circuit_breaker=self._circuit_breaker,
        )

    async def health_check(self) -> bool:
        try:
            if self._version is not None:
                self._version.get_code()
                return True
            if self._core is not None:
                self._core.list_namespace(limit=1)
                return True
            return False
        except Exception:
            return False


def _split_resource(resource_id: str) -> tuple[str, str]:
    if "/" in resource_id:
        return resource_id.split("/", 1)
    return "deployment", resource_id
