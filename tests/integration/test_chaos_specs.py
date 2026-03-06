"""
Chaos Engineering Specification Tests — CHX-001 through CHX-005.

Implements the formal behavioral specs from:
  docs/testing/localstack_e2e_live_specs.md  § 1. Chaos Engineering Tests (CHX)

Each test:
  1. Starts a LocalStack Pro container (shared module-level fixture).
  2. Provisions real AWS resources (ECS clusters/tasks, Lambda functions, ASGs)
     so that LocalStack ARN validation passes before the Chaos proxy fires.
  3. Injects a chaos fault rule via the LocalStack Chaos REST API.
  4. Exercises the relevant cloud operator or detection pipeline.
  5. Asserts the exact error type, retry behaviour, and circuit-breaker state
     defined in the Given-When-Then specification.
  6. Clears all fault rules in a per-test teardown autouse fixture.

Resolution notes (Phase 1.5.1):
  - All boto3 clients use Config(retries={"max_attempts": 0}) to disable
    botocore's internal retry layer, preventing timeout conflicts with the
    agent's own retry_with_backoff mechanism.
  - Real resources are provisioned via module-scoped fixtures because
    LocalStack's Chaos API proxy applies after ARN validation.
  - CHX-002 uses ResourceNotFoundException (not ValidationException) to
    align with the spec and the error_mapper's "NotFound" substring check.
  - error_mapper.py was updated to recognize AccessDeniedException by
    error code (not just HTTP 403 status).

Requires:
  - Docker daemon running.
  - LOCALSTACK_AUTH_TOKEN in env or ~/.localstack/auth.json.
  - localstack/localstack-pro:latest image pulled locally.
"""

from __future__ import annotations

import io
import json
import math
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timedelta, timezone
from random import uniform

import pytest

# ---------------------------------------------------------------------------
# Environment helpers (mirrors tests/integration/test_aws_operators_integration.py)
# ---------------------------------------------------------------------------


