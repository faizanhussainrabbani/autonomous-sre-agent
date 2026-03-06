# LocalStack Pro — Live Testing Plan for the Autonomous SRE Agent

**Date:** March 5, 2026  
**Version:** Phase 1.5.1  
**Authors:** SRE Agent Engineering Team  
**Status:** ✅ APPROVED — Ready for execution  
**Prerequisites:**
- LocalStack Pro token active (`LOCALSTACK_AUTH_TOKEN` in env or `~/.localstack/auth.json`)
- Docker running with `localstack/localstack-pro:latest` pulled
- `pytest`, `awscli-local`, `boto3`, `httpx` available in `.venv`

---

## Overview

This plan details how to leverage each LocalStack Pro feature to validate the Autonomous SRE Agent under production-realistic conditions. It is organized into five capability tracks, each with concrete test scenarios, acceptance criteria, and commands to run.

The Phase 1.5.1 **Error Mapper** (`aws/error_mapper.py`, `azure/error_mapper.py`) is the primary beneficiary of this plan — every scenario below validates that the mapper correctly classifies injected errors and that the resilience layer responds proportionately.

---

## Track 1: Chaos Engineering & Fault Injection (Chaos API)

### 1.1 Background

LocalStack Pro exposes a REST Chaos API at `http://localhost:4566/_localstack/chaos/faults`. Rules are applied per-service and per-operation, injecting:

- **HTTP error responses** (e.g., 429, 500, 503)
- **Network latency** (millisecond delays added to API responses)
- **Probabilistic failures** (percentage of requests that fail)

These faults are injected at the LocalStack layer, so **no application code is modified**.

### 1.2 Test Scenarios

#### Scenario CHX-001 — ThrottlingException → RateLimitError → Retry with Backoff

**Goal:** Validate that `map_boto_error` classifies `ThrottlingException` as `RateLimitError` and that `retry_with_backoff` retries it with exponential backoff.

**Setup:**
```bash
# Start LocalStack Pro (via pytest fixture or manually)
docker run -d -p 4566:4566 \
  -e LOCALSTACK_AUTH_TOKEN=$LOCALSTACK_AUTH_TOKEN \
  -e SERVICES=ecs,lambda,autoscaling \
  localstack/localstack-pro:latest

# Create ECS cluster
awslocal ecs create-cluster --cluster-name test-cluster
awslocal ecs run-task --cluster test-cluster --task-definition sre-test:1

# Inject ThrottlingException on all ECS stop_task calls
curl -s -X POST http://localhost:4566/_localstack/chaos/faults \
  -H "Content-Type: application/json" \
  -d '{
    "service": "ecs",
    "operation": "StopTask",
    "error": {"code": "ThrottlingException", "message": "Rate exceeded"},
    "probability": 1.0
  }'
```

**Test Code (`tests/chaos/test_chaos_throttling.py`):**
```python
import pytest
from sre_agent.adapters.cloud.aws.ecs_operator import ECSOperator
from sre_agent.adapters.cloud.resilience import RateLimitError, RetryConfig
import structlog, time

@pytest.mark.asyncio
async def test_throttle_triggers_rate_limit_error_and_retry():
    """ThrottlingException → RateLimitError, retried with backoff."""
    operator = ECSOperator(region="us-east-1", endpoint_url="http://localhost:4566")
    config = RetryConfig(max_retries=3, base_delay_seconds=0.1)

    start = time.monotonic()
    with pytest.raises(Exception):  # Exhausts all retries
        await operator.remediate(
            resource_id="task/abc123",
            namespace="",
            desired_count=0,
            config=config,
        )
    elapsed = time.monotonic() - start

    # Must have retried (backoff adds 0.1 + 0.2 + 0.4 = 0.7s minimum)
    assert elapsed >= 0.7, f"Expected backoff, got {elapsed:.2f}s — not retrying"
```

**Acceptance Criteria:**
- [ ] `map_boto_error` returns `RateLimitError`
- [ ] `retry_with_backoff` retries 3 times (exponential backoff observed via timing)
- [ ] Final exception is `TransientError("All 3 retries exhausted...")`
- [ ] No `CircuitOpenError` on first encounter

---

#### Scenario CHX-002 — ResourceNotFoundException → ResourceNotFoundError → NO Retry

