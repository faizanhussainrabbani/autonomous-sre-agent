# LLM Integration Gap Analysis Report

**Date:** 2026-03-17  
**Author:** Autonomous SRE Team  
**Scope:** Comprehensive gap analysis between current LLM integration implementation and documented specifications/best practices.

---

## 1. Context Sent to LLMs (Prompt Engineering)

### Current State
- `_build_hypothesis_prompt` and `_build_validation_prompt` in OpenAI and Anthropic adapters construct prompts using sections like `## Alert`, `## Service`, `## Timeline`,. JSON schema instructions are defined in `HYPOTHESIS_SYSTEM_PROMPT`.
- Token budget is enforced in `RAGDiagnosticPipeline._apply_token_budget`, including evidence in order of relevance until `context_budget` is reached.
- `HypothesisRequest.system_context` exists but is ignored during prompt assembly.
- Evidence context is included but deeper structural topologies (service dependency graph, configuration state) are not explicitly assembled in these prompts.

### Gap Description
- **Missing `system_context`**: Service-specific instructions or operation modes supplied dynamically are discarded, limiting diagnostic controllability.
- **Topological & Historical Context**: The prompt lacks explicit structural elements like the dependency graph or historical pattern data essential for more sophisticated reasoning.

### Recommended Implementation Approach
- In `src/sre_agent/adapters/llm/openai/adapter.py` (which Anthropic shares), update `_build_hypothesis_prompt` to evaluate `request.system_context`. If non-empty, inject a `## System Context` section after `## Service` and before `## Timeline`.
- Extend data models and prompt builders to accept and format `dependency_graph` and `historical_patterns`.

### Priority Level
- **High**: Adding `system_context` is high priority as it fulfills existing design intent. Adding topology is Medium priority for advanced diagnostic accuracy.

---

## 2. Context Received from LLMs (Response Handling)

### Current State
- Both OpenAI and Anthropic adapters parse JSON responses using `_parse_hypothesis` and `_parse_validation`.
- Divergent behavior on parse failure: OpenAI catches the exception, logs a warning, increments `LLM_PARSE_FAILURES`, and returns a safe fallback object. Anthropic delegates to openai parser helpers but often re-raises exceptions.
- Extracts `root_cause`, `confidence`, `reasoning`, `evidence_citations`, `suggested_remediation`. `_normalize_reasoning` handles converting list/strings into numbered text.

### Gap Description
- **Error Handling Inconsistency**: Uncaught parse exceptions from Anthropic can aggressively fail the diagnosis instead of returning a degraded fallback result.
- **Structured Schema Rigidity**: Strict reliance on fenced JSON restricts use cases where an LLM may output non-fenced JSON or use XML tags. Missing extraction guarantees for some citations or action steps if they deviate slightly from the JSON format. 

### Recommended Implementation Approach
- In `src/sre_agent/adapters/llm/anthropic/adapter.py`, standardize fallback behavior. Wrap the parsing logic in `try/except json.JSONDecodeError` block, increment parse failure metrics, and return a default `Hypothesis`/`ValidationResult` with low confidence.
- Consider moving towards native provider structured outputs (like OpenAI's structured outputs via pydantic) rather than pure JSON string parsing.

### Priority Level
- **Critical**: Unifying Anthropic parse failure behavior with OpenAI's fallback mechanism prevents unhandled exceptions from crashing the pipeline.

---

## 3. Industry Best Practices Alignment

### Current State
- OpenAI uses `response_format={"type": "json_object"}`. Anthropic relies on system prompts instructing it to return JSON.
- Timeout (`timeout_seconds`) is configured but not passed to provider API calls.
- XML tags (`<thought>`, `<action>`) and function calling/tools are currently not utilized for chain-of-thought implementations.
- Retries and semantic caching are missing.

### Gap Description
- **Timeouts Not Enforced**: Without call-level timeouts, provider hangs hold semaphore slots indefinitely, blocking the system.
- **Prompting Best Practices**: Anthropic works better with XML tags for structural separation and Chain-of-Thought reasoning. OpenAI function calling is more robust than JSON mode.
- **Resilience**: Lacking exponential backoff and retry logic for transient 5xx/429 errors from LLM providers.

### Recommended Implementation Approach
- In `src/sre_agent/adapters/llm/openai/adapter.py` and `anthropic/adapter.py`, wrap API calls in `asyncio.wait_for(..., timeout=self._config.timeout_seconds)`. On `TimeoutError`, return fallback and log.
- Implement a `@retry(stop=stop_after_attempt(3), wait=wait_exponential())` decorator on the API call functions.
- Evolve prompts to utilize Claude-specific XML tags when targeting the Anthropic adapter.

### Priority Level
- **Critical**: Timeout enforcement is critical to avoid system-wide stalls.
- **Medium**: Adopting specific XML patterns and function calling.

---

## 4. Observability and Instrumentation

### Current State
- Metrics defined in `src/sre_agent/adapters/telemetry/metrics.py` include `LLM_QUEUE_DEPTH` and `LLM_QUEUE_WAIT`, but `ThrottledLLMAdapter` does not emit them.
- Token counts are emitted. OpenAI uses `tiktoken`, Anthropic uses heuristic (`len/4`).
- OpenTelemetry spans and contextvars (`alert_id`) are not propagated fully into the LLM adapter calls.
- Missing `LLM_CALL_ERRORS` metrics.

### Gap Description
- **Missing Queue Metrics**: Queue size and wait times are unobservable, hiding performance degradation and backpressure.
- **Missing Tracing**: Lack of OpenTelemetry spans makes it hard to correlate LLM latency with the underlying anomaly event in distributed tracing backends.
- **Error Observability**: Provider timeouts and transport errors are not categorized in metrics.

### Recommended Implementation Approach
- In `src/sre_agent/adapters/llm/throttled_adapter.py`, include `enqueued_at` timestamp in the queue tuples. Update `LLM_QUEUE_DEPTH.set()` on enqueue/dequeue and observe `LLM_QUEUE_WAIT` upon drain processing.
- Instrument `generate_hypothesis` and `validate_hypothesis` with OpenTelemetry: `with tracer.start_as_current_span(...)`.
- Add `LLM_CALL_ERRORS` counter in metrics registry and increment on failures.

### Priority Level
- **High**: Implementing queue metrics and OTel spans ensures visibility into critical AI agent bottlenecks.
