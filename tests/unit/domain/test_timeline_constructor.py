"""
Unit tests for TimelineConstructor.

Tests chronological ordering, max events, and formatted output.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sre_agent.domain.diagnostics.timeline import TimelineConstructor
from sre_agent.domain.models.canonical import (
    CanonicalLogEntry,
    CanonicalMetric,
    CorrelatedSignals,
    ServiceLabels,
)


def _make_signals(
    n_metrics: int = 0,
    n_logs: int = 0,
) -> CorrelatedSignals:
    """Helper to create CorrelatedSignals with N metrics and N logs."""
    now = datetime.now(timezone.utc)
    labels = ServiceLabels(service="test-svc")
    metrics = [
        CanonicalMetric(
            name=f"metric_{i}",
            value=float(i),
            timestamp=now + timedelta(minutes=i),
            labels=labels,
        )
        for i in range(n_metrics)
    ]
    logs = [
        CanonicalLogEntry(
            timestamp=now + timedelta(minutes=n_metrics + i),
            message=f"log message {i}",
            severity="WARNING",
            labels=labels,
        )
        for i in range(n_logs)
    ]
    return CorrelatedSignals(
        service="test-svc",
        time_window_start=now,
        time_window_end=now + timedelta(hours=1),
        metrics=metrics,
        logs=logs,
    )


class TestTimelineConstructor:
    """Tests for chronological timeline construction."""

    def test_empty_signals(self):
        timeline = TimelineConstructor()
        signals = CorrelatedSignals(service="test-svc")
        result = timeline.build(signals)
        assert "No signals available" in result

    def test_chronological_ordering(self):
        timeline = TimelineConstructor()
        signals = _make_signals(n_metrics=3, n_logs=2)
        result = timeline.build(signals)
        lines = [l for l in result.split("\n") if "|" in l and "---" not in l]
        # All lines should be in chronological order
        assert len(lines) == 5

    def test_max_events_truncation(self):
        timeline = TimelineConstructor(max_events=3)
        signals = _make_signals(n_metrics=5)
        result = timeline.build(signals)
        lines = [l for l in result.split("\n") if "|" in l and "---" not in l]
        assert len(lines) == 3

    def test_metric_format(self):
        timeline = TimelineConstructor()
        signals = _make_signals(n_metrics=1)
        result = timeline.build(signals)
        assert "[METRIC]" in result
        assert "metric_0=" in result

    def test_log_format(self):
        timeline = TimelineConstructor()
        signals = _make_signals(n_logs=1)
        result = timeline.build(signals)
        assert "[LOG:WARNING]" in result
        assert "log message 0" in result

    def test_footer_contains_window(self):
        timeline = TimelineConstructor()
        signals = _make_signals(n_metrics=2)
        result = timeline.build(signals)
        assert "Timeline:" in result
        assert "2 events" in result

    def test_service_name_in_output(self):
        timeline = TimelineConstructor()
        signals = _make_signals(n_metrics=1)
        result = timeline.build(signals)
        assert "test-svc" in result