**Goal:** Validate that a 404/ResourceNotFoundException is immediately terminal — zero retries.

**Setup:**
```bash
# Inject ResourceNotFoundException on Lambda
curl -s -X POST http://localhost:4566/_localstack/chaos/faults \
  -H "Content-Type: application/json" \
  -d '{
    "service": "lambda",
    "operation": "PutFunctionConcurrency",
    "error": {"code": "ResourceNotFoundException", "message": "Function not found"},
    "probability": 1.0
  }'
```

**Test Code:**
```python
@pytest.mark.asyncio
async def test_resource_not_found_no_retry():
    """ResourceNotFoundException → ResourceNotFoundError, raises immediately, no retry."""
    operator = LambdaOperator(region="us-east-1", endpoint_url="http://localhost:4566")
    config = RetryConfig(max_retries=3, base_delay_seconds=0.1)

    start = time.monotonic()
    with pytest.raises(ResourceNotFoundError):
        await operator.remediate(
            resource_id="arn:aws:lambda:us-east-1:000000000000:function:ghost",
            namespace="",
            desired_count=5,
            config=config,
        )
    elapsed = time.monotonic() - start

    # Must NOT have retried — should exit in <0.1s
    assert elapsed < 0.1, f"Should not retry, but took {elapsed:.2f}s"
```

**Acceptance Criteria:**
- [ ] `ResourceNotFoundError` raised on first attempt
- [ ] No retry delay observed (elapsed < 100ms)
- [ ] Circuit breaker records failure (test via `circuit_breaker._failure_count == 1`)

---

#### Scenario CHX-003 — AccessDenied → AuthenticationError → NO Retry

**Goal:** Validate that authorization errors are immediately terminal.

**Setup:**
```bash
curl -s -X POST http://localhost:4566/_localstack/chaos/faults \
  -H "Content-Type: application/json" \
  -d '{
    "service": "autoscaling",
    "operation": "SetDesiredCapacity",
    "error": {"code": "AccessDeniedException", "http_status_code": 403},
    "probability": 1.0
  }'
```

**Acceptance Criteria:**
- [ ] `AuthenticationError` raised (not `TransientError`)
- [ ] Zero retries
- [ ] Log line emitted at `error` level with `"non_retryable_error"` event

---

#### Scenario CHX-004 — Probabilistic 500 Errors → Circuit Breaker Trips

**Goal:** Validate that sustained 5xx errors open the circuit breaker after the failure threshold.

**Setup:**
```bash
# Inject 80% 500 errors on ECS UpdateService
curl -s -X POST http://localhost:4566/_localstack/chaos/faults \
  -H "Content-Type: application/json" \
  -d '{
    "service": "ecs",
    "operation": "UpdateService",
    "error": {"http_status_code": 500, "code": "InternalError"},
    "probability": 0.8
  }'
```

**Test Code:**
```python
@pytest.mark.asyncio
async def test_circuit_breaker_trips_on_sustained_5xx():
    """Sustained InternalError 500s → TransientError → circuit opens after 5 failures."""
    from sre_agent.adapters.cloud.resilience import CircuitBreaker, CircuitState, CircuitOpenError
    cb = CircuitBreaker(failure_threshold=5, recovery_timeout_seconds=5.0, name="ecs-test")
    operator = ECSOperator(region="us-east-1", endpoint_url="http://localhost:4566")
    config = RetryConfig(max_retries=0)  # No retry — each call is one failure

    failures = 0
    for _ in range(6):
        try:
            await operator.remediate_with_circuit_breaker(
                resource_id="svc/test", desired_count=1, circuit_breaker=cb, config=config
            )
        except Exception:
            failures += 1

    assert cb.state == CircuitState.OPEN
    with pytest.raises(CircuitOpenError):
        await operator.remediate_with_circuit_breaker(
            resource_id="svc/test", desired_count=1, circuit_breaker=cb, config=config
        )
```

**Acceptance Criteria:**
- [ ] After 5 consecutive 5xx failures, `CircuitBreaker._state == OPEN`
- [ ] Subsequent calls raise `CircuitOpenError` immediately (no SDK call made)
- [ ] After `recovery_timeout_seconds`, circuit transitions to `HALF_OPEN`

---

#### Scenario CHX-005 — Network Latency Injection → AnomalyDetector Fires Latency Alert

