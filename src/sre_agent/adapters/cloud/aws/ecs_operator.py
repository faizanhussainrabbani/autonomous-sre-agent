"""
ECS Cloud Operator — Manages Amazon ECS task lifecycles and service scaling.

Phase 1.5: Implements CloudOperatorPort for CONTAINER_INSTANCE on AWS ECS.
Includes retry with exponential backoff and circuit breaker.
"""

from __future__ import annotations

import structlog
from typing import Any

try:
    from botocore.exceptions import ClientError as _BotoCoreClientError
    _AWS_ERRORS = (_BotoCoreClientError, ConnectionError, TimeoutError)
except ImportError:  # boto3 not installed
    _AWS_ERRORS = (Exception,)  # type: ignore[assignment]

from sre_agent.domain.models.canonical import ComputeMechanism
from sre_agent.ports.cloud_operator import CloudOperatorPort
from sre_agent.adapters.cloud.aws.error_mapper import map_boto_error
from sre_agent.adapters.cloud.resilience import (
    CircuitBreaker,
    RetryConfig,
    retry_with_backoff,
)

logger = structlog.get_logger(__name__)


class ECSOperator(CloudOperatorPort):
    """CloudOperatorPort adapter for Amazon ECS (Elastic Container Service)."""

    def __init__(
        self,
        ecs_client: Any,
        retry_config: RetryConfig | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self._ecs = ecs_client
        self._retry_config = retry_config or RetryConfig()
        self._circuit_breaker = circuit_breaker or CircuitBreaker(name="ecs")

    @property
    def provider_name(self) -> str:
        return "aws"

    @property
    def supported_mechanisms(self) -> list[ComputeMechanism]:
        return [ComputeMechanism.CONTAINER_INSTANCE]

    async def restart_compute_unit(
        self, resource_id: str, metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Stop an ECS task; the service scheduler starts a replacement."""
        meta = metadata or {}
        cluster = meta.get("cluster", "default")

        async def _do_stop():
            logger.info("ecs_stop_task", task=resource_id, cluster=cluster)
            try:
                response = self._ecs.stop_task(cluster=cluster, task=resource_id)
            except _AWS_ERRORS as exc:
                raise map_boto_error(exc) from exc
            return {"action": "stop_task", "task": resource_id, "response": response}

        return await retry_with_backoff(
            _do_stop,
            config=self._retry_config,
            circuit_breaker=self._circuit_breaker,
        )

    async def scale_capacity(
        self, resource_id: str, desired_count: int,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update the desiredCount of an ECS service."""
        meta = metadata or {}
        cluster = meta.get("cluster", "default")

        async def _do_scale():
            logger.info("ecs_update_service", service=resource_id, desired=desired_count)
            try:
                response = self._ecs.update_service(
                    cluster=cluster, service=resource_id, desiredCount=desired_count,
                )
            except _AWS_ERRORS as exc:
                raise map_boto_error(exc) from exc
            return {"action": "update_service", "service": resource_id, "desired_count": desired_count, "response": response}

        return await retry_with_backoff(
            _do_scale,
            config=self._retry_config,
            circuit_breaker=self._circuit_breaker,
        )

    async def health_check(self) -> bool:
        """Probe ECS connectivity. Intentionally broad — any failure = unhealthy."""
        try:
            self._ecs.list_clusters()
            return True
        except Exception:  # noqa: BLE001 — health probe intentionally broad
            return False
