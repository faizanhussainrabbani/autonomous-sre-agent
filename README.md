# 🤖 Autonomous SRE Agent

> An AI-powered reliability engineering system that detects, diagnoses, and safely remediates infrastructure incidents at machine speed.

[![Test Status](https://img.shields.io/badge/tests-passing-brightgreen.svg)](#) 
[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](#)
[![Phase](https://img.shields.io/badge/Phase-1_(Shadow_Mode)-orange.svg)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](#)

## 📖 Overview

Modern SRE teams manage hundreds of microservices. When incidents occur, engineers manually query multiple observability backends, correlate signals, consult post-mortems, and execute runbooks. The **Autonomous SRE Agent** automates this `detect → investigate → diagnose → remediate` pipeline for 5 well-understood incidents (see [Incident Taxonomy](docs/architecture/models/incident_taxonomy.md)) to dramatically reduce Mean Time to Recovery (MTTR).

The agent is built on a **Safety-First, RAG-Grounded** architecture. It relies on structural evidence and strict blast-radius limits rather than LLM self-reported confidence.

---

## ✨ Key Features

*   **Multi-Signal Telemetry:** Ingests and correlates distributed traces, structured logs, metrics (via OpenTelemetry), and deep kernel-level events (via eBPF).
*   **RAG-Grounded Diagnostics:** Embeds anomaly context and searches a Vector Database of historical post-mortems to ground its reasoning, eliminating LLM hallucinations.
*   **GitOps Remediation:** Executes state changes via direct Kubernetes APIs or configuration changes via safe, auditable ArgoCD Git Reverts.
*   **Impenetrable Guardrails:** Three-tiered safety framework (Execution, Knowledge, Security) restricts the agent's blast radius (e.g., "Cannot restart > 20% of fleet").
*   **Multi-Agent Coordination:** Relies on Redis/etcd distributed mutual exclusion locks to prevent conflicts with FinOps or SecOps automated agents.

---

## 🏗️ Repository Structure & Navigation

We follow strict FAANG-standard documentation and specification practices.

*   `docs/`: The "Evergreen" knowledge base. Start here to understand the system.
    *   **[Architecture Guide](docs/architecture/architecture.md)**: High-level system design and technology stack.
    *   **[Operations & Runbooks](docs/operations/operational_readiness.md)**: Runbooks, SLO definitions, and operational readiness.
    *   **[Security & Safety](docs/security/features_and_safety.md)**: Threat modeling and safety guardrail definitions.
    *   **[API Contracts](docs/api/api_contracts.md)**: The strict boundaries of our system.
*   `openspec/`: The Specifications. "Design Docs" and Testable Scenarios (Behavior-Driven Development).
*   `src/`: The Python application source code.
*   `tests/`: Unit and integration test suites.

---

## 🛠️ Technology Stack

The agent aims to be **Provider-Agnostic**, using adapter patterns to interface with various backends.

*   **Core Logic:** Python 3.11+
*   **Observability:** OpenTelemetry (OTLP), eBPF (Cilium/bcc), Prometheus, Jaeger
*   **Intelligence:** LangChain/LlamaIndex, OpenAI/Claude (Primary LLM), Pinecone (Vector RAG)
*   **Action Execution:** Kubernetes Python Client, ArgoCD (GitOps)
*   **Coordination:** Redis (Distributed Locks)

See the full [Technology Stack Guide](docs/architecture/Technology_Stack.md) for details.

---

## 🚀 Quick Start (Local Development)

### Prerequisites
*   Python 3.11 or higher
*   Docker & `k3d` (for local Kubernetes testing)
*   Git

### 1. Environment Setup

```bash
# Clone the repository
git clone https://github.com/your-org/autonomous-sre-agent.git
cd autonomous-sre-agent

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies in development mode
pip install -e ".[dev]"
```

### 2. Running Tests

We strictly adhere to Test-Driven Development based on the scenarios defined in `openspec/`.

```bash
# Run the core unit tests
pytest tests/unit

# Run tests with coverage reporting
pytest --cov=src tests/unit
```

### 3. Local Cluster Simulation (k3d)

To test the agent's interaction with Kubernetes, we use a local `k3d` cluster that includes Prometheus, Jaeger, and Loki pre-configured.

```bash
cd infra/local
./setup.sh
# To tear it down later, run: ./teardown.sh
```

Please refer to the **[Developer Onboarding Guide](docs/project/onboarding.md)** for detailed instructions on spinning up the mock observability stack.

---

## 🗺️ Roadmap: The 4 Phased Rollout

We are systematically rolling out the agent through carefully gated phases to ensure absolute safety.

1.  **Phase 1 (Data Foundation - Current Status):** Shadow mode. The agent ingests telemetry and suggests diagnoses to Slack, but takes *zero* action.
2.  **Phase 1.5 (Compute Agnosticism):** The agent adds adapters for generic cloud compute providers like EC2, ECS, and Lambda instead of only k8s.
3.  **Phase 2 (RAG Diagnostics - Next):** The agent creates GitOps Pull Requests and diagnostics using Vector DBs for humans to review.
4.  **Phase 3 (Autonomous Remediation):** The agent autonomously pushes Sev 3/4 remediations, but escalates Sev 1/2 to humans.

---

## 🤝 Contributing

We welcome contributions! However, because this agent executes production infrastructure actions, our contribution standards are exceptionally strict. 

**Before writing code, you MUST read:**
1.  The [Agent Constitution](.specify/memory/constitution.md)
2.  The [CONTRIBUTING.md](CONTRIBUTING.md) guide.

*Remember: Safety, determinism, and auditability above all else.*

---

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.
