# LocalStack Pro Integration Guide

**Status:** APPROVED  
**Target Audience:** SRE Agent Contributors, QA  

This guide provides precise, actionable instructions on leveraging **LocalStack Pro** to test the Autonomous SRE Agent's interactions with AWS services (EC2 ASG, ECS, Lambda) locally, without requiring actual AWS cloud resources or incurring costs.

---

## 1. Why LocalStack Pro?

The SRE Agent integrates deeply with AWS APIs (e.g., autoscaling capacities, stopping ECS tasks). The open-source (Community) edition of LocalStack does not support advanced emulation of:
- EC2 Auto Scaling Groups (ASG)
- Elastic Container Service (ECS)
- Advanced Lambda execution environments

To ensure our integration tests (`tests/integration/test_aws_operators_integration.py`) accurately validate the agent's behavior, we strictly require **LocalStack Pro**.

---

## 2. Prerequisites & Authentication

To run the integration tests locally, you must first authenticate your environment with a valid LocalStack Pro license.

### Step 2.1: Obtain the License
You must acquire a `LOCALSTACK_AUTH_TOKEN`. Contact the team lead if you do not have one.

### Step 2.2: Configure the Token
The test suite automatically resolves the token using one of two methods (checked in order):

**Method A: Environment Variable (Recommended for CI/CD)**
```bash
export LOCALSTACK_AUTH_TOKEN="ls-string-here"
```

**Method B: Local JSON File (Recommended for Local Dev)**
Save your token in `~/.localstack/auth.json`:
```json
{
  "LOCALSTACK_AUTH_TOKEN": "ls-string-here"
}
```

---

## 3. Test Environment Setup

The integration tests rely on `testcontainers-localstack` to spin up ephemeral, isolated LocalStack containers per test module.

### Dependencies
Ensure you have the required packages installed in your Python virtual environment (these are included in `[dev]`):

```bash
pip install testcontainers boto3 pytest-asyncio
```

### Docker Daemon
The `testcontainers` library requires a running Docker daemon. 
*   **Mac/Windows:** Ensure Docker Desktop, OrbStack, or Rancher Desktop is running.
*   **Linux:** Ensure the `docker` service is active (`systemctl start docker`).

The test suite automatically skips LocalStack tests if the Docker daemon cannot be reached.

---

## 4. Writing Tests: The Fixture Pattern

All new AWS integration tests should utilize the standard `pytest` fixture pattern to instantiate the container and bind `boto3` clients.

### 4.1: The LocalStack Container Fixture
Define a module-scoped fixture that spins up the container, injects the auth token, and enables specific services:

```python
import pytest
import os
from testcontainers.localstack import LocalStackContainer

@pytest.fixture(scope="module")
def localstack():
    """Start a LocalStack Pro container with autoscaling, ecs, and lambda services."""
    token = os.environ.get("LOCALSTACK_AUTH_TOKEN") # Fallbacks handled in conftest
    
    container = (
        LocalStackContainer(image="localstack/localstack-pro:latest")
        .with_env("SERVICES", "autoscaling,ecs,lambda")
        .with_env("LOCALSTACK_AUTH_TOKEN", token)
        .with_env("AWS_DEFAULT_REGION", "us-east-1")
    )
    with container as c:
        yield c
```

### 4.2: Binding `boto3` Clients
Create mocked `boto3` clients that point directly to the ephemeral LocalStack endpoint provided by the container fixture:

```python
@pytest.fixture(scope="module")
def ecs_client(localstack):
    import boto3
    return boto3.client(
        "ecs",
        region_name="us-east-1",
        endpoint_url=localstack.get_url(),
        aws_access_key_id="test-key",
        aws_secret_access_key="test-secret",
    )
```

### 4.3: Executing the Test
Inject the mocked client into the Operator class being tested:

```python
@pytest.mark.asyncio
async def test_ecs_operator_health(ecs_client):
    from sre_agent.adapters.cloud.aws.ecs_operator import ECSOperator
    
    operator = ECSOperator(ecs_client)
    is_healthy = await operator.health_check()
    
    assert is_healthy is True
```

---

## 5. Supported AWS Mock Features

When writing chaos induction or behavioral tests against LocalStack, you can leverage the following emulated capabilities:

| Service | Emulated Capability | SRE Agent Use Case |
|---------|---------------------|--------------------|
| **EC2 Auto Scaling (ASG)** | `SetDesiredCapacity`, `DescribeAutoScalingGroups` | Testing the agent's ability to scale out compute capacity in response to latency/traffic spikes. |
| **ECS** | `StopTask`, `UpdateService`, `ListTasks` | Validating the agent's response to OOM kills or isolating misbehaving tasks safely. |
| **Lambda** | `Invoke`, `GetFunctionConfiguration` | Validating the serverless detection module (cold start suppression handling). |

---

## 6. Troubleshooting Common Issues

| Issue | Cause / Solution |
|-------|------------------|
| **`Skipped: Docker daemon is not running`** | The test runner could not find `docker` in `$PATH` or communicate with the daemon. Start Docker. |
| **`boto3.exceptions.ClientError: 403 Forbidden`** | The container booted as Community tier. Ensure `LOCALSTACK_AUTH_TOKEN` is set, correctly spelled, and the license is not expired. |
| **`testcontainers.core.exceptions.ContainerStartException`** | Usually indicates port conflicts or Docker memory limits. Ensure Docker has at least 4GB of RAM allocated. |
| **`Unknown service: 'autoscaling'`** | Ensure you invoked `.with_env("SERVICES", "autoscaling")` on the `LocalStackContainer` fixture. |