def _is_docker_daemon_running() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        subprocess.run(
            ["docker", "info"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def _get_localstack_auth_token() -> str:
    token = os.environ.get("LOCALSTACK_AUTH_TOKEN", "")
    if not token:
        auth_file = os.path.expanduser("~/.localstack/auth.json")
        if os.path.exists(auth_file):
            with open(auth_file) as f:
                data = json.load(f)
                token = data.get("LOCALSTACK_AUTH_TOKEN", "")
    return token


_AUTH_TOKEN = _get_localstack_auth_token()

pytestmark = pytest.mark.skipif(
    not _is_docker_daemon_running(),
    reason="Docker daemon is not running — LocalStack chaos specs require Testcontainers.",
)

boto3 = pytest.importorskip("boto3")
testcontainers_localstack = pytest.importorskip("testcontainers.localstack")
LocalStackContainer = testcontainers_localstack.LocalStackContainer

import botocore.config  # noqa: E402

from sre_agent.adapters.cloud.aws.ec2_asg_operator import EC2ASGOperator  # noqa: E402
from sre_agent.adapters.cloud.aws.ecs_operator import ECSOperator  # noqa: E402
from sre_agent.adapters.cloud.aws.lambda_operator import LambdaOperator  # noqa: E402
from sre_agent.adapters.cloud.resilience import (  # noqa: E402
    AuthenticationError,
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
    RateLimitError,
    ResourceNotFoundError,
    RetryConfig,
    TransientError,
)
from sre_agent.domain.detection.anomaly_detector import AnomalyDetector  # noqa: E402
from sre_agent.domain.detection.baseline import BaselineService  # noqa: E402
from sre_agent.domain.models.canonical import (  # noqa: E402
    AnomalyType,
    CanonicalMetric,
    ServiceLabels,
)
from sre_agent.domain.models.detection_config import DetectionConfig  # noqa: E402

# ---------------------------------------------------------------------------
# Chaos API helpers
# ---------------------------------------------------------------------------

_CHAOS_ENDPOINT = "/_localstack/chaos/faults"


def _inject_chaos_rules(localstack_url: str, rules: list[dict]) -> None:
    """POST one or more fault rules to the LocalStack Chaos API.

    Args:
        localstack_url: Base URL of the LocalStack instance, e.g. http://localhost:4566.
        rules: List of chaos rule dicts (service, operation, error, probability / latency).
    """
    body = json.dumps(rules).encode()
    req = urllib.request.Request(
        f"{localstack_url}{_CHAOS_ENDPOINT}",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        assert resp.status == 200, f"Chaos API returned HTTP {resp.status}"


def _clear_chaos_rules(localstack_url: str) -> None:
    """DELETE all active chaos fault rules — best-effort teardown."""
    req = urllib.request.Request(
        f"{localstack_url}{_CHAOS_ENDPOINT}",
        method="DELETE",
    )
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Shared module-level LocalStack fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def localstack():
    """LocalStack Pro container with ECS, Lambda, and AutoScaling active."""
    container = (
        LocalStackContainer(image="localstack/localstack-pro:latest")
        .with_env("SERVICES", "autoscaling,ecs,lambda")
        .with_env("LOCALSTACK_AUTH_TOKEN", _AUTH_TOKEN)
        .with_env("AWS_DEFAULT_REGION", "us-east-1")
    )
    with container as c:
        yield c


@pytest.fixture(scope="module")
def localstack_url(localstack) -> str:
    return localstack.get_url()


@pytest.fixture(scope="module")
def ecs_client(localstack):
    return boto3.client(
        "ecs",
        region_name="us-east-1",
        endpoint_url=localstack.get_url(),
        aws_access_key_id="test",
        aws_secret_access_key="test",
        config=botocore.config.Config(retries={"max_attempts": 0}),
    )


@pytest.fixture(scope="module")
def asg_client(localstack):
    return boto3.client(
        "autoscaling",
        region_name="us-east-1",
        endpoint_url=localstack.get_url(),
        aws_access_key_id="test",
        aws_secret_access_key="test",
        config=botocore.config.Config(retries={"max_attempts": 0}),
    )


@pytest.fixture(scope="module")
def lambda_client(localstack):
    return boto3.client(
        "lambda",
        region_name="us-east-1",
        endpoint_url=localstack.get_url(),
        aws_access_key_id="test",
        aws_secret_access_key="test",
        config=botocore.config.Config(retries={"max_attempts": 0}),
    )


@pytest.fixture(autouse=True)
def clear_faults_after_each(localstack_url):
    """Guarantee fault rule cleanup after every test so tests do not bleed into each other."""
    yield
    _clear_chaos_rules(localstack_url)


# ---------------------------------------------------------------------------
# Resource provisioning helpers — LocalStack Chaos API applies after ARN
# validation, so real resources must exist before chaos faults are injected.
# ---------------------------------------------------------------------------


def _provision_ecs_resources(ecs_client, cluster_name="chx-cluster"):
    """Create an ECS cluster, register a task definition, and run a task.

    Returns:
        dict with keys: cluster, task_arn, service
    """
    try:
        ecs_client.create_cluster(clusterName=cluster_name)
    except Exception:  # noqa: BLE001
        pass  # Cluster may already exist

    try:
        ecs_client.register_task_definition(
            family="chx-task-def",
            containerDefinitions=[
                {
                    "name": "chx-container",
                    "image": "alpine:latest",
                    "memory": 128,
                }
            ],
        )
    except Exception:  # noqa: BLE001
        pass  # Task definition may already exist

    resp = ecs_client.run_task(cluster=cluster_name, taskDefinition="chx-task-def")
    task_arn = resp["tasks"][0]["taskArn"] if resp.get("tasks") else ""

    try:
        ecs_client.create_service(
            cluster=cluster_name,
            serviceName="chx-service",
            taskDefinition="chx-task-def",
            desiredCount=1,
        )
    except Exception:  # noqa: BLE001
        pass  # Service may already exist

    return {"cluster": cluster_name, "task_arn": task_arn, "service": "chx-service"}


def _provision_lambda_function(lambda_client, function_name="chx-lambda"):
    """Create a minimal Lambda function for chaos testing."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("handler.py", "def handler(event, context): return 'ok'")
    buf.seek(0)
    try:
        lambda_client.create_function(
            FunctionName=function_name,
            Runtime="python3.11",
            Role="arn:aws:iam::000000000000:role/lambda-role",
            Handler="handler.handler",
            Code={"ZipFile": buf.read()},
        )
    except Exception:  # noqa: BLE001
        pass  # Function may already exist
    return function_name


def _provision_asg(asg_client, asg_name="chx-asg"):
    """Create a launch configuration and Auto Scaling Group."""
    try:
        asg_client.create_launch_configuration(
            LaunchConfigurationName="chx-launch-config",
            ImageId="ami-12345678",
            InstanceType="t2.micro",
        )
    except Exception:  # noqa: BLE001
        pass
    try:
        asg_client.create_auto_scaling_group(
            AutoScalingGroupName=asg_name,
            LaunchConfigurationName="chx-launch-config",
            MinSize=0,
            MaxSize=10,
            DesiredCapacity=1,
            AvailabilityZones=["us-east-1a"],
        )
    except Exception:  # noqa: BLE001
        pass
    return asg_name


@pytest.fixture(scope="module")
def ecs_resources(ecs_client):
    """Provision ECS cluster, task definition, running task, and service."""
    return _provision_ecs_resources(ecs_client)


@pytest.fixture(scope="module")
def lambda_function_name(lambda_client):
    """Provision a Lambda function for chaos testing."""
    return _provision_lambda_function(lambda_client)


@pytest.fixture(scope="module")
def asg_name(asg_client):
    """Provision an Auto Scaling Group for chaos testing."""
    return _provision_asg(asg_client)


# ---------------------------------------------------------------------------
# Spec CHX-001: Rate Limit Error Backoff
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chx_001_throttling_exception_triggers_ratelimit_and_retry(
    localstack_url: str, ecs_client, ecs_resources
) -> None:
    """CHX-001 — Given ThrottlingException chaos fault on ecs:StopTask (100%),
    When the SRE Agent attempts to stop an ECS task,
    Then map_boto_error translates the fault into RateLimitError,
    And retry_with_backoff retries exactly RetryConfig.max_retries times,
    And execution takes at least the cumulative backoff duration before raising TransientError.

    Spec: docs/testing/localstack_e2e_live_specs.md §1 CHX-001
    """
    # ── Given ──────────────────────────────────────────────────────────────
    _clear_chaos_rules(localstack_url)

    _inject_chaos_rules(localstack_url, [
        {
            "service": "ecs",
            "operation": "StopTask",
            "error": {"code": "ThrottlingException"},
        }
    ])

    max_retries = 3
    base_delay = 0.05  # seconds (fast delays for test performance)
    # Expected cumulative sleep: base*(2^0) + base*(2^1) + base*(2^2) = 0.05+0.10+0.20 = 0.35s
    expected_min_elapsed = sum(base_delay * (2 ** i) for i in range(max_retries))

    config = RetryConfig(
        max_retries=max_retries,
        base_delay_seconds=base_delay,
        max_delay_seconds=10.0,
    )
    circuit_breaker = CircuitBreaker(failure_threshold=10, name="chx-001")
    operator = ECSOperator(ecs_client, retry_config=config, circuit_breaker=circuit_breaker)

    # ── When ───────────────────────────────────────────────────────────────
    task_arn = ecs_resources["task_arn"]
    start = time.monotonic()
    with pytest.raises(TransientError) as exc_info:
        await operator.restart_compute_unit(
            resource_id=task_arn,
            metadata={"cluster": ecs_resources["cluster"]},
        )
    elapsed = time.monotonic() - start

    # ── Then ───────────────────────────────────────────────────────────────
    # The final raised exception is TransientError("All N retries exhausted...")
    assert "retries exhausted" in str(exc_info.value).lower(), (
        f"Expected exhausted-retries message, got: {exc_info.value}"
    )
    # Cumulative backoff must be observable in wall-clock time
    assert elapsed >= expected_min_elapsed, (
        f"Expected >= {expected_min_elapsed:.2f}s backoff, got {elapsed:.2f}s — retries not firing"
    )
    # Circuit breaker must not yet be OPEN (only accumulated failures, threshold=10)
    assert circuit_breaker.state == CircuitState.CLOSED


# ---------------------------------------------------------------------------
# Spec CHX-002: Fast-Fail on Resource Not Found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chx_002_resource_not_found_aborts_immediately_no_retry(
    localstack_url: str, lambda_client, lambda_function_name
) -> None:
    """CHX-002 — Given ResourceNotFoundException chaos fault on lambda:PutFunctionConcurrency,
    When the SRE Agent attempts to remediate the Lambda function,
    Then map_boto_error translates the fault into ResourceNotFoundError,
    And the operation aborts immediately without any retries (elapsed < 500ms),
    And the Circuit Breaker registers exactly one failure.

    Spec: docs/testing/localstack_e2e_live_specs.md §1 CHX-002
    """
    # ── Given ──────────────────────────────────────────────────────────────
    _clear_chaos_rules(localstack_url)

    _inject_chaos_rules(localstack_url, [
        {
            "service": "lambda",
            "operation": "PutFunctionConcurrency",
            "error": {"code": "ResourceNotFoundException"},
        }
    ])

    config = RetryConfig(max_retries=3, base_delay_seconds=1.0)  # Would add 7s if retried
    circuit_breaker = CircuitBreaker(failure_threshold=5, name="chx-002")
    operator = LambdaOperator(lambda_client, retry_config=config, circuit_breaker=circuit_breaker)

    # ── When ───────────────────────────────────────────────────────────────
    start = time.monotonic()
    with pytest.raises(ResourceNotFoundError):
        await operator.scale_capacity(
            resource_id=lambda_function_name,
            desired_count=5,
        )
    elapsed = time.monotonic() - start

    # ── Then ───────────────────────────────────────────────────────────────
    # Must abort without sleeping between retries
    assert elapsed < 0.5, (
        f"ResourceNotFoundError should be immediate (<500ms), got {elapsed*1000:.1f}ms — "
        "possible unintended retry"
    )
    # Circuit breaker records exactly one failure (the single non-retryable attempt)
    assert circuit_breaker._failure_count == 1


# ---------------------------------------------------------------------------
# Spec CHX-003: Fast-Fail on Authentication Errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chx_003_access_denied_aborts_immediately_no_retry(
    localstack_url: str, asg_client, asg_name
) -> None:
    """CHX-003 — Given AccessDeniedException chaos fault on autoscaling:SetDesiredCapacity (403),
    When the SRE Agent attempts to scale an ASG,
    Then the fault is mapped strictly to AuthenticationError,
    And the remediation attempt aborts immediately entirely (no retries),
    And the circuit breaker records a single failure.

    Spec: docs/testing/localstack_e2e_live_specs.md §1 CHX-003
    """
    # ── Given ──────────────────────────────────────────────────────────────
    _clear_chaos_rules(localstack_url)

    _inject_chaos_rules(localstack_url, [
        {
            "service": "autoscaling",
            "operation": "SetDesiredCapacity",
            "error": {"code": "AccessDeniedException"},
        }
    ])

    config = RetryConfig(max_retries=3, base_delay_seconds=1.0)  # Would add 7s if retried
    circuit_breaker = CircuitBreaker(failure_threshold=5, name="chx-003")
    operator = EC2ASGOperator(asg_client, retry_config=config, circuit_breaker=circuit_breaker)

    # ── When ───────────────────────────────────────────────────────────────
    start = time.monotonic()
    with pytest.raises(AuthenticationError):
        await operator.scale_capacity(
            resource_id=asg_name,
            desired_count=3,
        )
    elapsed = time.monotonic() - start

    # ── Then ───────────────────────────────────────────────────────────────
    # Must abort without sleeping between retries
    assert elapsed < 0.5, (
        f"AuthenticationError should be immediate (<500ms), got {elapsed*1000:.1f}ms — "
        "possible unintended retry"
    )
    # AuthenticationError is non-retryable -> circuit records one failure, still CLOSED
    assert circuit_breaker._failure_count == 1
    assert circuit_breaker.state == CircuitState.CLOSED


# ---------------------------------------------------------------------------
# Spec CHX-004: Circuit Breaking on Sustained 500s
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chx_004_circuit_breaker_trips_on_sustained_500_errors(
    localstack_url: str, ecs_client, ecs_resources
) -> None:
    """CHX-004 — Given a CircuitBreaker(failure_threshold=5) and InternalError(500) on
    ecs:UpdateService at 100% probability,
    When the SRE Agent makes 5 consecutive remediation calls each failing with TransientError,
    Then the 5th failure transitions the Circuit Breaker to OPEN,
    And subsequent calls immediately raise CircuitOpenError without reaching LocalStack.

    Spec: docs/testing/localstack_e2e_live_specs.md §1 CHX-004
    """
    # ── Given ──────────────────────────────────────────────────────────────
    _clear_chaos_rules(localstack_url)

    # 100% probability of 500 error for UpdateService calls
    _inject_chaos_rules(localstack_url, [
        {
            "service": "ecs",
            "operation": "UpdateService",
            "error": {"code": "InternalError"},
        }
    ])

    # max_retries=0 -> each scale_capacity call = exactly one SDK attempt = one circuit failure
    config = RetryConfig(max_retries=0, base_delay_seconds=0.05)
    circuit_breaker = CircuitBreaker(failure_threshold=5, name="chx-004")
    operator = ECSOperator(ecs_client, retry_config=config, circuit_breaker=circuit_breaker)

    service_name = ecs_resources["service"]
    cluster_name = ecs_resources["cluster"]

    # ── When ───────────────────────────────────────────────────────────────
    # Drive 5 consecutive failures to reach the threshold
    for call_num in range(1, 6):
        with pytest.raises((TransientError, Exception)):
            await operator.scale_capacity(
                resource_id=service_name,
                desired_count=1,
                metadata={"cluster": cluster_name},
            )
        # Verify incremental failure accumulation
        assert circuit_breaker._failure_count == call_num, (
            f"Expected failure_count={call_num} after call {call_num}, "
            f"got {circuit_breaker._failure_count}"
        )

    # ── Then ───────────────────────────────────────────────────────────────
    # After 5 failures the circuit must be OPEN
    assert circuit_breaker.state == CircuitState.OPEN, (
        f"Expected CircuitState.OPEN after {circuit_breaker._failure_count} failures, "
        f"got {circuit_breaker.state}"
    )

    # The 6th call must be rejected immediately by the circuit breaker (no SDK call made)
    rejection_start = time.monotonic()
    with pytest.raises(CircuitOpenError) as exc_info:
        await operator.scale_capacity(
            resource_id=service_name,
            desired_count=1,
            metadata={"cluster": cluster_name},
        )
    rejection_elapsed = time.monotonic() - rejection_start

    assert "OPEN" in str(exc_info.value), (
        f"CircuitOpenError message should mention OPEN state: {exc_info.value}"
    )
    # Circuit breaker rejection is instantaneous, no network round trip
    assert rejection_elapsed < 0.05, (
        f"CircuitOpenError should be raised in <50ms, took {rejection_elapsed*1000:.1f}ms"
    )


# ---------------------------------------------------------------------------
# Spec CHX-005: Network Latency Detection Validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chx_005_injected_network_latency_fires_latency_spike_alert(
    localstack_url: str, lambda_client
) -> None:
    """CHX-005 — Given a baseline latency of ~50ms and 800ms latency injected on all Lambda calls,
    When a Lambda API call is timed and fed to AnomalyDetector,
    Then the detector issues a LATENCY_SPIKE alert with sigma formally > 10.

    Spec: docs/testing/localstack_e2e_live_specs.md §1 CHX-005

    Note on two-phase detection: The detector requires two consecutive above-threshold
    metrics: the first starts the timer, the second fires the alert. Both metric calls
    are made within the same hour bucket (minute=30 anchor) to guarantee baseline alignment.
    """
    # ── Given ──────────────────────────────────────────────────────────────
    # Build baseline: 35 data points ≈ 50ms with small natural variation
    # Anchored to minute=30 to avoid hour-bucket boundary during the test.
    now = datetime.now(timezone.utc).replace(minute=30, second=0, microsecond=0)

    baseline = BaselineService()
    config = DetectionConfig(
        latency_sigma_threshold=3.0,
        latency_duration_minutes=0,  # Duration=0: fires after second consecutive metric
    )
    detector = AnomalyDetector(baseline_service=baseline, config=config)

    for i in range(35):
        ts = now - timedelta(seconds=i * 10)
        normal_latency = 0.050 + uniform(-0.005, 0.005)  # 45–55ms
        await baseline.ingest("lambda-svc", "http_request_duration_seconds", normal_latency, ts)

    _clear_chaos_rules(localstack_url)

    # Inject 800ms latency on all Lambda API calls via Chaos API
    _inject_chaos_rules(localstack_url, [
        {
            "service": "lambda",
            "latency": 800,  # milliseconds
            "probability": 1.0,
        }
    ])

    # ── When ───────────────────────────────────────────────────────────────
    # Time an actual boto3 call that goes through LocalStack with injected latency.
    # This gives us the real observed latency to feed into the detector.
    call_start = time.monotonic()
    lambda_client.list_functions(MaxItems=1)  # Actual SDK call; latency injected here
    observed_latency_s = time.monotonic() - call_start  # in seconds

    # The observed latency must be at least 800ms for the test to be valid
    assert observed_latency_s >= 0.75, (
        f"Expected injected latency >= 750ms, got {observed_latency_s*1000:.0f}ms. "
        "Chaos latency injection may not have applied."
    )

    spike_metric = CanonicalMetric(
        name="http_request_duration_seconds",
        value=observed_latency_s,
        timestamp=now,
        labels=ServiceLabels(service="lambda-svc", namespace="default"),
    )

    # Phase 1: first metric above threshold — starts the duration timer (returns no alert)
    result_phase1 = await detector.detect("lambda-svc", [spike_metric])
    assert len(result_phase1.alerts) == 0, (
        "First metric should start the timer, not fire an alert (two-phase detection pattern)"
    )

    # Phase 2: second metric — duration check passes, alert fires
    result_phase2 = await detector.detect("lambda-svc", [spike_metric])

    # ── Then ───────────────────────────────────────────────────────────────
    latency_alerts = [
        a for a in result_phase2.alerts if a.anomaly_type == AnomalyType.LATENCY_SPIKE
    ]
    assert len(latency_alerts) >= 1, (
        f"Expected at least one LATENCY_SPIKE alert. Got alerts: "
        f"{[a.anomaly_type for a in result_phase2.alerts]}"
    )

    alert = latency_alerts[0]
    assert alert.deviation_sigma > 10.0, (
        f"Expected sigma > 10 for 800ms spike against 50ms baseline, got {alert.deviation_sigma:.1f}σ"
    )
    assert alert.service == "lambda-svc"
