@AGENTS.md

## Purpose

Use this file as the primary context entrypoint when working in this repository with Claude Code.
It provides high-signal project context, coding conventions, and workflows.

Follow this file first, then consult linked architecture and standards documents for deeper detail.

## Project Mission

The Autonomous SRE Agent is an AI-powered reliability system for cloud-native infrastructure.
Its mission is to reduce MTTR by automating the incident loop:

1. Detect anomalies from telemetry.
2. Diagnose likely root causes with retrieval-grounded intelligence.
3. Propose or execute safe remediation actions.
4. Validate outcomes and preserve auditability.

The system targets Kubernetes, AWS, and Azure environments with strict operational safety controls.

## Architecture Overview

The architecture is layered and hexagonal:

* Detection and correlation build canonical incident context.
* Intelligence runs RAG-driven diagnosis and severity classification.
* Action and operator adapters execute infrastructure remediations.
* Orchestration coordinates locks, cooldowns, and policy gates.
* API and CLI expose operational entry points.

Hexagonal architecture is mandatory in src/sre_agent:

* domain/: core business logic and policies.
* ports/: abstract interfaces consumed by the domain.
* adapters/: concrete implementations for external systems.
* api/: FastAPI and CLI entry points.
* config/: settings, logging, and bootstrap wiring.

Dependency direction must stay inward: domain depends on ports, not adapters.

## Key Design Principles

### Multi-agent coordination

The SRE agent operates in a shared ecosystem with SecOps and FinOps agents.
Use deterministic lock semantics, priority preemption, fencing tokens, and cooldown windows.

Priority order:

1. SecOps
2. SRE
3. FinOps

### Human supremacy

Human operators can always override agent behavior.
Autonomous flows must yield to manual intervention, kill-switch activation, and explicit approval gates.

### GitOps integration

Infrastructure changes should be auditable and reproducible.
Prefer GitOps-compatible remediation flows and rollback-safe actions when changing deployment state.

### Safety-first automation

Treat LLM outputs as advisory.
Require policy and guardrail checks before executing remediations.

## Technology Stack

Core platform:

* Python 3.11+
* FastAPI for HTTP API surface
* anyio and httpx for async-first I/O
* structlog for structured logging

Intelligence stack:

* LangChain-style orchestration patterns for RAG workflows
* OpenAI and Anthropic LLM adapters
* Embedding adapters and ChromaDB vector storage
* Token-aware reasoning and evidence reranking pipeline components

Cloud operators:

* Kubernetes operator adapters
* AWS adapters for ECS, EC2 Auto Scaling, and Lambda
* Azure adapters for App Services and Functions

## Codebase Structure

Focus areas to understand quickly:

* src/sre_agent/domain/
  * models/: canonical and diagnosis models
  * detection/: anomaly detection and correlation
  * diagnostics/: RAG pipeline, confidence, severity, timeline
  * remediation/: planning and execution logic
  * safety/: blast radius, guardrails, cooldown, kill switch
* src/sre_agent/ports/
  * cloud_operator.py, llm.py, embedding.py, vector_store.py, diagnostics.py, events.py
* src/sre_agent/adapters/
  * llm/: OpenAI and Anthropic LLM adapters
  * embedding/: sentence-transformer embedding adapter
  * vectordb/: ChromaDB vector store adapter
  * cloud/kubernetes/: Kubernetes operator adapter
  * cloud/aws/: ECS, EC2 ASG, and Lambda operator adapters
  * cloud/azure/: App Service and Functions operator adapters
* src/sre_agent/api/
  * main.py
  * rest/diagnose_router.py
  * rest/events_router.py
  * rest/severity_override_router.py

## Coding Conventions

Follow engineering standards in docs/project/standards/engineering_standards.md.

Mandatory conventions:

* Enforce SOLID principles in new and changed code.
* Keep domain logic isolated from infrastructure dependencies.
* Use Pydantic v2 models for new or refactored domain data models. Do not introduce new dataclass-based domain models.
* Prefer async-first implementations using anyio and httpx.
* Use structured logging with structlog and include relevant operational context.
* Maintain test coverage at or above 90 percent as defined in pyproject.toml.

When changing adapter behavior, preserve contract compatibility with corresponding ports.

## Development Workflow

Common commands:

```bash
bash scripts/dev/setup_deps.sh start
bash scripts/dev/run.sh test:unit
bash scripts/dev/run.sh test:integ      # requires Docker and LocalStack
bash scripts/dev/run.sh test:e2e
bash scripts/dev/run.sh test            # full suite
bash scripts/dev/run.sh lint            # ruff + mypy
bash scripts/dev/run.sh format          # auto-format with ruff
bash scripts/dev/run.sh coverage        # tests with coverage report
bash scripts/dev/run.sh server --reload
```

For LocalStack Pro authentication and container management rules, use docs/testing/localstack_pro_usage_standard.md.

Use docs/getting-started.md for full setup, environment variables, and troubleshooting.

## Environment Variables

Copy .env.example to .env and fill in required values before running the agent.
Never hardcode secrets or API keys in source files. All sensitive configuration must come from environment variables.

## Primary Documents to Consult

Read these first when planning or implementing changes:

* docs/architecture/overview.md
* docs/architecture/layers/intelligence_layer.md
* AGENTS.md
* master_system_document.md

Recommended supporting standards:

* docs/project/standards/engineering_standards.md
* docs/architecture/multi-agent-coordination.md
* docs/getting-started.md

## Commit Conventions

Use conventional commit style: `type(scope): description`

Common types: feat, fix, refactor, test, docs, chore.
Scope should match the affected layer or module (e.g., `domain`, `adapters`, `api`, `scripts`).
Keep the subject line under 72 characters. Use the body for context when the change is non-trivial.

## Working Rules for Claude Code

Before implementation:

1. Identify impacted layer boundaries (domain, port, adapter, API).
2. Confirm whether safety, lock coordination, or human-approval logic is affected.
3. Check related architecture and standards docs before editing.

During implementation:

1. Keep changes minimal, testable, and boundary-safe.
2. Preserve adapter portability across Kubernetes, AWS, and Azure targets.
3. Add or update tests with each behavior change.

Before completion:

1. Run unit tests via scripts/dev/run.sh test:unit.
2. Verify coverage policy remains compliant.
3. Summarize architectural impact and residual risks.