---
title: LocalStack Pro Usage Standard
description: Canonical LocalStack Pro authentication, container configuration, Lambda tuning, CI integration, and health validation rules for all development, demo, and testing workflows.
ms.date: 2026-04-04
ms.topic: reference
author: SRE Agent Engineering Team
status: APPROVED
---

## Purpose

This standard defines the mandatory LocalStack Pro runtime pattern for this repository.

Every development, demo, and integration testing workflow must follow this standard.

The LocalStack CLI startup path `localstack start` is not allowed in this repository.

## Canonical Runtime

Use Docker as the only startup mechanism.

Use Docker Compose as the default command:

```bash
bash scripts/dev/setup_deps.sh start
```

Equivalent direct Docker command:

```bash
docker run --rm -d \
  --name localstack \
  -p 4566:4566 \
  -e LOCALSTACK_AUTH_TOKEN=<your-token> \
  -e DEFAULT_REGION=us-east-1 \
  -e SERVICES=autoscaling,cloudwatch,ec2,ecs,events,iam,lambda,logs,s3,secretsmanager,sns,sts \
  -e LAMBDA_RUNTIME_ENVIRONMENT_TIMEOUT=120 \
  -e EAGER_SERVICE_LOADING=1 \
  -e DOCKER_HOST=unix:///var/run/docker.sock \
  -v localstack_data:/var/lib/localstack \
  -v /var/run/docker.sock:/var/run/docker.sock \
  localstack/localstack-pro:latest
```

## Authentication

There is exactly **one** way to provide the LocalStack Pro token: the `LOCALSTACK_AUTH_TOKEN` environment variable.

For local development, set it in `.env` (which is auto-loaded by all scripts):

```bash
# .env
LOCALSTACK_AUTH_TOKEN=ls-your-token-here
```

For CI, store it as a repository secret and pass it via the workflow environment.

No file-based fallbacks (`~/.localstack/auth.json`) are used. The legacy `LOCALSTACK_API_KEY` variable is deprecated by LocalStack and must not be used.

### Obtaining a Token

