"""Global kill switch for autonomous remediation."""

from __future__ import annotations

from datetime import datetime, timezone

from sre_agent.domain.models.canonical import DomainEvent, EventTypes
from sre_agent.ports.events import EventBus, EventStore


class KillSwitch:
    """In-memory kill switch state for autonomous action gating."""

    def __init__(self, event_bus: EventBus | None = None, event_store: EventStore | None = None) -> None:
        self._active = False
        self._event_bus = event_bus
        self._event_store = event_store
        self._activated_by = ""
        self._reason = ""
        self._activated_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        return self._active

    async def activate(self, operator_id: str, reason: str) -> None:
        self._active = True
        self._activated_by = operator_id
        self._reason = reason
        self._activated_at = datetime.now(timezone.utc)
        await self._emit(
            DomainEvent(
                event_type=EventTypes.KILL_SWITCH_ACTIVATED,
                payload={
                    "operator_id": operator_id,
                    "reason": reason,
                    "activated_at": self._activated_at.isoformat(),
                },
            ),
        )

    async def deactivate(self, operator_id: str) -> None:
        self._active = False
        await self._emit(
            DomainEvent(
                event_type=EventTypes.KILL_SWITCH_DEACTIVATED,
                payload={"operator_id": operator_id},
            ),
        )

    async def _emit(self, event: DomainEvent) -> None:
        if self._event_store is not None:
            await self._event_store.append(event)
        if self._event_bus is not None:
            await self._event_bus.publish(event)