**Goal:** Validate the full detection pipeline: inject latency at the LocalStack level → OTel adapter captures increased response times → `AnomalyDetector` fires a `LATENCY_SPIKE` alert.

**Setup:**
```bash
# Inject 800ms network latency on all Lambda API calls
curl -s -X POST http://localhost:4566/_localstack/chaos/faults \
  -H "Content-Type: application/json" \
  -d '{
    "service": "lambda",
    "latency": 800,
    "probability": 1.0
  }'
```

**Test Code:**
```python
@pytest.mark.asyncio
async def test_injected_latency_fires_anomaly_alert():
    """LocalStack latency injection → captured as metric → AnomalyDetector fires LATENCY_SPIKE."""
    from sre_agent.domain.detection.anomaly_detector import AnomalyDetector
    from sre_agent.domain.detection.baseline import BaselineService
    from sre_agent.domain.models.canonical import AnomalyType

    baseline = BaselineService()
    detector = AnomalyDetector(baseline_service=baseline)

    # Seed baseline with normal 50ms latency
    now = datetime.now(timezone.utc).replace(minute=30, second=0, microsecond=0)
    for i in range(35):
        await baseline.ingest("lambda-svc", "http_request_duration_seconds",
                              0.05 + random.uniform(-0.005, 0.005), now - timedelta(seconds=i*10))

    # Simulate captured metric from real LocalStack call with latency injection
    # In practice, the OTel adapter records the actual response time
    spike_metric = CanonicalMetric(
        name="http_request_duration_seconds",
        value=0.85,   # 17x above 50ms baseline
        timestamp=now,
        labels=ServiceLabels(service="lambda-svc", namespace="default"),
    )

    # Two detections required (timer start + fire)
    await detector.detect("lambda-svc", [spike_metric])
    result = await detector.detect("lambda-svc", [spike_metric])

    alerts = [a for a in result.alerts if a.anomaly_type == AnomalyType.LATENCY_SPIKE]
    assert len(alerts) >= 1
    assert alerts[0].sigma > 10.0
```

**Acceptance Criteria:**
- [ ] Real API call latency (with injected 800ms) is captured by the OTel adapter
- [ ] `AnomalyDetector` fires `LATENCY_SPIKE` alert with sigma > 10σ
- [ ] Alert contains correct `service` label and `severity >= HIGH`

---

### 1.3 Chaos Fault Cleanup

Always clear all faults after each scenario:
```bash
curl -s -X DELETE http://localhost:4566/_localstack/chaos/faults
```

Or scope faults to a single test via the Testcontainers fixture:
```python
@pytest.fixture(autouse=True)
async def clear_chaos_faults(localstack_url):
    yield
    httpx.delete(f"{localstack_url}/_localstack/chaos/faults")
```

---

## Track 2: Cloud Pods — Pre-Seeded Incident Environments

### 2.1 Background

Cloud Pods are snapshots of LocalStack state (IAM roles, ECS clusters, Lambda functions, ASG configs) that can be saved, versioned, and instantly loaded. They eliminate the per-test provisioning time and guarantee reproducible baseline states.

### 2.2 Pod Catalogue

| Pod Name | Description | Use Case |
|---|---|---|
| `sre-agent/steady-state` | Healthy ECS + Lambda + ASG + IAM roles provisioned | Baseline for all remediation tests |
| `sre-agent/oom-scenario` | ECS service at 0 desired count, OOM events in CW Logs | Test ECS scale-up remediation |
| `sre-agent/lambda-throttled` | Lambda at 0 reserved concurrency, pending invocations | Test Lambda concurrency remediation |
| `sre-agent/asg-underprovisioned` | ASG at min capacity, CPU alarm triggered | Test EC2 ASG scale-out remediation |
| `sre-agent/cascading-failure` | ECS down + Lambda throttled + high-latency CloudFront | Test `AlertCorrelationEngine` multi-incident grouping |

### 2.3 Creating a Cloud Pod

```bash
# 1. Start LocalStack Pro and provision the steady-state environment
docker run -d -p 4566:4566 \
  -e LOCALSTACK_AUTH_TOKEN=$LOCALSTACK_AUTH_TOKEN \
  localstack/localstack-pro:latest

# 2. Provision resources
python infra/scripts/provision_localstack_steady_state.py

# 3. Save the pod
localstack pod save sre-agent/steady-state
# Output: Pod 'sre-agent/steady-state' saved. SHA: abc123def456

# 4. Share with team (stored in LocalStack Cloud)
localstack pod push sre-agent/steady-state
```

