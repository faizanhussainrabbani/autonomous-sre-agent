"""
Timeline Constructor — chronological signal assembly for LLM context.

Sorts correlated signals (metrics, logs, events) into a human-readable
chronological timeline suitable for injection into LLM prompts.

Supports anomaly-type-aware filtering to reduce noise in LLM context.

Phase 2: Intelligence Layer — Sprint 2 (Reasoning & Inference)
Phase 2.2: Token Optimization — Smart Timeline Filtering
"""

from __future__ import annotations

from datetime import datetime

from sre_agent.domain.models.canonical import (
    CanonicalLogEntry,
    CanonicalMetric,
    CorrelatedSignals,
)

# Signal relevance map: which keywords matter for which anomaly type.
# Events whose description contains at least one keyword in the set
# are kept; all others are filtered out.
SIGNAL_RELEVANCE: dict[str, set[str]] = {
    "OOM_KILL": {
        "memory", "oom", "pod_restart", "container", "cgroup", "heap",
        "gc", "kill", "restart", "mem_", "rss", "swap",
    },
    "HIGH_LATENCY": {
        "latency", "p99", "p50", "p95", "connection", "queue", "timeout",
        "upstream", "downstream", "duration", "slow", "response_time",
    },
    "ERROR_RATE_SPIKE": {
        "error", "5xx", "4xx", "exception", "panic", "crash", "http",
        "status", "failure", "fault", "500", "503",
    },
    "DISK_EXHAUSTION": {
        "disk", "volume", "inode", "storage", "pvc", "io", "write",
        "read", "capacity", "full", "space",
    },
    "CERT_EXPIRY": {
        "certificate", "tls", "ssl", "expir", "renew", "x509",
        "cert", "https", "pem",
    },
}


class TimelineConstructor:
    """Assembles correlated signals into a chronological timeline string."""

    def __init__(self, max_events: int = 50) -> None:
        self._max_events = max_events

    def build(
        self,
        signals: CorrelatedSignals,
        anomaly_type: str | None = None,
    ) -> str:
        """Build a chronological timeline from correlated signals.

        Args:
            signals: Correlated metrics, logs, traces, and events.
            anomaly_type: Optional anomaly type for relevance filtering.

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

        # Phase 2.2: Apply anomaly-type-aware filtering
        if anomaly_type and anomaly_type in SIGNAL_RELEVANCE:
            relevant_keywords = SIGNAL_RELEVANCE[anomaly_type]
            entries = [
                (ts, desc)
                for ts, desc in entries
                if any(kw in desc.lower() for kw in relevant_keywords)
            ]
            # Fallback: if filtering removed everything, keep all
            if not entries:
                entries = self._collect_all(signals)

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

    def _collect_all(
        self, signals: CorrelatedSignals,
    ) -> list[tuple[datetime, str]]:
        """Collect all signals without filtering (fallback)."""
        entries: list[tuple[datetime, str]] = []
        for m in signals.metrics:
            entries.append((
                m.timestamp,
                f"[METRIC] {m.name}={m.value:.4f} (service={m.labels.service})",
            ))
        for log in signals.logs:
            entries.append((
                log.timestamp,
                f"[LOG:{log.severity}] {log.message} (service={log.labels.service})",
            ))
        for evt in signals.events:
            entries.append((
                evt.timestamp,
                f"[EVENT:{evt.event_type}] source={evt.source} {evt.metadata}",
            ))
        for trace in signals.traces:
            root = trace.root_span
            if root and root.start_time:
                entries.append((
                    root.start_time,
                    f"[TRACE] {root.service}/{root.operation} "
                    f"duration={root.duration_ms:.1f}ms "
                    f"status={root.status_code}",
                ))
        return entries
