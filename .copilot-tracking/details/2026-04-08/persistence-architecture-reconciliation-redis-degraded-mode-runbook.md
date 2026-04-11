<!-- markdownlint-disable-file -->
# Runbook Draft: Redis Degraded Mode for Coordination and Streams

## Goal

Define degraded-mode behavior for lock, cooldown, stream, and cache responsibilities when Redis is unavailable or latency is unsafe.

## Degradation Classes

* Mode A: Full Redis outage (no key-value, no streams, no pub/sub)
* Mode B: Streams degraded (key-value path healthy, stream lag or stream ops failing)
* Mode C: Coordination degraded (lock/cooldown key path latency or failures)
* Mode D: Persistence risk (AOF/RDB lag indicates durability risk while service appears available)

## Detection Signals

* Redis ping failure on 3 consecutive probes over 90 seconds
* stream_consumer_lag_seconds > 60 seconds for 10 consecutive minutes
* lock acquisition timeout rate > 5% over 5 consecutive minutes
* command latency p95 > 120 ms over 5 consecutive minutes
* Redis memory usage > 75% with consumer lag growth for 10 consecutive minutes
* replication or persistence lag > 120 seconds for 5 consecutive minutes

## Degraded-Mode Actions

1. Disable autonomous remediation execution that requires distributed lock certainty.
2. Force human approval mode for actions touching shared resources.
3. Preserve outbox rows in pending state and pause relay consumers.
4. Continue incident event writes to PostgreSQL event store.
5. Emit high-priority operational alert for coordination degradation.

## Mode-Specific Response

* Mode A:
	* Apply all degraded-mode actions immediately.
	* Broadcast human-override advisory to on-call channel.
* Mode B:
	* Keep lock/cooldown path active if key-value checks are healthy.
	* Pause stream consumers and relay publishing until lag stabilizes.
* Mode C:
	* Disable autonomous actions and lock-dependent orchestration.
	* Keep diagnostic cache reads best-effort; bypass cache writes if unstable.
* Mode D:
	* Keep service active but mark durability state critical.
	* Require manual approval for any action whose audit trail depends on Redis state.

## Recovery Actions

1. Verify Redis health and replication state.
2. Resume outbox relay with backlog drain monitoring.
3. Re-enable lock/cooldown enforcement via Redis backend.
4. Confirm lag and timeout metrics return below thresholds.
5. Exit degraded mode after 15-minute sustained stability window.

## Validation Checks

* No autonomous action executes without lock certainty during degradation.
* Outbox backlog growth is observable and bounded.
* Recovery drains backlog without duplicate side effects.
* Mode-specific safeguards are applied according to detected degradation class.

## Test and Drill Expectations

* Monthly tabletop review of Mode A through Mode D decision paths.
* Quarterly chaos test in staging:
	* Redis full outage simulation
	* Streams-only latency injection
	* Lock path timeout injection
* Post-drill report must capture threshold behavior, false positives, and runbook tuning deltas.

## Exit Criteria

* Redis-dependent coordination controls are restored.
* Backlog and lag metrics are within expected operating range.
* Incident timeline includes degraded-mode and recovery audit entries.
* Stability window (15 minutes) is completed with no threshold re-breach.