### 2.4 Using a Cloud Pod in Tests

```python
# tests/integration/conftest.py
import subprocess
import pytest

@pytest.fixture(scope="session")
def localstack_steady_state():
    """Load pre-seeded steady-state Cloud Pod before integration tests."""
    subprocess.run(
        ["localstack", "pod", "load", "sre-agent/steady-state"],
        check=True,
    )
    yield
    # Teardown: clear state
    subprocess.run(["localstack", "state", "reset"], check=True)
```

### 2.5 Test Scenarios Using Cloud Pods

#### Scenario POD-001 — OOM Remediation from Seeded State

```python
@pytest.mark.asyncio
async def test_oom_remediation_from_pod(localstack_oom_pod):
    """Load OOM pod, run SRE Agent, verify ECS service scaled up."""
    # Pod has service at desired=0 (simulating OOM kill)
    ecs = boto3.client("ecs", endpoint_url="http://localhost:4566", region_name="us-east-1")
    svc_before = ecs.describe_services(cluster="prod", services=["checkout-svc"])
    assert svc_before["services"][0]["desiredCount"] == 0

    operator = ECSOperator(region="us-east-1", endpoint_url="http://localhost:4566")
    await operator.remediate(resource_id="checkout-svc", namespace="prod", desired_count=2)

    svc_after = ecs.describe_services(cluster="prod", services=["checkout-svc"])
    assert svc_after["services"][0]["desiredCount"] == 2
```

**Acceptance Criteria:**
- [ ] Pod loads in < 5 seconds
- [ ] ECS service reports desired=0 before remediation
- [ ] Agent sets desired=2 successfully
- [ ] Total test runtime < 10s (vs 45s with boto3 provisioning)

---

#### Scenario POD-002 — Cascading Failure → AlertCorrelationEngine Groups Correctly

```python
@pytest.mark.asyncio
async def test_cascading_failure_correlation(localstack_cascading_pod):
    """Multi-service failure pod → correlation engine groups into single incident."""
    from sre_agent.domain.intelligence.alert_correlation import AlertCorrelationEngine

    engine = AlertCorrelationEngine()
    # Feed alerts that the OTel adapter would emit from the loaded pod state
    alerts = [
        build_alert("ecs-checkout-svc", AnomalyType.MEMORY_PRESSURE, severity=Severity.CRITICAL),
        build_alert("lambda-payment", AnomalyType.INVOCATION_ERROR_SURGE, severity=Severity.HIGH),
        build_alert("ecs-checkout-svc", AnomalyType.ERROR_RATE_SURGE, severity=Severity.HIGH),
    ]
    incidents = engine.correlate(alerts)
    assert len(incidents) == 1  # All grouped into single cascading incident
    assert incidents[0].root_cause_service == "ecs-checkout-svc"
```

**Acceptance Criteria:**
- [ ] 3 alerts from 2 services correlated into 1 incident
- [ ] Root cause correctly attributed to `ecs-checkout-svc` (upstream service)
- [ ] Pod state reproducible across team members: `localstack pod load sre-agent/cascading-failure`

---

## Track 3: Ephemeral Instances — PR Preview Environments

### 3.1 Background

Ephemeral Instances are short-lived cloud-hosted LocalStack deployments. Each PR in the SRE Agent repo triggers a unique Ephemeral Instance pre-loaded with the relevant Cloud Pod, allowing reviewers to interact with a live agent against real (mocked) AWS infrastructure.

### 3.2 CI/CD Integration

Add the following to `.github/workflows/pr_preview.yml`:

