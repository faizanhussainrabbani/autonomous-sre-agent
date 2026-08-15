# External Dependencies Guide

> All external services, tools, and infrastructure needed to develop, test, and run the SRE Agent locally.

---

## Quick Reference

| Dependency | Required For | Default Port | Install Method |
|---|---|---|---|
| **Docker** | Integration/E2E tests, dep services | — | [docker.com](https://docs.docker.com/get-docker/) |
| **PostgreSQL** | Persistence store (incident lifecycle, outbox, vector metadata) | 5434 | Docker (via `docker-compose.deps.yml`) or Homebrew |
| **Redis** | Distributed locks and Redis Streams event bus | 6379 | Docker (via `docker-compose.deps.yml`) or Homebrew |
| **LocalStack Pro** | AWS integration tests | 4566 | Docker (via `docker-compose.deps.yml`) |
| **Prometheus** | Metric queries, OTel adapter tests | 9090 | Docker (via `docker-compose.deps.yml`) |
| **Jaeger** | Trace ingestion tests | 16686 | Docker (via `docker-compose.deps.yml`) |
| **ChromaDB** | Vector store (RAG diagnostics) | Embedded | `pip install chromadb` (included in `[intelligence]`) |
| **OpenAI API** | LLM hypothesis generation | — | API key in `.env` |
| **Anthropic API** | Alternative LLM provider | — | API key in `.env` |
| **k3d + Colima** | Local Kubernetes cluster (Phase 3+) | 8080 | `brew install k3d colima` |

---

## Starting Dependencies

The fastest way to start all development dependencies:

```bash
# Start PostgreSQL, Redis, LocalStack, Prometheus, Jaeger
../../scripts/dev/setup_deps.sh start

# Check health
../../scripts/dev/setup_deps.sh health

# Stop everything
../../scripts/dev/setup_deps.sh stop
```

This uses `docker-compose.deps.yml` in the project root.

Local connection strings:

* PostgreSQL: `postgresql://test:test@localhost:5434/sre_demo`
* Redis: `redis://localhost:6379/0`

---

## Dependency Details

### 1. Docker

**Required:** Yes (for integration tests and development services)

Docker is required to run LocalStack, Prometheus, Jaeger, and other containerized services.

```bash
# macOS
brew install --cask docker

# Verify
docker --version
docker compose version
```

---

### 2. PostgreSQL

**Required:** For persistence mode (`persistence.enabled: true`)

PostgreSQL is the primary durable store for incident lifecycle events, outbox
delivery state, coordination audit entries, and vector metadata.

**Local credentials (default):**

* user: `test`
* password: `test`
* database: `sre_demo`
* host: `localhost`
* port: `5434`

**Connection strings:**

* `postgresql://test:test@localhost:5434/sre_demo`
* `postgresql+asyncpg://test:test@localhost:5434/sre_demo`

All demo, E2E, and migration flows must use this exact database target. Any other Postgres host, port, user, or database name is treated as a configuration error.

**Note:** pgvector support is automatic when the extension is available; the
migration layer falls back to JSONB vector storage when it is not.

---

### 3. Redis

**Required:** For Redis lock backend and Redis Streams event bus backend

Redis is used for distributed lock coordination and optional event streaming.

**Connection URL:**

* `redis://localhost:6379/0`

---

### 4. LocalStack Pro

**Required:** For integration tests (`test_chaos_specs.py`, `test_iam_specs.py`, `test_pod_specs.py`)

LocalStack emulates AWS APIs locally so integration tests can exercise real ECS, EC2, Lambda, IAM, S3, and SecretsManager operations without hitting AWS.

**Setup:**
1. Get a Pro token at [app.localstack.cloud](https://app.localstack.cloud)
2. Add to `.env`:
   ```
   LOCALSTACK_AUTH_TOKEN=<LOCALSTACK_AUTH_TOKEN>
   ```
3. Start via Docker Compose:
   ```bash
   ../../scripts/dev/setup_deps.sh start
   ```

**Verification:**
```bash
# Health check
curl http://localhost:4566/_localstack/health

# List available services
curl http://localhost:4566/_localstack/health | python3 -m json.tool
```

**Which tests need it:**
- `tests/integration/test_chaos_specs.py` — fault injection scenarios
- `tests/integration/test_iam_specs.py` — IAM scope enforcement
- `tests/integration/test_pod_specs.py` — cloud pod operations

---

### 5. ChromaDB (Vector Store)

**Required:** For Phase 2 RAG diagnostics pipeline

ChromaDB is the default vector database for storing and searching embedded documents (post-mortems, runbooks). It runs **embedded in-process** — no separate server needed.

**Installation:**
```bash
pip install -e ".[intelligence]"    # includes chromadb
# or: pip install chromadb
```

**Usage:** Automatically created in-memory by `intelligence_bootstrap.py`. For persistent storage, set `persist_directory` when calling `create_vector_store()`.

---

### 6. LLM APIs (OpenAI / Anthropic)

**Required:** For live LLM hypothesis generation

The Intelligence Layer uses LLM APIs for:
- Root cause hypothesis generation
- Cross-validation (second opinion)

**Setup:**
```bash
# In .env:
OPENAI_API_KEY=<OPENAI_API_KEY>
# OR
ANTHROPIC_API_KEY=<ANTHROPIC_API_KEY>
```

**Auto-detection:** The `intelligence_bootstrap.py` module detects which API key is set:
- If `ANTHROPIC_API_KEY` is set → uses Anthropic (Claude)
- If `OPENAI_API_KEY` is set → uses OpenAI (GPT-4o-mini)
- If neither → defaults to OpenAI (will fail on API call without a key)

**Note:** Unit tests don't require real API keys — they use mocked LLM adapters. Only live demos and E2E tests with `--live` flag need real keys.

---

### 7. Prometheus

**Required:** For OTel adapter tests and metric querying

Prometheus collects and queries time-series metrics from the agent.

**Setup:**
```bash
../../scripts/dev/setup_deps.sh start   # starts Prometheus on port 9090
```

**Configuration:** The Prometheus config file lives at `infra/prometheus/prometheus.yml`. The Docker Compose file mounts this automatically.

**UI:** http://localhost:9090

---

### 8. Jaeger

**Required:** For distributed trace ingestion and querying

Jaeger receives OTLP traces from the OTel Collector and provides distributed trace visualization.

**Setup:**
```bash
../../scripts/dev/setup_deps.sh start   # starts Jaeger on port 16686
```

**Ports:**
- `16686` — Jaeger UI
- `4317` — OTLP gRPC receiver
- `4318` — OTLP HTTP receiver

**UI:** http://localhost:16686

---

### 9. k3d + Colima (Phase 3+)

**Required:** For Kubernetes remediation testing (Phase 3)

k3d creates lightweight Kubernetes clusters running inside Docker. Colima provides the Linux VM on macOS with eBPF-capable kernel support.

**Installation:**
```bash
brew install k3d colima kubectl helm
```

**Setup:** Use the existing eBPF development environment script:
```bash
./infra/local/setup.sh     # creates k3d cluster, deploys OTel + sample services
./infra/local/teardown.sh  # tears down everything
```

> [!NOTE]
> k3d/Colima are not needed for Phase 1–2 development. They become relevant in Phase 3 (Autonomous Remediation) when the agent needs to interact with Kubernetes APIs.

---

## Test Dependency Matrix

| Test Suite | Docker | LocalStack | LLM Key | k3d |
|---|---|---|---|---|
| `tests/unit/` | ❌ | ❌ | ❌ | ❌ |
| `tests/e2e/test_phase2_e2e.py` | ❌ | ❌ | ❌ | ❌ |
| `tests/integration/test_chaos_specs.py` | ✅ | ✅ | ❌ | ❌ |
| `tests/integration/test_iam_specs.py` | ✅ | ✅ | ❌ | ❌ |
| `tests/e2e/test_realworld_scenarios_e2e.py` | ❌ | ❌ | ❌ | ❌ |
| `../../scripts/demo/live_demo_*.py` | ❌ | ❌ | ✅ | ❌ |

---

## Troubleshooting

### LocalStack not starting
```bash
# Check if the port is already in use
lsof -i :4566

# Check LocalStack logs
docker logs sre-localstack
```

### ChromaDB import errors
```bash
# Ensure the intelligence extras are installed
pip install -e ".[intelligence]"
```

### Docker Compose version mismatch
```bash
# Requires Docker Compose v2 (docker compose, not docker-compose)
docker compose version  # Should show v2.x
```
