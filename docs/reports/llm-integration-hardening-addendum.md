---
title: LLM Integration Hardening Addendum
description: Concrete hardening tasks derived from current LLM integration observations, with patch points and test cases
author: Autonomous SRE Team
ms.date: 2026-03-17
ms.topic: how-to
keywords:
  - llm
  - hardening
  - timeout
  - observability
  - testing
estimated_reading_time: 12
---

## Objective

This addendum maps current implementation observations to concrete hardening tasks, exact patch points, and test coverage.

## Observation 1: `timeout_seconds` is defined but not enforced

### Why it matters

Without call-level timeouts, provider hangs can hold semaphore slots indefinitely and delay incident diagnosis.

### Patch points

1. `/Users/faizanhussain/Documents/Project/Practice/AiOps/src/sre_agent/adapters/llm/openai/adapter.py`
   - In `generate_hypothesis(...)`, wrap API call with `asyncio.wait_for(..., timeout=self._config.timeout_seconds)`
   - In `validate_hypothesis(...)`, wrap API call with the same timeout
2. `/Users/faizanhussain/Documents/Project/Practice/AiOps/src/sre_agent/adapters/llm/anthropic/adapter.py`
   - In `generate_hypothesis(...)`, wrap `messages.create(...)` with `asyncio.wait_for`
   - In `validate_hypothesis(...)`, wrap `messages.create(...)` with `asyncio.wait_for`
3. Optional centralization:
   - Add helper `_with_timeout(coro)` in each adapter to avoid duplicate timeout wrappers

### Suggested behavior

- On timeout, raise `TimeoutError` (or adapter-specific custom exception) and log structured event including provider, call type, and timeout value.
- Increment `DIAGNOSIS_ERRORS{error_type="timeout"}` through existing pipeline catch path.

### Test cases

1. `tests/unit/adapters/test_openai_llm_adapter.py`
   - `test_generate_hypothesis_times_out`
   - Mock client call to sleep beyond timeout, assert timeout is raised
2. `tests/unit/adapters/test_anthropic_llm_adapter.py`
   - `test_validate_hypothesis_times_out`
3. `tests/unit/adapters/test_throttled_llm_adapter.py`
   - `test_timeout_releases_semaphore_slot`
   - Submit tasks where one times out, verify subsequent queued work proceeds
4. `tests/unit/domain/test_rag_pipeline.py`
   - `test_pipeline_timeout_returns_fallback_result`

## Observation 2: `system_context` exists but is not included in prompt

### Why it matters

The request model allows runtime context injection, but current prompt construction ignores it. This reduces controllability for service-specific constraints.

### Patch points

1. `/Users/faizanhussain/Documents/Project/Practice/AiOps/src/sre_agent/adapters/llm/openai/adapter.py`
   - Update `_build_hypothesis_prompt(request)`:
     - If `request.system_context` is non-empty, append section:
       - `## System Context`
       - raw context text
2. No Anthropic-specific patch required for prompt structure
   - Anthropic adapter reuses OpenAI prompt builders

### Suggested behavior

- Append context as explicit section after `## Service` and before `## Timeline`.
- Preserve compatibility by skipping section when empty.

### Test cases

1. `tests/unit/adapters/test_openai_llm_adapter.py`
   - `test_build_hypothesis_prompt_includes_system_context_when_present`
   - `test_build_hypothesis_prompt_omits_system_context_when_empty`
2. `tests/unit/adapters/test_anthropic_llm_adapter.py`
   - `test_anthropic_uses_shared_hypothesis_prompt_builder`

## Observation 3: queue metrics are defined but not emitted

### Why it matters

`LLM_QUEUE_DEPTH` and `LLM_QUEUE_WAIT` exist in registry but are not updated, so queue contention cannot be monitored.

### Patch points

1. `/Users/faizanhussain/Documents/Project/Practice/AiOps/src/sre_agent/adapters/llm/throttled_adapter.py`
   - Import metrics:
     - `LLM_QUEUE_DEPTH`, `LLM_QUEUE_WAIT`
   - In `_enqueue(...)`:
     - capture enqueue timestamp (monotonic)
     - update `LLM_QUEUE_DEPTH.set(self._queue.qsize())` after put
   - In `_drain_loop(...)`:
     - carry enqueue timestamp in queue tuple
     - after semaphore acquisition, compute queue wait and observe `LLM_QUEUE_WAIT.observe(wait_seconds)`
     - update depth gauge after dequeue
   - In `close()` and cancellation paths:
     - set gauge to current queue size
2. Optional:
   - Add provider/call type labels to queue metrics if cardinality remains stable

### Suggested queue tuple extension

Current tuple:

```python
(priority, seq, fut, coro_func, args)
```

Proposed tuple:

```python
(priority, seq, enqueued_at, fut, coro_func, args)
```

### Test cases

1. `tests/unit/adapters/test_throttled_llm_adapter.py`
   - `test_queue_depth_metric_updates_on_enqueue_and_drain`
   - `test_queue_wait_metric_records_positive_wait_under_contention`
2. `tests/e2e/test_gap_closure_e2e.py`
   - `test_queue_wait_metric_nonzero_when_load_exceeds_cap`

## Additional hardening opportunities

### Structured timeout and provider failure metrics

#### Patch points

- `src/sre_agent/adapters/telemetry/metrics.py`
  - Add `LLM_CALL_ERRORS` counter with labels `provider`, `call_type`, `error_kind`
- OpenAI and Anthropic adapters
  - Increment `LLM_CALL_ERRORS` on API error and timeout paths

#### Test cases

- Adapter unit tests asserting metric increment for timeout, auth error, and transport error paths

### Parse failure consistency

OpenAI parser currently returns fallback objects on JSON decode errors; Anthropic path catches parse exceptions and re-raises only on thrown exceptions.

#### Patch points

- `src/sre_agent/adapters/llm/anthropic/adapter.py`
  - Standardize to OpenAI fallback behavior for malformed payloads if desired

#### Test cases

- `test_anthropic_parse_failure_returns_fallback_validation_result`
- `test_anthropic_parse_failure_increments_metric`

## Proposed delivery plan

1. Timeout enforcement in both adapters
2. Prompt system context integration
3. Queue metrics emission in throttle wrapper
4. New/updated unit tests for each change
5. Optional consistency refinements for parse and error metrics

## Acceptance criteria

- Adapter calls fail fast after configured timeout
- Prompt includes `system_context` when provided
- Queue depth and wait metrics are visible and non-zero under contention
- All new tests pass along with existing throttle and pipeline suites