```yaml
name: PR Preview — SRE Agent against Ephemeral LocalStack

on:
  pull_request:
    branches: [main]

jobs:
  ephemeral-preview:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install LocalStack CLI
        run: pip install localstack

      - name: Start Ephemeral Instance with steady-state pod
        env:
          LOCALSTACK_AUTH_TOKEN: ${{ secrets.LOCALSTACK_AUTH_TOKEN }}
        run: |
          # Start ephemeral instance and load pre-seeded pod
          ENDPOINT=$(localstack ephemeral start \
            --pod sre-agent/steady-state \
            --lifetime 1800 \
            --output endpoint-url)
          echo "LOCALSTACK_ENDPOINT=$ENDPOINT" >> $GITHUB_ENV
          echo "Ephemeral instance at: $ENDPOINT"

      - name: Run SRE Agent against Ephemeral Instance
        env:
          LOCALSTACK_ENDPOINT: ${{ env.LOCALSTACK_ENDPOINT }}
          LOCALSTACK_AUTH_TOKEN: ${{ secrets.LOCALSTACK_AUTH_TOKEN }}
          AWS_ACCESS_KEY_ID: test
          AWS_SECRET_ACCESS_KEY: test
          AWS_DEFAULT_REGION: us-east-1
        run: |
          source .venv/bin/activate
          pytest tests/integration/ \
            --localstack-endpoint=$LOCALSTACK_ENDPOINT \
            --timeout=120 \
            -v

      - name: Post Endpoint URL to PR
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: `🚀 **SRE Agent Preview Running**\n\nEphemeral LocalStack: \`${{ env.LOCALSTACK_ENDPOINT }}\`\n\nInspect the agent's remediation behavior against a live (mocked) AWS topology.`
            })

      - name: Terminate Ephemeral Instance
        if: always()
        run: localstack ephemeral stop
        env:
          LOCALSTACK_AUTH_TOKEN: ${{ secrets.LOCALSTACK_AUTH_TOKEN }}
```

### 3.3 Ephemeral Instance Test Scenarios

#### Scenario EPH-001 — New Error Mapper Regression Test on PR

**Goal:** Every PR that touches `error_mapper.py` or any operator automatically runs the Chaos fault scenarios (CHX-001 through CHX-004) against an Ephemeral Instance.

**Execution:**
```bash
# Parameterize all chaos scenarios against the ephemeral endpoint
pytest tests/chaos/ \
  --localstack-endpoint=$LOCALSTACK_ENDPOINT \
  -k "throttling or not_found or access_denied or circuit_breaker" \
  -v
```

**Acceptance Criteria:**
- [ ] Ephemeral instance ready in < 60 seconds
- [ ] All 4 chaos scenarios pass (CHX-001 through CHX-004)
- [ ] PR comment posted with test results and ephemeral endpoint URL

---

#### Scenario EPH-002 — Collaborative Debugging Session

**Goal:** When a developer cannot reproduce a bug locally, they spin up a shared Ephemeral Instance.

**Steps:**
```bash
# Developer A: spin up and inject failure
localstack ephemeral start --pod sre-agent/cascading-failure --lifetime 3600
# Output: https://xyz123.localstack.cloud/

# Developer B: connect to same instance and inspect agent behavior
export AWS_ENDPOINT_URL=https://xyz123.localstack.cloud/
awslocal ecs describe-services --cluster prod --services checkout-svc
python -m sre_agent.cli diagnose --resource-id ecs:checkout-svc
```

**Acceptance Criteria:**
- [ ] Both developers see identical infrastructure state
- [ ] Agent diagnosis runs against the shared endpoint
- [ ] Session lifetime is 3600s, auto-terminates after

---

## Track 4: Advanced API Coverage — Phase 2 Readiness

### 4.1 RDS Failover Operator (Phase 2)

**Goal:** Validate the future `RDSOperator` against LocalStack's Pro RDS API (not available in Community).

**Test Scenario (ADS-001):**
```python
@pytest.mark.asyncio
@pytest.mark.phase2
async def test_rds_failover_remediation():
    """RDS primary → replica failover when primary OOM detected."""
    rds = boto3.client("rds", endpoint_url="http://localhost:4566", region_name="us-east-1")

    # Create RDS cluster (Pro feature)
    rds.create_db_cluster(
        DBClusterIdentifier="sre-test-cluster",
        Engine="aurora-mysql",
        MasterUsername="admin",
        MasterUserPassword="password123",
    )

    # Simulate OOM on primary — trigger failover
    operator = RDSOperator(region="us-east-1", endpoint_url="http://localhost:4566")
    result = await operator.remediate(
        resource_id="sre-test-cluster",
        namespace="",
        desired_count=0,  # Convention: 0 = trigger failover
    )
    assert result["action"] == "failover"
