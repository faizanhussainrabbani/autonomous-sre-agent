# 🤖 Autonomous SRE Agent

> An AI-powered reliability engineering system that detects, diagnoses, and safely remediates infrastructure incidents at machine speed.

[![Test Status](https://img.shields.io/badge/tests-496%20passing-brightgreen.svg)](#) 
[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](#)
[![Phase](https://img.shields.io/badge/Phase-2_(Intelligence_Layer)-blueviolet.svg)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](#)

## 📖 Overview

Modern SRE teams manage hundreds of microservices. When incidents occur, engineers manually query multiple observability backends, correlate signals, consult post-mortems, and execute runbooks. The **Autonomous SRE Agent** automates this `detect → investigate → diagnose → remediate` pipeline for 5 well-understood incidents (see [Incident Taxonomy](docs/architecture/models/incident_taxonomy.md)) to dramatically reduce Mean Time to Recovery (MTTR).

The agent is built on a **Safety-First, RAG-Grounded** architecture. It relies on structural evidence and strict blast-radius limits rather than LLM self-reported confidence.

---

## ✨ Key Features

*   **Multi-Signal Telemetry:** Ingests and correlates distributed traces, structured logs, metrics (via OpenTelemetry), and deep kernel-level events (via eBPF).
*   **RAG-Grounded Diagnostics:** Embeds anomaly context and searches a Vector Database of historical post-mortems to ground its reasoning, eliminating LLM hallucinations.
*   **Multi-Dimensional Severity Classification:** Automated Sev 1–4 assignment using weighted impact scoring across user impact, blast radius, service tier, financial impact, and reversibility.
*   **Multi-Cloud Support:** Provider-agnostic adapters for AWS (ECS, EC2, Lambda), Azure (App Service, Functions), and Kubernetes via hexagonal architecture.
*   **Impenetrable Guardrails:** Three-tiered safety framework (Execution, Knowledge, Security) restricts the agent's blast radius (e.g., "Cannot restart > 20% of fleet").
*   **Multi-Agent Coordination:** Redis/etcd distributed mutual exclusion locks prevent conflicts with FinOps or SecOps automated agents.

---

## 🚀 Quick Start

### Prerequisites

*   Python 3.11+
*   Docker (for integration tests)
*   Git

### 1. Setup

```bash
# Clone and enter the project
git clone https://github.com/your-org/autonomous-sre-agent.git
cd autonomous-sre-agent

# Install everything (creates venv if needed)
/Users/faizanhussain/Documents/Project/Practice/AiOps/scripts/dev/run.sh setup

# Configure environment variables
cp .env.example .env
# Edit .env with your API keys (OPENAI_API_KEY or ANTHROPIC_API_KEY)
```

### 2. Run the API Server

```bash
/Users/faizanhussain/Documents/Project/Practice/AiOps/scripts/dev/run.sh server            # Production mode
/Users/faizanhussain/Documents/Project/Practice/AiOps/scripts/dev/run.sh server --reload   # Dev mode with auto-reload
```

API docs available at http://localhost:8080/docs

### 3. Run Tests

```bash
/Users/faizanhussain/Documents/Project/Practice/AiOps/scripts/dev/run.sh test:unit    # Unit tests (~400 tests, fast, no deps)
/Users/faizanhussain/Documents/Project/Practice/AiOps/scripts/dev/run.sh test:e2e     # E2E tests
/Users/faizanhussain/Documents/Project/Practice/AiOps/scripts/dev/run.sh test         # Full suite (501 tests)
/Users/faizanhussain/Documents/Project/Practice/AiOps/scripts/dev/run.sh coverage     # Tests with coverage report
```

### 4. Start External Dependencies

```bash
# Start LocalStack, Prometheus, Jaeger via Docker
/Users/faizanhussain/Documents/Project/Practice/AiOps/scripts/dev/setup_deps.sh start

# Run integration tests (requires LocalStack Pro)
/Users/faizanhussain/Documents/Project/Practice/AiOps/scripts/dev/run.sh test:integ

# Stop dependencies
/Users/faizanhussain/Documents/Project/Practice/AiOps/scripts/dev/setup_deps.sh stop
```

See the full [External Dependencies Guide](docs/operations/external_dependencies.md) for details.

---

## 🏗️ Repository Structure

```
├── src/sre_agent/           # Application source code
│   ├── api/                 # FastAPI server + CLI
│   ├── adapters/            # External integrations (LLM, VectorDB, Cloud, Telemetry)
│   ├── config/              # Settings, logging, YAML loading
│   ├── domain/              # Core business logic (detection, diagnostics)
│   ├── events/              # Event bus + event store
│   └── ports/               # Abstract interfaces (Hexagonal Architecture)
├── tests/                   # Unit, integration, E2E test suites
├── docs/                    # Full documentation (see docs/README.md)
├── openspec/                # Design specs and BDD scenarios
├── scripts/                 # Run scripts and demo scenarios
├── infra/                   # Kubernetes manifests, Prometheus config
├── config/                  # Agent YAML configuration
├── .env.example             # Environment variable template
└── docker-compose.deps.yml  # Development dependency services
```

*   **[Documentation Index](docs/README.md)** — Full index of all project documentation.
*   **[Architecture Guide](docs/architecture/architecture.md)** — System design and hexagonal layer overview.
*   **[API Contracts](docs/api/api_contracts.md)** — REST and event API schemas.
*   **[External Dependencies](docs/operations/external_dependencies.md)** — What you need to run locally.

---

## 🛠️ Technology Stack

*   **Core Logic:** Python 3.11+, Pydantic, structlog
*   **API:** FastAPI, Uvicorn
*   **Observability:** OpenTelemetry (OTLP), eBPF (Cilium/bcc), Prometheus, Jaeger
*   **Intelligence:** OpenAI (GPT-4o-mini) / Anthropic (Claude), ChromaDB (Vector Store), SentenceTransformers (Embeddings)
*   **Cloud Operators:** AWS (boto3) — ECS, EC2, Lambda | Azure (azure-mgmt) — App Service, Functions | Kubernetes
*   **Coordination:** Redis (Distributed Locks)
*   **Testing:** pytest, LocalStack Pro, Testcontainers

See the full [Technology Stack Guide](docs/architecture/Technology_Stack.md) for details.

---

## 🗺️ Roadmap

| Phase | Status | Description |
|---|---|---|
| **Phase 1: Data Foundation** | ✅ Complete | Telemetry ingestion, anomaly detection, canonical data models |
| **Phase 1.5: Cloud Portability** | ✅ Complete | AWS/Azure cloud operator adapters, resilience patterns |
| **Phase 2: Intelligence Layer** | ✅ Complete | RAG diagnostics, LLM reasoning, severity classification |
| **Phase 3: Autonomous Remediation** | 🔲 Next | GitOps remediation, Kubernetes actions, human-in-the-loop |
| **Phase 4: Predictive** | 🔲 Planned | Proactive scaling, architectural recommendations |

---

## 🤝 Contributing

We welcome contributions! Because this agent executes production infrastructure actions, our contribution standards are strict.

**Before writing code, read:**
1.  The [Agent Constitution](.specify/memory/constitution.md)
2.  The [CONTRIBUTING.md](CONTRIBUTING.md) guide.

*Safety, determinism, and auditability above all else.*

---

## 📄 License

This project is licensed under the MIT License — see the LICENSE file for details.