Developer tokens and CI tokens are available at [app.localstack.cloud/workspace/auth-tokens](https://app.localstack.cloud/workspace/auth-tokens).

Use a **CI Auth Token** (not a developer token) for CI pipelines.

## Required Configuration

All LocalStack Pro runtimes must include these values:

| Parameter | Value |
|-----------|-------|
| Image | `localstack/localstack-pro:latest` |
| Port mapping | `4566:4566` |
| `LOCALSTACK_AUTH_TOKEN` | Valid Pro token |
| `DEFAULT_REGION` | `us-east-1` |
| `SERVICES` | `autoscaling,cloudwatch,ec2,ecs,events,iam,lambda,logs,s3,secretsmanager,sns,sts` |
| `LAMBDA_RUNTIME_ENVIRONMENT_TIMEOUT` | `120` |
| `EAGER_SERVICE_LOADING` | `1` |
| Volume mount | `localstack_data:/var/lib/localstack` |
| Docker socket | `/var/run/docker.sock:/var/run/docker.sock` |
| Health endpoint | `http://localhost:4566/_localstack/health` |

Additional environment variables are allowed only when required by a specific test scenario (for example, `ENFORCE_IAM=1` in IAM integration tests).

### Service List Rationale

| Service | Why Required |
|---------|-------------|
| `autoscaling` | EC2 ASG operator tests and demos |
| `cloudwatch` | CloudWatch alarm and metric enrichment demos |
| `ec2` | Launch template creation for ASG tests |
| `ecs` | ECS operator tests (stop task, update service) |
| `events` | EventBridge reaction demos |
| `iam` | IAM enforcement integration tests |
| `lambda` | Lambda operator tests and incident demos |
| `logs` | CloudWatch Logs enrichment in demos |
| `s3` | General storage for test fixtures |
| `secretsmanager` | Secret resolution in adapters |
| `sns` | SNS topic/subscription in multi-service demos |
| `sts` | Credential verification |

## Lambda Runtime Tuning

Lambda execution in LocalStack Pro requires Docker-in-Docker. The LocalStack container spins up separate Docker containers for each Lambda runtime environment.

### LAMBDA_RUNTIME_ENVIRONMENT_TIMEOUT

Default: `20` seconds. This standard requires: `120` seconds.

The default 20-second timeout is insufficient for first-run cold starts where LocalStack must pull the Lambda runtime image (for example, `public.ecr.aws/lambda/python:3.11`). Setting 120 seconds prevents timeout failures during initial Lambda invocations.

### EAGER_SERVICE_LOADING

Default: `0` (lazy). This standard requires: `1` (eager).

When set to `1`, LocalStack preloads all configured services at container startup instead of loading them on first request. This adds approximately 30 seconds to startup time but eliminates race conditions where a service is not ready when a test or demo sends its first request.

### Docker Socket Mount

The Docker socket mount `/var/run/docker.sock:/var/run/docker.sock` is mandatory. Without it, Lambda invocations fail with `Docker not available` errors because LocalStack cannot create runtime containers.

## Health Validation

### Before Tests and Demos

Validate runtime health and Pro edition:

```bash
bash scripts/dev/localstack_check.sh
```

For a deeper check that also smoke-tests Lambda execution:

```bash
bash scripts/dev/localstack_check.sh --deep
```

For integration tests, the command below enforces Pro checks before test execution:

```bash
bash scripts/dev/run.sh test:integ
```

### What Validation Confirms

* Container image is `localstack/localstack-pro:latest`
* `edition` is `pro` in the health payload
* All 12 required services are `available` or `running`
* (With `--deep`) Lambda runtime can create, invoke, and delete a function

### Health Endpoint Response Format

```json
{
  "edition": "pro",
  "version": "4.x.x",
  "services": {
    "autoscaling": "available",
    "cloudwatch": "available",
    "ec2": "available",
    "ecs": "available",
    "events": "available",
    "iam": "available",
    "lambda": "available",
    "logs": "available",
    "s3": "available",
    "secretsmanager": "available",
    "sns": "available",
    "sts": "available"
  }
}
```

## CI Pipeline Integration

Integration tests run in CI using the official `LocalStack/setup-localstack` GitHub Action.

### GitHub Actions Configuration

The CI workflow (`.github/workflows/ci.yml`) includes an `integration-localstack` job that:

1. Starts LocalStack Pro using `LocalStack/setup-localstack@v0.2.3` with `use-pro: 'true'`
2. Passes `LOCALSTACK_AUTH_TOKEN` from the repository secret
3. Runs `scripts/dev/localstack_check.sh` as a readiness gate
4. Runs `pytest tests/integration/ -v --tb=short`

### Repository Secret Setup

1. Go to repository Settings > Secrets and variables > Actions
2. Create a new repository secret named `LOCALSTACK_AUTH_TOKEN`
3. Paste a valid **CI Auth Token** from [app.localstack.cloud](https://app.localstack.cloud/workspace/auth-tokens)

CI Auth Tokens are separate from developer tokens and designed for automated pipelines.

## Failure Modes

### Missing token

Symptoms:

* LocalStack Pro container fails to start
* Startup exits with license activation errors (exit code 55)
* `scripts/dev/setup_deps.sh start` reports "LOCALSTACK_AUTH_TOKEN is required"

Resolution:

* Set `LOCALSTACK_AUTH_TOKEN` in `.env` or export it in your shell
* Restart with `bash scripts/dev/setup_deps.sh start`

### Invalid or expired token

Symptoms:

* Container logs show "License activation failed"
* Container exits during boot with exit code 55

Resolution:

* Get a valid token from [app.localstack.cloud](https://app.localstack.cloud/workspace/auth-tokens)
* Replace the token and recreate the container

### Community tier fallback

Symptoms:

* Health payload returns `"edition": "community"`
* Pro-only features fail with `403 Forbidden` or unsupported service errors

Resolution:

* Ensure image is `localstack/localstack-pro:latest` (not `localstack/localstack:latest`)
* Ensure valid `LOCALSTACK_AUTH_TOKEN` is injected at container startup
* Recreate container using the canonical runtime command

### Service not enabled

Symptoms:

* `An error occurred (InternalFailure) when calling the CreateTopic operation: Service 'sns' is not enabled`

Resolution:

* Verify `SERVICES` environment variable includes all 12 required services
* Do not override the `SERVICES` variable unless adding extra services

### Lambda invocation timeout

Symptoms:

* `Timeout while starting up lambda environment for function <name>`
* Lambda stays in `Pending` state indefinitely

Resolution:

* Verify `LAMBDA_RUNTIME_ENVIRONMENT_TIMEOUT=120` is set on the container
* Verify Docker socket is mounted: `/var/run/docker.sock:/var/run/docker.sock`
* Pre-pull the runtime image: `docker pull public.ecr.aws/lambda/python:3.11`
* Check Docker has at least 4 GB of RAM allocated

### Slow startup with EAGER_SERVICE_LOADING

Symptoms:

* Container takes 60+ seconds to become healthy (vs 10-20 seconds without eager loading)

This is expected behavior. Eager loading trades startup time for runtime readiness. All 12 services are initialized before the health endpoint reports ready, eliminating lazy-load race conditions.

## Troubleshooting

Run these checks in order:

```bash
# 1. Is the container running with the Pro image?
docker ps --filter name=^localstack$ --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'

# 2. What does the health endpoint say?
curl -s http://localhost:4566/_localstack/health | python3 -m json.tool

# 3. Check container logs for activation errors
docker logs localstack --tail 30

# 4. Run the full readiness validation
bash scripts/dev/localstack_check.sh

# 5. Run deep check including Lambda smoke test
bash scripts/dev/localstack_check.sh --deep
```

If `edition` is not `pro`, do not run integration tests or LocalStack demos. Fix authentication first, then restart LocalStack Pro.

## Enforcement in This Repository

This standard is implemented and enforced at these entry points:

| Entry Point | What It Enforces |
|-------------|-----------------|
| `docker-compose.deps.yml` | Canonical service config, image, ports, volumes, tuning vars |
| `scripts/dev/setup_deps.sh` | Token resolution, Docker Compose startup, health checks |
| `scripts/dev/run.sh test:integ` | Pro validation gate before integration tests |
| `scripts/dev/localstack_check.sh` | Standalone readiness validation (basic + deep) |
| `tests/localstack_pro_standard.py` | Shared Python test fixture with canonical settings |
| `scripts/demo/_demo_utils.py` | Demo startup helpers with Docker-based standardization |
| `.github/workflows/ci.yml` | CI integration test job with Pro auth and readiness gate |
