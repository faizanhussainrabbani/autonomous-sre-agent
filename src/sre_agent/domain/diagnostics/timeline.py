"""
Timeline Constructor — chronological signal assembly for LLM context.

Sorts correlated signals (metrics, logs, events) into a human-readable
chronological timeline suitable for injection into LLM prompts.

Phase 2: Intelligence Layer — Sprint 2 (Reasoning & Inference)
"""

from __future__ import annotations

from datetime import datetime

from sre_agent.domain.models.canonical import (
    CanonicalLogEntry,
    CanonicalMetric,
    CorrelatedSignals,
)


class TimelineConstructor:
    """Assembles correlated signals into a chronological timeline string."""

    def __init__(self, max_events: int = 50) -> None:
        self._max_events = max_events

    def build(self, signals: CorrelatedSignals) -> str:
        """Build a chronological timeline from correlated signals.

        Args:
            signals: Correlated metrics, logs, traces, and events.

        Returns:
            A formatted timeline string for LLM prompt injection.
        """
        entries: list[tuple[datetime, str]] = []

        # Metrics
        for m in signals.metrics:
            entries.append((
                m.timestamp,
                f"[METRIC] {m.name}={m.value:.4f} (service={m.labels.service})",
            ))

        # Logs
        for log in signals.logs:
            entries.append((
                log.timestamp,
                f"[LOG:{log.severity}] {log.message} (service={log.labels.service})",
            ))

        # Events
        for evt in signals.events:
            entries.append((
                evt.timestamp,
                f"[EVENT:{evt.event_type}] source={evt.source} {evt.metadata}",
            ))

        # Traces (use root span if available)
        for trace in signals.traces:
            root = trace.root_span
            if root and root.start_time:
                entries.append((
                    root.start_time,
                    f"[TRACE] {root.service}/{root.operation} "
                    f"duration={root.duration_ms:.1f}ms "
                    f"status={root.status_code}",
                ))

        if not entries:
            return "No signals available for timeline construction."

        # Sort chronologically and truncate
        entries.sort(key=lambda e: e[0])
        entries = entries[: self._max_events]

        lines = [
            f"{ts.isoformat()} | {desc}"
            for ts, desc in entries
        ]

        footer = (
            f"\n--- Timeline: {len(entries)} events, "
            f"window {signals.time_window_start.isoformat()} "
            f"to {signals.time_window_end.isoformat()} ---"
        )

        return "\n".join(lines) + footer
