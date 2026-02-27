"""
Pipeline Health Monitor — monitors the health of the telemetry pipeline itself.

Detects OTel collector failures, eBPF load failures, and late-arriving data.
This is meta-observability: the agent observing its own data pipeline.

Implements: Task 1.6 — Pipeline health monitor
Validates: AC-2.5.1 through AC-2.5.5
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

from sre_agent.domain.models.canonical import DomainEvent, EventTypes
from sre_agent.ports.events import EventBus

logger = structlog.get_logger(__name__)


class PipelineComponentStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"


@dataclass
class ComponentHealth:
    """Health state for a single pipeline component."""
    name: str
    status: PipelineComponentStatus = PipelineComponentStatus.HEALTHY
    last_heartbeat: datetime | None = None
    consecutive_misses: int = 0
    fallback_active: bool = False
    fallback_reason: str | None = None
    affected_services: list[str] = field(default_factory=list)


class PipelineHealthMonitor:
    """Monitors the health of the telemetry ingestion pipeline.

    Tracks:
    - OTel collector heartbeats (AC-2.5.1: detected within 60s)
    - eBPF program status (AC-2.5.3: graceful fallback on incompatibility)
    - Data freshness (AC-2.5.4: late-arriving data handling)
    - Per-service observability status (AC-2.5.2: degraded flag)
    """

    def __init__(
        self,
        event_bus: EventBus | None = None,
        heartbeat_timeout_seconds: int = 60,
    ) -> None:
        self._event_bus = event_bus
        self._heartbeat_timeout = timedelta(seconds=heartbeat_timeout_seconds)
        self._components: dict[str, ComponentHealth] = {}
        self._degraded_services: dict[str, str] = {}  # service → reason
        self._late_data_count: int = 0

    def register_component(self, name: str) -> None:
        """Register a pipeline component for monitoring."""
        self._components[name] = ComponentHealth(
            name=name,
            last_heartbeat=datetime.now(timezone.utc),
        )

    @property
    def components(self) -> dict[str, ComponentHealth]:
        return dict(self._components)

    @property
    def degraded_services(self) -> dict[str, str]:
        return dict(self._degraded_services)

    async def record_heartbeat(self, component: str) -> None:
        """Record a heartbeat from a pipeline component.

        Resets failure counters and clears degraded status.
        """
        if component not in self._components:
            self.register_component(component)

        comp = self._components[component]
        was_degraded = comp.status != PipelineComponentStatus.HEALTHY

        comp.last_heartbeat = datetime.now(timezone.utc)
        comp.consecutive_misses = 0
        comp.status = PipelineComponentStatus.HEALTHY

        if was_degraded:
            logger.info("pipeline_component_recovered", component=component)
            # Clear degraded services that were affected by this component
            services_to_clear = [
                svc for svc, reason in self._degraded_services.items()
                if component in reason
            ]
            for svc in services_to_clear:
                del self._degraded_services[svc]

    async def check_heartbeats(self) -> list[str]:
        """Check all components for missed heartbeats.

        Returns list of components that have missed heartbeats.
        Validates: AC-2.5.1 — failure detected within 60 seconds.
        """
        failed: list[str] = []
        now = datetime.now(timezone.utc)

        for name, comp in self._components.items():
            if comp.last_heartbeat is None:
                continue

            time_since = now - comp.last_heartbeat
            if time_since > self._heartbeat_timeout:
                comp.consecutive_misses += 1

                if comp.status == PipelineComponentStatus.HEALTHY:
                    comp.status = PipelineComponentStatus.DEGRADED
                    logger.warning(
                        "pipeline_heartbeat_missed",
                        component=name,
                        seconds_since_last=time_since.total_seconds(),
                        threshold=self._heartbeat_timeout.total_seconds(),
                    )

                    if self._event_bus:
                        await self._event_bus.publish(
                            DomainEvent(
                                event_type=EventTypes.OBSERVABILITY_DEGRADED,
                                payload={
                                    "component": name,
                                    "status": "degraded",
                                    "seconds_since_heartbeat": time_since.total_seconds(),
                                    "affected_services": comp.affected_services,
                                },
                            )
                        )

                if comp.consecutive_misses >= 3:
                    comp.status = PipelineComponentStatus.DOWN

                failed.append(name)

        return failed

    async def record_ebpf_failure(
        self,
        node: str,
        kernel_version: str,
        error: str,
    ) -> None:
        """Record an eBPF load failure — graceful fallback to OTel-only.

        Validates: AC-2.5.3 — eBPF incompatibility logged with kernel version,
        system falls back to OTel-only mode.
        """
        component_name = f"ebpf-{node}"
        if component_name not in self._components:
            self.register_component(component_name)

        comp = self._components[component_name]
        comp.status = PipelineComponentStatus.DEGRADED
        comp.fallback_active = True
        comp.fallback_reason = (
            f"eBPF load failed on {node} (kernel {kernel_version}): {error}. "
            f"Falling back to OTel-only telemetry."
        )

        logger.warning(
            "ebpf_load_failure",
            node=node,
            kernel_version=kernel_version,
            error=error,
            fallback="otel_only",
        )

        if self._event_bus:
            await self._event_bus.publish(
                DomainEvent(
                    event_type=EventTypes.OBSERVABILITY_DEGRADED,
                    payload={
                        "component": component_name,
                        "type": "ebpf_failure",
                        "node": node,
                        "kernel_version": kernel_version,
                        "error": error,
                        "fallback": "otel_only",
                    },
                )
            )

    async def flag_degraded_observability(
        self,
        service: str,
        reason: str,
    ) -> None:
        """Flag a service as having degraded observability.

        Validates: AC-2.5.2 — affected services flagged.
        """
        self._degraded_services[service] = reason
        logger.warning(
            "service_observability_degraded",
            service=service,
            reason=reason,
        )

    def is_service_degraded(self, service: str) -> bool:
        """Check if a service has degraded observability."""
        return service in self._degraded_services

    async def record_late_data(
        self,
        service: str,
        delay_seconds: float,
        signal_type: str,
    ) -> None:
        """Record late-arriving data.

        Validates: AC-2.5.4 — late data (>60s) still ingested.
        """
        self._late_data_count += 1
        logger.info(
            "late_data_ingested",
            service=service,
            delay_seconds=delay_seconds,
            signal_type=signal_type,
            total_late_count=self._late_data_count,
        )

    def get_health_summary(self) -> dict[str, Any]:
        """Get pipeline health summary."""
        return {
            "components": {
                name: {
                    "status": comp.status.value,
                    "last_heartbeat": (
                        comp.last_heartbeat.isoformat() if comp.last_heartbeat else None
                    ),
                    "consecutive_misses": comp.consecutive_misses,
                    "fallback_active": comp.fallback_active,
                }
                for name, comp in self._components.items()
            },
            "degraded_services": dict(self._degraded_services),
            "late_data_count": self._late_data_count,
            "overall_status": (
                "degraded" if self._degraded_services or
                any(c.status != PipelineComponentStatus.HEALTHY for c in self._components.values())
                else "healthy"
            ),
        }
