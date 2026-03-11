## ADDED Requirements

### Requirement: Evidence Compression Before LLM Submission
The system SHALL compress retrieved evidence chunks before including them in LLM prompts to reduce token consumption while preserving SRE-critical information.

#### Scenario: Compressing runbook evidence for hypothesis generation
- **WHEN** the RAG pipeline retrieves evidence chunks from the vector store
- **THEN** the system SHALL compress each evidence chunk using a token-level compression algorithm
- **AND** the compression SHALL preserve critical SRE terminology (e.g., OOM, kill, latency, p99, deployment, rollback)
- **AND** the compressed evidence SHALL be at least 40% smaller in token count than the original

#### Scenario: Compression port abstraction
- **WHEN** the system compresses evidence
- **THEN** it SHALL use an abstract `CompressorPort` interface
- **AND** the concrete compressor adapter SHALL be injected at runtime

### Requirement: Cross-Encoder Reranking of Retrieved Evidence
The system SHALL rerank vector search results using a cross-encoder model to improve evidence relevance before token budget allocation.

#### Scenario: Reranking after vector search
- **WHEN** the vector store returns top-K results by cosine similarity
- **THEN** the system SHALL rerank the results using a cross-encoder model that evaluates (query, document) pairs
- **AND** keep only the top-N highest-scoring results (N ≤ K)
- **AND** the reranking SHALL use an abstract `RerankerPort` interface

#### Scenario: Reranking improves evidence quality
- **WHEN** the cross-encoder reranker processes retrieved documents
- **THEN** the reranked order MAY differ from the original cosine similarity order
- **AND** the reranked results SHALL have a higher average relevance to the specific alert context

### Requirement: Semantic Caching of Diagnosis Results
The system SHALL cache diagnosis results to avoid redundant LLM calls for recurring incidents.

#### Scenario: Cache hit for recurring incident
- **WHEN** an alert arrives with the same fingerprint (service + anomaly_type + metric) as a recently diagnosed incident
- **AND** the cached result has not expired (configurable TTL, default 4 hours)
- **THEN** the system SHALL return the cached diagnosis without making LLM API calls
- **AND** the cache hit SHALL be logged for observability

#### Scenario: Cache miss for novel combination
- **WHEN** an alert arrives with a fingerprint not present in the cache
- **THEN** the system SHALL proceed with the full RAG diagnostic pipeline
- **AND** store the result in the cache after successful diagnosis

### Requirement: Anomaly-Type-Aware Timeline Filtering
The system SHALL filter timeline signals by relevance to the anomaly type to reduce noise in LLM context.

#### Scenario: OOM incident timeline filtering
- **WHEN** constructing a timeline for an OOM_KILL anomaly
- **THEN** the timeline SHALL include memory, pod restart, container, and OOM-related signals
- **AND** the timeline SHALL exclude unrelated signals (e.g., DNS, certificate, disk)

#### Scenario: Unrecognized anomaly type
- **WHEN** the anomaly type has no defined signal relevance map
- **THEN** the system SHALL include all signals (no filtering) as a safe fallback

### Requirement: Lightweight Validation Prompts
The system SHALL send only citation summaries (not full evidence content) to the validation LLM call.

#### Scenario: Validation with summary-only context
- **WHEN** the second-opinion validator cross-checks a hypothesis
- **THEN** the validation prompt SHALL include the hypothesis and citation snippets (≤150 chars each)
- **AND** SHALL NOT re-send full evidence chunk content
- **AND** the total validation prompt input tokens SHALL be ≤800

### Requirement: Structured Output via Pydantic Models
The system SHALL use Pydantic models for LLM response parsing to eliminate JSON parsing failures.

#### Scenario: Hypothesis response validation
- **WHEN** the LLM returns a hypothesis response
- **THEN** the system SHALL validate the response against a Pydantic model with typed fields
- **AND** if the response does not conform, the system SHALL retry with the same context (up to 2 retries)
- **AND** the JSON schema description SHALL be removed from the system prompt (handled by the structured output mechanism)

### Requirement: Token Usage Observability
The system SHALL expose per-stage token consumption metrics for cost monitoring.

#### Scenario: Token metrics per diagnosis
- **WHEN** a diagnosis completes
- **THEN** the system SHALL record the total input tokens, output tokens, and compression savings
- **AND** the metrics SHALL be available via the existing Prometheus `/metrics` endpoint
