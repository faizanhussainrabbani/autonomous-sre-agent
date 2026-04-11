"""Cooldown protocol enforcement."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from sre_agent.domain.models.canonical import ComputeMechanism

if TYPE_CHECKING:
    from sre_agent.ports.persistence import CoordinationAuditPort

logger = logging.getLogger(__name__)


class CooldownEnforcer:
    """Tracks cooldown windows to prevent remediation oscillation."""

    def __init__(self, audit: CoordinationAuditPort | None = None) -> None:
        self._cooldowns: dict[str, float] = {}
        self._audit = audit

    async def record_action(
        self,
        resource_id: str,
        compute_mechanism: ComputeMechanism,
        provider: str,
        namespace: str,
        ttl_seconds: int,
        actor_id: str = "sre-agent",
    ) -> str:
        key = self.build_key(
            resource_id=resource_id,
            compute_mechanism=compute_mechanism,
            provider=provider,
            namespace=namespace,
        )
        self._cooldowns[key] = time.time() + ttl_seconds
        await self._audit_cooldown(
            actor_id=actor_id,
            action="set",
            provider=provider,
            compute_mechanism=compute_mechanism,
            resource_id=resource_id,
            ttl_seconds=ttl_seconds,
        )
        return key

    async def is_in_cooldown(
        self,
        resource_id: str,
        compute_mechanism: ComputeMechanism,
        provider: str,
        namespace: str,
        requester_priority: int = 2,
    ) -> tuple[bool, int]:
        key = self.build_key(
            resource_id=resource_id,
            compute_mechanism=compute_mechanism,
            provider=provider,
            namespace=namespace,
        )
        expiry = self._cooldowns.get(key)
        if expiry is None:
            return False, 0
        if requester_priority == 1:
            return False, 0
        remaining = int(expiry - time.time())
        if remaining <= 0:
            self._cooldowns.pop(key, None)
            return False, 0
        return True, remaining

    @staticmethod
    def build_key(
        resource_id: str,
        compute_mechanism: ComputeMechanism,
        provider: str,
        namespace: str,
    ) -> str:
        if compute_mechanism == ComputeMechanism.KUBERNETES:
            resource_type, resource_name = _split_resource(resource_id)
            return f"cooldown:{namespace}:{resource_type}:{resource_name}"
        return f"cooldown:{provider}:{compute_mechanism.name}:{resource_id}"

    async def _audit_cooldown(
        self,
        *,
        actor_id: str,
        action: str,
        provider: str,
        compute_mechanism: ComputeMechanism,
        resource_id: str,
        ttl_seconds: int | None = None,
    ) -> None:
        """Fire-and-forget audit write for cooldown events."""
        if self._audit is None:
            return
        try:
            from sre_agent.ports.persistence import CooldownAuditEntry

            await self._audit.record_cooldown_event(
                CooldownAuditEntry(
                    actor_type=actor_id.rsplit("-", 1)[0] if "-" in actor_id else actor_id,
                    actor_id=actor_id,
                    action=action,
                    provider=provider,
                    compute_mechanism=compute_mechanism.name,
                    resource_id=resource_id,
                    details={
                        "last_actor": actor_id,
                        "action": action,
                        "compute_mechanism": compute_mechanism.name,
                        **({"ttl_seconds": ttl_seconds} if ttl_seconds else {}),
                    },
                )
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "coordination_audit.cooldown_write_failed",
                exc_info=True,
                extra={"action": action, "resource_id": resource_id},
            )


def _split_resource(resource_id: str) -> tuple[str, str]:
    if "/" in resource_id:
        resource_type, resource_name = resource_id.split("/", 1)
        return resource_type, resource_name
    return "resource", resource_id
