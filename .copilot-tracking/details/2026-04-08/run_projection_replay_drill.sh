#!/usr/bin/env bash
set -euo pipefail

# Projection replay drill scaffold for planning-package validation.
# This script is intentionally lightweight and environment-driven.

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "ERROR: DATABASE_URL is required" >&2
  exit 1
fi

if [[ -z "${DRILL_WINDOW_START:-}" || -z "${DRILL_WINDOW_END:-}" ]]; then
  echo "ERROR: DRILL_WINDOW_START and DRILL_WINDOW_END are required" >&2
  exit 1
fi

if ! command -v psql >/dev/null 2>&1; then
  echo "ERROR: psql is required to run this drill scaffold" >&2
  exit 1
fi

echo "Running projection replay drill scaffold"
echo "Window: ${DRILL_WINDOW_START} -> ${DRILL_WINDOW_END}"

# Baseline counts.
baseline_count="$(psql "$DATABASE_URL" -t -A -c "SELECT COUNT(*) FROM incidents;")"
event_count="$(psql "$DATABASE_URL" -t -A -c "SELECT COUNT(*) FROM incident_events WHERE occurred_at >= '${DRILL_WINDOW_START}'::timestamptz AND occurred_at < '${DRILL_WINDOW_END}'::timestamptz;")"

# NOTE:
# Implement environment-specific rebuild execution here.
# Typical implementation:
# 1) snapshot and clone/truncate projection
# 2) replay incident_events in occurred_at order
# 3) recompute incidents projection

# Placeholder integrity checks.
latest_fk_missing="$(psql "$DATABASE_URL" -t -A -c "SELECT COUNT(*) FROM incidents i LEFT JOIN incident_events e ON i.latest_event_id = e.event_id WHERE e.event_id IS NULL;")"

echo "baseline_incidents=${baseline_count}"
echo "window_event_count=${event_count}"
echo "latest_event_fk_missing=${latest_fk_missing}"

if [[ "$latest_fk_missing" != "0" ]]; then
  echo "FAIL: incidents.latest_event_id integrity check failed" >&2
  exit 2
fi

echo "PASS: projection replay drill scaffold checks completed"