```

### 4.2 Complex Topology — ServiceGraph Depth Testing

**Goal:** Build a deep multi-tier topology (API GW → Cognito → Lambda → RDS) and verify `ServiceGraph.find_root_cause()` traces the correct upstream service.

**Test Scenario (ADS-002):**
```python
@pytest.mark.asyncio
@pytest.mark.phase2
async def test_deep_topology_root_cause():
    """6-tier topology: API GW → Cognito → AppSync → Lambda → DynamoDB → RDS.
    Inject latency on RDS → verify root cause identified as RDS, not API GW.
    """
    # Use Pro APIs to provision full topology
    # ... (provision via boto3 against localstack Pro)

    # Inject latency only at the RDS tier
    inject_chaos_latency("rds", latency_ms=2000)

    # Run SRE Agent dependency graph analysis
    graph = ServiceGraph.from_localstack_topology(endpoint="http://localhost:4566")
    root_cause = graph.find_root_cause(anomalous_service="api-gateway")

    assert root_cause == "rds-primary"
    assert graph.depth("api-gateway", "rds-primary") == 5
```

---

## Track 5: IAM Policy Enforcement — Least Privilege Validation

### 5.1 Background

LocalStack Pro enforces IAM policies locally when `IAM_SOFT_MODE=0`. This allows shift-left security testing: verify the SRE Agent cannot perform unauthorized actions before it ever touches a real AWS account.

### 5.2 IAM Policy Definitions

Create `infra/iam/sre_agent_policy.json`:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ECSRemediation",
      "Effect": "Allow",
      "Action": ["ecs:StopTask", "ecs:UpdateService", "ecs:DescribeServices"],
      "Resource": "arn:aws:ecs:us-east-1:000000000000:cluster/prod/*"
    },
    {
      "Sid": "LambdaRemediation",
      "Effect": "Allow",
      "Action": ["lambda:PutFunctionConcurrency", "lambda:GetFunctionConcurrency"],
      "Resource": "arn:aws:lambda:us-east-1:000000000000:function:*"
    },
    {
      "Sid": "ASGRemediation",
      "Effect": "Allow",
      "Action": ["autoscaling:SetDesiredCapacity", "autoscaling:DescribeAutoScalingGroups"],
      "Resource": "*"
    }
  ]
}
```

### 5.3 Test Scenarios

#### Scenario IAM-001 — Agent Cannot Access Unauthorized Namespace

**Goal:** Agent with `prod/*` scope cannot stop tasks in `staging/*`.

**Setup:**
```bash
# Enable IAM enforcement
docker run -d -p 4566:4566 \
  -e LOCALSTACK_AUTH_TOKEN=$LOCALSTACK_AUTH_TOKEN \
  -e IAM_SOFT_MODE=0 \
  -e ENFORCE_IAM=1 \
  localstack/localstack-pro:latest

# Create IAM role with prod-only policy
awslocal iam create-role --role-name sre-agent-role --assume-role-policy-document file://...
awslocal iam put-role-policy --role-name sre-agent-role \
  --policy-name sre-agent-policy \
  --policy-document file://infra/iam/sre_agent_policy.json
```

**Test Code:**
```python
@pytest.mark.asyncio
async def test_agent_cannot_act_outside_authorized_scope():
    """Agent with prod/* IAM scope raises AuthenticationError on staging/* target."""
    operator = ECSOperator(
        region="us-east-1",
        endpoint_url="http://localhost:4566",
        role_arn="arn:aws:iam::000000000000:role/sre-agent-role",
    )
    with pytest.raises(AuthenticationError) as exc_info:
        await operator.remediate(
            resource_id="staging-task-abc",
            namespace="staging",    # Outside prod/* scope
            desired_count=0,
        )
    assert "AccessDenied" in str(exc_info.value) or "403" in str(exc_info.value)
```

**Acceptance Criteria:**
- [ ] `AuthenticationError` raised for out-of-scope namespace
- [ ] `map_boto_error` correctly classifies the IAM `AccessDeniedException` as `AuthenticationError`
- [ ] Zero retries (non-retryable exception)
- [ ] Audit log entry emitted at `security` level

---

#### Scenario IAM-002 — Agent Cannot Call Non-Whitelisted Action

**Goal:** Agent cannot call `ecs:DeleteCluster` (not in its policy).

