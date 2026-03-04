"""
EC2 Auto Scaling Operator — Manages EC2 ASG scaling via boto3.

Phase 1.5: Implements CloudOperatorPort for VIRTUAL_MACHINE on AWS EC2 ASGs.
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


class EC2ASGOperator(CloudOperatorPort):
    """CloudOperatorPort adapter for Amazon EC2 Auto Scaling Groups."""

    def __init__(
        self,
        autoscaling_client: Any,
        retry_config: RetryConfig | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self._asg = autoscaling_client
        self._retry_config = retry_config or RetryConfig()
        self._circuit_breaker = circuit_breaker or CircuitBreaker(name="ec2_asg")

    @property
    def provider_name(self) -> str:
        return "aws"

    @property
    def supported_mechanisms(self) -> list[ComputeMechanism]:
        return [ComputeMechanism.VIRTUAL_MACHINE]

    async def restart_compute_unit(
        self, resource_id: str, metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError(
            "EC2 ASG operator does not support individual instance restart. "
            "Use scale_capacity to cycle instances via the ASG."
        )

    async def scale_capacity(
        self, resource_id: str, desired_count: int,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Set the DesiredCapacity of an EC2 Auto Scaling Group."""

        async def _do_scale():
            logger.info("ec2_asg_set_desired_capacity", asg=resource_id, desired=desired_count)
            try:
                response = self._asg.set_desired_capacity(
                    AutoScalingGroupName=resource_id,
                    DesiredCapacity=desired_count,
                )
            except _AWS_ERRORS as exc:
                raise TransientError(f"ASG SetDesiredCapacity failed: {exc}") from exc
            return {"action": "set_desired_capacity", "asg": resource_id, "desired": desired_count, "response": response}

        return await retry_with_backoff(
            _do_scale,
            config=self._retry_config,
            circuit_breaker=self._circuit_breaker,
        )

    async def health_check(self) -> bool:
        """Probe ASG connectivity. Intentionally broad — any failure = unhealthy."""
        try:
            self._asg.describe_auto_scaling_groups(MaxRecords=1)
            return True
        except Exception:  # noqa: BLE001 — health probe intentionally broad
            return False
