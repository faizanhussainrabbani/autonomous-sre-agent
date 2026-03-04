"""
Azure Functions Operator — Manages Azure Functions lifecycle via azure-mgmt-web.

Phase 1.5: Implements CloudOperatorPort for SERVERLESS on Azure Functions.
Includes retry with exponential backoff and circuit breaker.
"""

from __future__ import annotations

import structlog
from typing import Any

from sre_agent.domain.models.canonical import ComputeMechanism
from sre_agent.ports.cloud_operator import CloudOperatorPort
from sre_agent.adapters.cloud.resilience import (
    CircuitBreaker,
    RetryConfig,
    TransientError,
    retry_with_backoff,
)

logger = structlog.get_logger(__name__)


class FunctionsOperator(CloudOperatorPort):
    """CloudOperatorPort adapter for Azure Functions."""

    def __init__(
        self,
        web_client: Any,
        retry_config: RetryConfig | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self._web = web_client
        self._retry_config = retry_config or RetryConfig()
        self._circuit_breaker = circuit_breaker or CircuitBreaker(name="functions")

    @property
    def provider_name(self) -> str:
        return "azure"

    @property
    def supported_mechanisms(self) -> list[ComputeMechanism]:
        return [ComputeMechanism.SERVERLESS]

    async def restart_compute_unit(
        self, resource_id: str, metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Restart an Azure Function app."""
        meta = metadata or {}
        resource_group = meta.get("resource_group", "")

        async def _do_restart():
            logger.info("functions_restart", app=resource_id, rg=resource_group)
            try:
                self._web.web_apps.restart(resource_group, resource_id)
            except Exception as exc:
                raise TransientError(f"Functions restart failed: {exc}") from exc
            return {"action": "restart", "function_app": resource_id}

        return await retry_with_backoff(
            _do_restart,
            config=self._retry_config,
            circuit_breaker=self._circuit_breaker,
        )

    async def scale_capacity(
        self, resource_id: str, desired_count: int,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Scale Azure Functions Premium plan instance count."""
        meta = metadata or {}
        resource_group = meta.get("resource_group", "")
        plan_name = meta.get("plan_name", resource_id)

        async def _do_scale():
            logger.info("functions_scale", plan=plan_name, desired=desired_count)
            try:
                plan = self._web.app_service_plans.get(resource_group, plan_name)
                plan.sku.capacity = desired_count
                self._web.app_service_plans.create_or_update(resource_group, plan_name, plan)
            except Exception as exc:
                raise TransientError(f"Functions scale failed: {exc}") from exc
            return {"action": "scale", "plan": plan_name, "desired_count": desired_count}

        return await retry_with_backoff(
            _do_scale,
            config=self._retry_config,
            circuit_breaker=self._circuit_breaker,
        )

    async def health_check(self) -> bool:
        try:
            list(self._web.web_apps.list())
            return True
        except Exception:
            return False
