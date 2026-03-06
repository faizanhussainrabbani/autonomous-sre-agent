## ADDED Requirements

### Requirement: Vector Embedding and Retrieval
The system SHALL embed incoming alerts as vectors and perform semantic similarity search against a vector database containing historical incidents, post-mortems, and runbooks.

#### Scenario: Alert triggers RAG retrieval
- **WHEN** an anomaly alert is generated for a service
- **THEN** the system SHALL embed the alert context (service name, error type, affected metrics, time window) as a vector
- **AND** retrieve the top-K most semantically similar historical incidents from the vector database
- **AND** each retrieved document SHALL include a similarity score

#### Scenario: No relevant historical data found
- **WHEN** the similarity search returns no documents above the configured similarity threshold
- **THEN** the system SHALL classify the incident as "novel"
- **AND** the incident SHALL be escalated to a human responder with all available telemetry context

### Requirement: Evidence-Based Root Cause Diagnosis
The system SHALL generate root cause hypotheses grounded in retrieved historical evidence, not pure LLM generation.

#### Scenario: Diagnosis with strong RAG evidence
- **WHEN** the RAG pipeline retrieves a historical post-mortem with similarity score above threshold
- **AND** the LLM generates a root cause hypothesis referencing the retrieved evidence
- **THEN** the diagnosis SHALL include citations to the specific documents used
- **AND** the evidence-weighted confidence score SHALL factor in trace correlation, timeline match, and retrieval quality

#### Scenario: Diagnosis with weak or conflicting evidence
- **WHEN** retrieved documents provide conflicting root cause indicators
- **THEN** the system SHALL present multiple hypotheses ranked by evidence-weighted confidence
- **AND** if no hypothesis exceeds the minimum confidence threshold the system SHALL escalate to a human responder

### Requirement: Chronological Event Timeline Construction
The system SHALL construct a chronological timeline of events leading up to and during the incident.

#### Scenario: Timeline for deployment-correlated incident
- **WHEN** an incident is detected within 60 minutes of a deployment
- **THEN** the timeline SHALL include the deployment event, configuration changes, metric shifts, log entries, and alert triggers in chronological order
- **AND** the timeline SHALL highlight temporal correlations between the deployment and the anomaly onset

### Requirement: Second Opinion Validation
The system SHALL cross-check the primary agent's diagnosis using a separate validator before authorizing remediation actions.

#### Scenario: Primary and validator agree on diagnosis
- **WHEN** the primary LLM agent and the secondary validator produce consistent root cause hypotheses
- **THEN** the system SHALL proceed with remediation planning
- **AND** the agreement SHALL be logged with both agents' reasoning

#### Scenario: Primary and validator disagree
- **WHEN** the primary LLM agent and the secondary validator produce conflicting diagnoses
- **THEN** the system SHALL NOT proceed with autonomous remediation
- **AND** the incident SHALL be escalated to a human responder with both diagnoses presented

### Requirement: Provenance Tracking
The system SHALL maintain a full audit trail of which documents, data sources, and reasoning steps were used to reach each diagnosis.

#### Scenario: Provenance query after incident resolution
- **WHEN** an operator reviews a resolved incident
- **THEN** the system SHALL display the exact post-mortems, runbooks, and telemetry queries that informed the diagnosis
- **AND** the reasoning chain from evidence to conclusion SHALL be fully inspectable

### Requirement: Embedding Strategy and Document Chunking
The system SHALL standardize the embedding model, dimensionality, and chunking strategy for vectorizing historical incidents and runbooks.

#### Scenario: Document ingestion and chunking
- **WHEN** a new post-mortem or runbook is added to the knowledge base
- **THEN** the system SHALL chunk the document using semantic boundaries (e.g., Markdown headers) rather than strict token counts
- **AND** the vectors SHALL be generated using a configurable embedding model (defaulting to `sentence-transformers` for development, structured via a `VectorStorePort`)
- **AND** the vector representations SHALL be updated on a 90-day rolling cadence to prevent TTL staleness

### Requirement: LLM Prompt Engineering and Token Budgets
The system SHALL strictly define LLM prompt templates, enforce token budgets per diagnosis, and handle rate-limiting fallbacks.

#### Scenario: Enforcing token budgets during RAG formulation
- **WHEN** constructing the context window for a root cause hypothesis request
- **THEN** the system SHALL allocate a strict token budget (e.g., max 4000 tokens for context)
- **AND** prioritize the most recent, highest-similarity evidence blocks if the context size exceeds the budget
- **AND** include specific system instructions demanding structured output with mandatory confidence score and exact evidence citations

#### Scenario: Handling LLM rate limits and fallbacks
- **WHEN** the primary LLM provider (e.g., OpenAI/Anthropic) returns a 429 RateLimitExceeded or 503 ServiceUnavailable
- **THEN** the system SHALL implement exponential backoff
- **AND** if retries are exhausted within the configured SLA (e.g., 30s), transition gracefully to a degraded state
- **AND** escalate the incident to a human without hallucinating a low-confidence diagnosis

### Requirement: Intelligence Layer Port Interfaces
The system SHALL implement the Intelligence Layer strictly through abstract Port definitions, preserving the Hexagonal Architecture and Dependency Inversion.

#### Scenario: Swapping vector databases or LLM providers
- **WHEN** the system orchestrates the RAG diagnostic pipeline
- **THEN** it SHALL rely exclusively on abstract ports (`DiagnosticPort`, `VectorStorePort`, `LLMReasoningPort`)
- **AND** the concrete adapters (e.g., ChromaDB, OpenAI, Anthropic, Pinescone) SHALL be injected at runtime via the bootstrap configuration