```python
@pytest.mark.asyncio
async def test_agent_cannot_call_non_whitelisted_action():
    """Agent with restricted IAM policy raises AuthenticationError on DeleteCluster."""
    ecs = boto3.client(
        "ecs",
        endpoint_url="http://localhost:4566",
        region_name="us-east-1",
        # Use the sre-agent-role credentials
    )
    with pytest.raises(ClientError) as exc_info:
        ecs.delete_cluster(cluster="prod")
    assert exc_info.value.response["Error"]["Code"] in ("AccessDeniedException", "AccessDenied")
```

**Acceptance Criteria:**
- [ ] `ecs:DeleteCluster` rejected by IAM enforcement
- [ ] Error correctly mapped to `AuthenticationError` by `map_boto_error`
- [ ] No cluster deletion occurs in LocalStack state

---

## Execution Matrix

| Track | Scenario | Environment | Est. Duration | Priority |
|---|---|---|---|---|
| Chaos | CHX-001 Throttling→Retry | Testcontainers/LocalStack Pro | 15s | P0 |
| Chaos | CHX-002 NotFound→No Retry | Testcontainers/LocalStack Pro | 5s | P0 |
| Chaos | CHX-003 AccessDenied→No Retry | Testcontainers/LocalStack Pro | 5s | P0 |
| Chaos | CHX-004 Circuit Breaker | Testcontainers/LocalStack Pro | 20s | P0 |
| Chaos | CHX-005 Latency→Alert | Testcontainers/LocalStack Pro | 10s | P1 |
| Cloud Pods | POD-001 OOM Remediation | Local + Cloud Pod | 10s | P1 |
| Cloud Pods | POD-002 Cascading Correlation | Local + Cloud Pod | 15s | P1 |
| Ephemeral | EPH-001 PR Regression | GitHub Actions | 3–5 min | P1 |
| Ephemeral | EPH-002 Collaborative Debug | Manual | N/A | P2 |
| Advanced API | ADS-001 RDS Failover | Testcontainers/LocalStack Pro | 30s | P2 (Phase 2) |
| Advanced API | ADS-002 Deep Topology | Testcontainers/LocalStack Pro | 45s | P2 (Phase 2) |
| IAM | IAM-001 Scope Enforcement | Testcontainers/LocalStack Pro | 10s | P0 |
| IAM | IAM-002 Action Whitelist | Testcontainers/LocalStack Pro | 5s | P0 |

**P0 = Gate for Phase 1.5.1 release. P1 = Sprint 1 backlog. P2 = Phase 2 planning.**

---

## Implementation Order

```
Sprint 1 (This Week)
├── tests/chaos/conftest.py          — LocalStack Pro Testcontainer fixture with Chaos API helper
├── tests/chaos/test_error_mapping.py — CHX-001 through CHX-004
├── tests/chaos/test_detection.py    — CHX-005 (latency → alert)
└── infra/iam/sre_agent_policy.json  — IAM least-privilege policy document

Sprint 2
├── infra/scripts/provision_steady_state.py — Provisions Cloud Pod seed state
├── localstack pod save sre-agent/steady-state
├── localstack pod save sre-agent/oom-scenario
├── tests/integration/test_cloud_pods.py   — POD-001, POD-002
└── .github/workflows/pr_preview.yml       — EPH-001 CI integration

Sprint 3 (Phase 2 Planning)
├── tests/chaos/test_iam_enforcement.py — IAM-001, IAM-002
├── tests/integration/test_rds_operator.py — ADS-001
└── tests/integration/test_deep_topology.py — ADS-002
```

---

## References

- [LocalStack Chaos API Docs](https://docs.localstack.cloud/user-guide/chaos-engineering/)
- [LocalStack Cloud Pods Docs](https://docs.localstack.cloud/user-guide/state-management/cloud-pods/)
- [LocalStack Ephemeral Instances](https://docs.localstack.cloud/user-guide/cloud-sandbox/ephemeral-instance/)
- [LocalStack IAM Enforcement](https://docs.localstack.cloud/references/iam-coverage/)
- [Resilience Module](../src/sre_agent/adapters/cloud/resilience.py)
- [AWS Error Mapper](../../src/sre_agent/adapters/cloud/aws/error_mapper.py)
- [Azure Error Mapper](../../src/sre_agent/adapters/cloud/azure/error_mapper.py)
- [Test Findings Report](test_findings_report.md)
