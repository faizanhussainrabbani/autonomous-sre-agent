<!-- markdownlint-disable-file -->
# Runbook Draft: Projection Rebuild and Archive Replay Drill

## Goal

Define a repeatable drill to rebuild incident projection state from incident_events and validate archive replay from retained event exports.

## Preconditions

* incident_events table contains representative lifecycle events
* incidents projection table can be rebuilt from scratch
* archive export sample exists for replay simulation

## Drill Dataset Requirements

* Minimum replay window: 30 days of incident_events.
* Minimum event volume: 100,000 events.
* Minimum incident cardinality: 5,000 distinct incident_id values.
* Include at least one sample for each event class:
  * anomaly.detected
  * diagnosis.generated
  * remediation.started
  * remediation.completed
  * human.override.detected

## Rebuild Procedure

1. Snapshot current incidents projection counts and checksum totals.
2. Truncate or clone projection table in drill environment.
3. Replay ordered incident_events grouped by incident_id and occurred_at.
4. Recompute incidents projection rows and status transitions.
5. Compare rebuilt projection against expected counts and sampled records.

## Archive Replay Procedure

1. Import archived event segment into drill environment.
2. Replay imported events through the same projection rebuild process.
3. Validate continuity for incident status and latest_event_id pointers.
4. Record timing and resource metrics for replay throughput.

## Validation Checks

* Projection parity:
  * row count delta = 0
  * sampled incident status parity = 100%
* Referential integrity:
  * incidents.latest_event_id references existing incident_events rows
* Replay performance:
  * p95 replay latency per event <= 80 ms
  * total rebuild duration <= 45 minutes for baseline drill dataset

## Automation Scaffold

* Execution entrypoint:
  * ./.copilot-tracking/details/2026-04-08/run_projection_replay_drill.sh
* Required environment variables:
  * DATABASE_URL
  * DRILL_WINDOW_START
  * DRILL_WINDOW_END
* Script outputs:
  * row count parity summary
  * sampled status parity summary
  * replay latency summary (p50/p95)
  * non-zero exit code on failed pass/fail checks

## Drill Cadence

* Minimum quarterly execution
* Additional run after schema changes to incident_events, incidents, or outbox processing logic
* Additional run after major index or partition policy changes affecting replay performance

## Exit Criteria

* Drill can restore projection consistency from events only.
* Archive replay succeeds with no data loss in sampled range.
* Findings and remediation actions are recorded in operational report.
* Automation report and command output are attached to the operational report.
