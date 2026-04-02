---
title: Phase 2.9 Completion Closure Acceptance Criteria
description: Measurable pass/fail acceptance criteria for full closure of Phase 2.9 remaining implementation and quality gaps.
ms.date: 2026-04-02
ms.topic: reference
author: SRE Agent Engineering Team
---

## Acceptance criteria matrix

| ID | Plan section | Criterion | Pass condition |
|---|---|---|---|
| AC-P29C-1 | 2.1 | OTel runtime uses resilient log chain | OTel log path composes primary Loki + fallback Kubernetes via `FallbackLogAdapter` |
| AC-P29C-2 | 2.1 | Bootstrap provider path is hardened | `bootstrap_provider()` wraps provider create/activate path with structured error logging and explicit raise semantics |
| AC-P29C-3 | 2.2 | Kubernetes adapter performs bounded concurrent pod log fetch | `query_logs()` reads up to 5 pods concurrently and respects `limit`/`tail_lines` bounds |
| AC-P29C-4 | 2.2 | Kubernetes trace query behavior for unknown service is explicit and tested | `query_by_trace_id()` behavior is deterministic and covered by unit tests |
| AC-P29C-5 | 2.3 | Fallback adapter has no silent exception swallowing | No `except ...: pass` remains in fallback adapter; failures are logged with structured context |
| AC-P29C-6 | 2.4 | CloudWatch log-group resolution is shared | Both `CloudWatchLogsAdapter` and `AlertEnricher` use the same resolver implementation |
| AC-P29C-7 | 2.4 | Resolver order and fallback are preserved | Resolution order remains overrides -> pattern discovery -> Lambda fallback and is test-covered |
| AC-P29C-8 | 2.4 | Enrichment supports ECS-oriented log-group resolution path | Enrichment tests include ECS/log-group discovery scenario |
| AC-P29C-9 | 2.5 | Bridge enrichment toggle has a central source | Bridge derives default enrichment enablement from central `AgentConfig` feature flag |
| AC-P29C-10 | 2.5 | Env override behavior is explicit and safe | `BRIDGE_ENRICHMENT` can override central value and is documented in code behavior |
| AC-P29C-11 | 2.6 | New Relic contract tests use transport-level HTTP mocking | `test_newrelic_log_adapter.py` uses `httpx.MockTransport` pattern |
| AC-P29C-12 | 2.6 | Reusable New Relic response factory exists | `tests/factories/newrelic_responses.py` exists and is used by New Relic log adapter tests |
| AC-P29C-13 | 2.6 | Standalone New Relic adapter coverage command is green | `pytest tests/unit/adapters/telemetry/newrelic/test_newrelic_log_adapter.py --cov=sre_agent.adapters.telemetry.newrelic --cov-report=term-missing` exits 0 |
| AC-P29C-14 | 2.7 | Previously failing diagnostics unit tests are green | Failing tests in `test_pipeline_observability.py` and `test_token_optimization.py` pass |
| AC-P29C-15 | 2.7 | Repository lint gate is green | `bash scripts/dev/run.sh lint` exits 0 |
| AC-P29C-16 | 2.7 | Repository unit gate is green | `bash scripts/dev/run.sh test:unit` exits 0 |
| AC-P29C-17 | 2.7 | Repository coverage gate is green | `bash scripts/dev/run.sh coverage` exits 0 and reports global >= 90% |
| AC-P29C-18 | 2.8 | CloudWatch bootstrap integration verification exists | Integration test validates `TelemetryProviderType.CLOUDWATCH` through `bootstrap_provider()` |
| AC-P29C-19 | 2.8 | Capability review docs reflect resolved runtime behavior | `docs/reports/analysis/log_fetching_capabilities_review.md` reflects active fallback wiring and closure status |
| AC-P29C-20 | 2.8 | OpenSpec Phase 2.9 tasks checklist reflects final state | `openspec/changes/phase-2-9-log-fetching-gap-closure/tasks.md` checkboxes updated accurately |
| AC-P29C-21 | 4.2 | Dependency version guardrails applied | Kubernetes optional dependency uses bounded major range |
| AC-P29C-22 | 4.2 | Bridge and settings defaults remain enrichment-enabled by default | Default execution without explicit override keeps enrichment enabled |
| AC-P29C-23 | 5 | Verification artifact maps all criteria to pass/fail evidence | Verification report includes explicit pass/fail and evidence per criterion |
| AC-P29C-24 | 6 | Run-validation artifact captures end-to-end execution evidence | Validation report includes commands, results, and edge-case outcomes |
| AC-P29C-25 | 7 | Changelog entry is complete and traceable | `CHANGELOG.md` includes change rationale, file impact summary, and references to plan and acceptance criteria docs |

## Edge case coverage requirements

1. Provider bootstrap failures emit structured diagnostics and do not silently mask root cause.
2. Kubernetes API pod-list failures and pod-log failures return safe empty results while preserving service continuity.
3. Fallback behavior covers both primary exceptions and primary empty results.
4. Shared log-group resolution handles unknown service names via deterministic fallback.
5. Enrichment toggle resolution behaves correctly for:
   * no env override
   * `BRIDGE_ENRICHMENT=1`
   * `BRIDGE_ENRICHMENT=0`

## Standards-compliance checks

1. No adapter imports are introduced into `src/sre_agent/domain/` or `src/sre_agent/ports/`.
2. New/updated tests follow naming convention, AAA structure, and async marker usage.
3. Markdown artifacts include required frontmatter and maintain repository writing conventions.
