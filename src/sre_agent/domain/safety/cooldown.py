"""Cooldown protocol enforcement."""

from __future__ import annotations

import time

from sre_agent.domain.models.canonical import ComputeMechanism


class CooldownEnforcer:
    """Tracks cooldown windows to prevent remediation oscillation."""

    def __init__(self) -> None:
        self._cooldowns: dict[str, float] = {}

    def record_action(
        self,
        resource_id: str,
        compute_mechanism: ComputeMechanism,
        provider: str,
        namespace: str,
        ttl_seconds: int,
    ) -> str:
        key = self.build_key(
            resource_id=resource_id,
            compute_mechanism=compute_mechanism,
            provider=provider,
            namespace=namespace,
        )
        self._cooldowns[key] = time.time() + ttl_seconds
        return key

    def is_in_cooldown(
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


def _split_resource(resource_id: str) -> tuple[str, str]:
    if "/" in resource_id:
        resource_type, resource_name = resource_id.split("/", 1)
        return resource_type, resource_name
    return "resource", resource_id
