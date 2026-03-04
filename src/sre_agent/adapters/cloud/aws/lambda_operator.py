"""
Lambda Operator — Manages AWS Lambda concurrency settings via boto3.

Phase 1.5: Implements CloudOperatorPort for SERVERLESS on AWS Lambda.
Includes retry with exponential backoff and circuit breaker.
"""

from __future__ import annotations

import structlog
from typing import Any

try:
    from botocore.exceptions import ClientError as _BotoCoreClientError
    _AWS_ERRORS = (_BotoCoreClientError, ConnectionError, TimeoutError)
except ImportError:
    _AWS_ERRORS = (Exception,)  # type: ignore[assignment]

from sre_agent.domain.models.canonical import ComputeMechanism
from sre_agent.ports.cloud_operator import CloudOperatorPort
from sre_agent.adapters.cloud.resilience import (
    CircuitBreaker,
    RetryConfig,
    TransientError,
    retry_with_backoff,
)

logger = structlog.get_logger(__name__)


class LambdaOperator(CloudOperatorPort):
    """CloudOperatorPort adapter for AWS Lambda."""

    def __init__(
        self,
        lambda_client: Any,
        retry_config: RetryConfig | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self._lambda = lambda_client
        self._retry_config = retry_config or RetryConfig()
        self._circuit_breaker = circuit_breaker or CircuitBreaker(name="lambda")

    @property
    def provider_name(self) -> str:
        return "aws"

    @property
    def supported_mechanisms(self) -> list[ComputeMechanism]:
        return [ComputeMechanism.SERVERLESS]

    def is_action_supported(self, action: str, compute_mechanism: ComputeMechanism) -> bool:
        if action == "restart":
            return False  # Lambda functions cannot be "restarted"
        return super().is_action_supported(action, compute_mechanism)

    async def restart_compute_unit(
        self, resource_id: str, metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError(
            "Lambda functions cannot be restarted. "
            "Use scale_capacity to adjust reserved concurrency instead."
        )

    async def scale_capacity(
        self, resource_id: str, desired_count: int,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Adjust reserved concurrency for a Lambda function."""

        async def _do_scale():
            logger.info("lambda_put_concurrency", function=resource_id, concurrency=desired_count)
            try:
                response = self._lambda.put_function_concurrency(
                    FunctionName=resource_id,
                    ReservedConcurrentExecutions=desired_count,
                )
            except _AWS_ERRORS as exc:
                raise TransientError(f"Lambda PutFunctionConcurrency failed: {exc}") from exc
            return {"action": "put_function_concurrency", "function": resource_id, "concurrency": desired_count, "response": response}

        return await retry_with_backoff(
            _do_scale,
            config=self._retry_config,
            circuit_breaker=self._circuit_breaker,
        )

    async def health_check(self) -> bool:
        """Probe Lambda connectivity. Intentionally broad — any failure = unhealthy."""
        try:
            self._lambda.list_functions(MaxItems=1)
            return True
        except Exception:  # noqa: BLE001 — health probe intentionally broad
            return False
