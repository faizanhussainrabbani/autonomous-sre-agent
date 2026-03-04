"""
Cloud Operator Port — Provider-agnostic remediation interface.

Defines the abstract interface for managing compute unit lifecycle
(restart, scale) across different cloud providers and compute mechanisms.

Phase 1.5: Decouples remediation from Kubernetes-specific API calls.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from sre_agent.domain.models.canonical import ComputeMechanism


class CloudOperatorPort(ABC):
    """Abstract interface for cloud remediation operations.

    Concrete adapters (ECSOperator, EC2ASGOperator, LambdaOperator,
    AppServiceOperator, etc.) implement this to manage compute
    lifecycle via their respective cloud SDKs.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Cloud provider identifier (e.g., 'aws', 'azure')."""
        ...

    @property
    @abstractmethod
    def supported_mechanisms(self) -> list[ComputeMechanism]:
        """List of compute mechanisms this operator supports."""
        ...

    @abstractmethod
    async def restart_compute_unit(
        self,
        resource_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Restart a compute unit (ECS Task, App Service, etc.).

        Args:
            resource_id: Universal identifier (ARN, resource URI, etc.).
            metadata: Provider-specific metadata (cluster, resource group, etc.).

        Returns:
            Dict with operation result details.

        Raises:
            NotImplementedError: If restart is not supported for this operator.
        """
        ...

    @abstractmethod
    async def scale_capacity(
        self,
        resource_id: str,
        desired_count: int,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Scale the capacity of a compute target.

        Args:
            resource_id: Universal identifier (service ARN, ASG name, etc.).
            desired_count: New desired instance/task count.
            metadata: Provider-specific metadata.

        Returns:
            Dict with operation result details.
        """
        ...

    def is_action_supported(
        self,
        action: str,
        compute_mechanism: ComputeMechanism,
    ) -> bool:
        """Check if an action is supported for a given compute mechanism.

        Args:
            action: Action name ('restart', 'scale').
            compute_mechanism: Target compute type.

        Returns:
            True if the action is supported.
        """
        return compute_mechanism in self.supported_mechanisms

    @abstractmethod
    async def health_check(self) -> bool:
        """Validate connectivity to the cloud provider.

        Returns:
            True if the operator can reach its backing service.
        """
        ...
