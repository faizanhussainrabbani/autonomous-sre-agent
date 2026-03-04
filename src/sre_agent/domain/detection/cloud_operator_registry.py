"""
Cloud Operator Registry — Selects the correct CloudOperatorPort adapter
based on the target service's compute mechanism and cloud provider.

Phase 1.5: Decouples remediation dispatch from provider-specific code.
"""

from __future__ import annotations

from typing import Any

import structlog

from sre_agent.domain.models.canonical import ComputeMechanism
from sre_agent.ports.cloud_operator import CloudOperatorPort

logger = structlog.get_logger(__name__)


class CloudOperatorRegistry:
    """Registry for cloud remediation operator adapters.

    Routes remediation requests to the correct CloudOperatorPort
    implementation based on compute_mechanism and cloud provider.
    """

    def __init__(self) -> None:
        # (provider, mechanism) → CloudOperatorPort
        self._operators: dict[tuple[str, ComputeMechanism], CloudOperatorPort] = {}
        # Fallback: provider → [CloudOperatorPort, ...] for multi-mechanism operators
        self._by_provider: dict[str, list[CloudOperatorPort]] = {}

    def register(self, operator: CloudOperatorPort) -> None:
        """Register an operator for its supported compute mechanisms."""
        provider = operator.provider_name
        for mechanism in operator.supported_mechanisms:
            key = (provider, mechanism)
            self._operators[key] = operator
            logger.info(
                "cloud_operator_registered",
                provider=provider,
                mechanism=mechanism.value,
                operator_type=type(operator).__name__,
            )

        if provider not in self._by_provider:
            self._by_provider[provider] = []
        self._by_provider[provider].append(operator)

    def get_operator(
        self,
        provider: str,
        compute_mechanism: ComputeMechanism,
    ) -> CloudOperatorPort | None:
        """Resolve the correct operator for a provider + mechanism pair.

        Args:
            provider: Cloud provider name ('aws', 'azure').
            compute_mechanism: Target compute type (KUBERNETES, SERVERLESS, etc.).

        Returns:
            The matching CloudOperatorPort, or None if not registered.
        """
        return self._operators.get((provider, compute_mechanism))

    def list_operators(self, provider: str | None = None) -> list[CloudOperatorPort]:
        """List all registered operators, optionally filtered by provider."""
        if provider is not None:
            return list(self._by_provider.get(provider, []))
        all_ops: list[CloudOperatorPort] = []
        for ops in self._by_provider.values():
            all_ops.extend(ops)
        return all_ops

    async def health_check_all(self) -> dict[str, bool]:
        """Run health checks on all registered operators."""
        results: dict[str, bool] = {}
        seen: set[int] = set()
        for operator in self._operators.values():
            if id(operator) in seen:
                continue
            seen.add(id(operator))
            name = f"{operator.provider_name}:{type(operator).__name__}"
            try:
                results[name] = await operator.health_check()
            except Exception as exc:
                results[name] = False
                logger.error("operator_health_check_failed", operator=name, error=str(exc))
        return results
