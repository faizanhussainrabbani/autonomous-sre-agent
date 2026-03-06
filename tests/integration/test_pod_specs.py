"""
Cloud Pod Specification Tests — POD-001 and POD-002.

Implements the formal behavioral specs from:
  docs/testing/localstack_e2e_live_specs.md  § 2. Cloud Pod Tests (POD)

Architecture:
  - A LocalStack Pro container is started with the PODS service enabled.
  - Cloud pod state is loaded via the LocalStack CLI (``localstack pod load``)
    or its equivalent REST API endpoint, both of which restore a pre-saved
    snapshot of ECS/service state into the running LocalStack instance.
  - When no pre-saved pod is available (first run, offline CI), each test
    creates an equivalent ECS state manually and continues — the assertion
    logic remains identical.
  - The AlertCorrelationEngine (POD-002) is exercised with a static
    ServiceGraph that matches the cascade topology stored in the pod.

Skip conditions:
  - Docker daemon is not running.
  - LOCALSTACK_AUTH_TOKEN is not set (Cloud Pods require a Pro token).

Spec: docs/testing/localstack_e2e_live_specs.md §2 POD-001 and POD-002
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

import pytest

# ---------------------------------------------------------------------------
# Environment helpers
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
    reason="Docker daemon is not running — LocalStack cloud pod specs require Testcontainers.",
)

boto3 = pytest.importorskip("boto3")
testcontainers_localstack = pytest.importorskip("testcontainers.localstack")
LocalStackContainer = testcontainers_localstack.LocalStackContainer

from sre_agent.adapters.cloud.aws.ecs_operator import ECSOperator  # noqa: E402
from sre_agent.adapters.cloud.resilience import RetryConfig  # noqa: E402
from sre_agent.domain.detection.alert_correlation import (  # noqa: E402
    AlertCorrelationEngine,
    CorrelatedIncident,
)
from sre_agent.domain.models.canonical import (  # noqa: E402
    AnomalyAlert,
    AnomalyType,
    ComputeMechanism,
    ServiceEdge,
    ServiceGraph,
    ServiceNode,
)

# ---------------------------------------------------------------------------
# Cloud Pod loading helpers
# ---------------------------------------------------------------------------

_POD_OOM_SCENARIO = "sre-agent/oom-scenario"
_POD_CASCADING_FAILURE = "sre-agent/cascading-failure"

# ECS resource names that the pods contain
_POD_OOM_CLUSTER = "sre-cluster"
_POD_OOM_SERVICE = "checkout-service"

_POD_CASCADE_CLUSTER = "sre-cluster"
_CASCADE_SERVICES = ["ecs-checkout-svc", "ecs-payment-svc", "ecs-db-svc"]
_CASCADE_ROOT_SERVICE = "ecs-checkout-svc"  # Earliest alert → root of cascade


def _load_cloud_pod_cli(pod_name: str, endpoint_url: str) -> bool:
    """Load a Cloud Pod via the ``localstack pod load`` CLI command.

    Returns True when the pod was loaded successfully, False otherwise.
    """
    if not shutil.which("localstack"):
        return False
    try:
        result = subprocess.run(
            ["localstack", "pod", "load", pod_name, "--endpoint-url", endpoint_url],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def _load_cloud_pod_api(pod_name: str, localstack_url: str) -> bool:
    """Load a Cloud Pod via the LocalStack Pro REST API (no CLI required).

    Endpoint: POST /_localstack/pods/{name}/load
    Returns True on HTTP 200/202, False on any error.
    """
    req = urllib.request.Request(
        f"{localstack_url}/_localstack/pods/{pod_name}/load",
        data=b"{}",
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status in (200, 202)
    except (urllib.error.URLError, urllib.error.HTTPError):
        return False


def _pod_loaded(pod_name: str, localstack_url: str) -> bool:
    """Try CLI first, then REST API. Returns True when the pod was loaded."""
    return _load_cloud_pod_cli(pod_name, localstack_url) or _load_cloud_pod_api(
        pod_name, localstack_url
    )


# ---------------------------------------------------------------------------
# Shared LocalStack fixture (module-level)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def localstack():
    """LocalStack Pro container with ECS and Cloud Pods enabled."""
    container = (
        LocalStackContainer(image="localstack/localstack-pro:latest")
        .with_env("SERVICES", "ecs")
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
    )


# ---------------------------------------------------------------------------
# ECS state provisioning helpers (fallback when pod can't be loaded)
# ---------------------------------------------------------------------------


def _provision_oom_scenario_state(ecs_client) -> None:
    """Create the ECS cluster + OOM-crashed service (desiredCount=0) manually.

    This replicates the state that the 'sre-agent/oom-scenario' Cloud Pod
    would restore, so assertions can run even when the pod is not available.
    """
    try:
        ecs_client.create_cluster(clusterName=_POD_OOM_CLUSTER)
    except Exception:  # noqa: BLE001
        pass  # Already exists

    task_def_arn = ""
    try:
        resp = ecs_client.register_task_definition(
            family="dummy",
            containerDefinitions=[{"name": "test", "image": "nginx", "memory": 128}]
        )
        task_def_arn = resp["taskDefinition"]["taskDefinitionArn"]
    except Exception:
        pass

    try:
        ecs_client.create_service(
            cluster=_POD_OOM_CLUSTER,
            serviceName=_POD_OOM_SERVICE,
            desiredCount=0,  # Simulates post-OOM state (scheduler set it to 0)
            launchType="FARGATE",
            taskDefinition=task_def_arn,
            networkConfiguration={
                "awsvpcConfiguration": {
                    "subnets": ["subnet-00000000"],
                    "assignPublicIp": "DISABLED",
                }
            },
        )
    except Exception:
        # Ensure desiredCount is 0 (pod state simulation)
        try:
            ecs_client.update_service(
                cluster=_POD_OOM_CLUSTER,
                service=_POD_OOM_SERVICE,
                desiredCount=0,
            )
        except Exception:
            pass


def _provision_cascade_scenario_state(ecs_client) -> None:
    """Create the ECS cluster + 3 cascade services manually.

    Replicates the 'sre-agent/cascading-failure' Cloud Pod state when the
    pod cannot be loaded from LocalStack Cloud.
    """
    try:
        ecs_client.create_cluster(clusterName=_POD_CASCADE_CLUSTER)
    except Exception:  # noqa: BLE001
        pass

    task_def_arn = ""
    try:
        resp = ecs_client.register_task_definition(
            family="dummy-cascade",
            containerDefinitions=[{"name": "test", "image": "nginx", "memory": 128}]
        )
        task_def_arn = resp["taskDefinition"]["taskDefinitionArn"]
    except Exception:
        pass

    for svc_name in _CASCADE_SERVICES:
        try:
            ecs_client.create_service(
                cluster=_POD_CASCADE_CLUSTER,
                serviceName=svc_name,
                desiredCount=0,  # All crashed (cascade failure)
                launchType="FARGATE",
                taskDefinition=task_def_arn,
                networkConfiguration={
                    "awsvpcConfiguration": {
                        "subnets": ["subnet-00000000"],
                        "assignPublicIp": "DISABLED",
                    }
                },
            )
        except Exception:
            try:
                ecs_client.update_service(
                    cluster=_POD_CASCADE_CLUSTER,
                    service=svc_name,
                    desiredCount=0,
                )
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Cascade topology for POD-002 (mirrors the pod's service graph)
# ---------------------------------------------------------------------------

def _build_cascade_service_graph() -> ServiceGraph:
    """Construct the static dependency graph for the cascading-failure pod.

    Topology (caller → callee):
        ecs-checkout-svc → ecs-payment-svc → ecs-db-svc

    Semantics:
        - get_downstream("ecs-checkout-svc") = ["ecs-payment-svc"]
        - get_downstream("ecs-payment-svc") = ["ecs-db-svc"]
        - get_upstream("ecs-payment-svc") = ["ecs-checkout-svc"]
        - get_upstream("ecs-db-svc") = ["ecs-payment-svc"]
    """
    return ServiceGraph(
        nodes={
            "ecs-checkout-svc": ServiceNode(service="ecs-checkout-svc", tier=1),
            "ecs-payment-svc": ServiceNode(service="ecs-payment-svc", tier=1),
            "ecs-db-svc": ServiceNode(service="ecs-db-svc", tier=2),
        },
        edges=[
            ServiceEdge(source="ecs-checkout-svc", target="ecs-payment-svc"),
            ServiceEdge(source="ecs-payment-svc", target="ecs-db-svc"),
        ],
    )


# ---------------------------------------------------------------------------
# Spec POD-001: OOM Recovery Scale-Up
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pod_001_oom_scenario_agent_scales_service_to_healthy_count(
    localstack_url: str, ecs_client
) -> None:
    """POD-001 — Given the 'sre-agent/oom-scenario' pod initializes an ECS service
    at desiredCount=0 (OOM-crashed),
    When the SRE Agent remediation path runs scale_capacity for the affected service,
    Then the ECS service desiredCount is set to 2 (healthy replica count).

    Spec: docs/testing/localstack_e2e_live_specs.md §2 POD-001

    Pod state manifest:
        cluster: sre-cluster
        service: checkout-service
        initial desiredCount: 0   (scheduler set it to 0 post-OOM kill)
        target desiredCount: 2    (remediation target for this service tier)
    """
    # ── Given ──────────────────────────────────────────────────────────────
    # Try to load the canonical pod state; fall back to manual provisioning.
    if not _pod_loaded(_POD_OOM_SCENARIO, localstack_url):
        _provision_oom_scenario_state(ecs_client)

    # Confirm pre-condition: service exists with desiredCount=0
    pre_resp = ecs_client.describe_services(
        cluster=_POD_OOM_CLUSTER,
        services=[_POD_OOM_SERVICE],
    )
    services = [s for s in pre_resp.get("services", []) if s.get("status") != "INACTIVE"]
    assert len(services) == 1, (
        f"Pre-condition failed: expected service '{_POD_OOM_SERVICE}' in cluster "
        f"'{_POD_OOM_CLUSTER}' to exist, got: {pre_resp.get('failures', [])}"
    )
    pre_desired = services[0]["desiredCount"]
    assert pre_desired == 0, (
        f"Pre-condition failed: expected desiredCount=0 (OOM-crashed), got {pre_desired}. "
        "Verify the pod snapshot or manual state provisioning."
    )

    # ── When ───────────────────────────────────────────────────────────────
    config = RetryConfig(max_retries=2, base_delay_seconds=0.1)
    operator = ECSOperator(ecs_client, retry_config=config)

    await operator.scale_capacity(
        resource_id=_POD_OOM_SERVICE,
        desired_count=2,
        metadata={"cluster": _POD_OOM_CLUSTER},
    )

    # ── Then ───────────────────────────────────────────────────────────────
    post_resp = ecs_client.describe_services(
        cluster=_POD_OOM_CLUSTER,
        services=[_POD_OOM_SERVICE],
    )
    post_services = [s for s in post_resp.get("services", []) if s.get("status") != "INACTIVE"]
    assert len(post_services) == 1

    post_desired = post_services[0]["desiredCount"]
    assert post_desired == 2, (
        f"Expected desiredCount=2 after remediation, got {post_desired}. "
        "scale_capacity did not update the ECS service desiredCount correctly."
    )


# ---------------------------------------------------------------------------
# Spec POD-002: Cascading Failure Correlation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pod_002_cascading_failure_pod_yields_single_correlated_incident(
    localstack_url: str, ecs_client
) -> None:
    """POD-002 — Given the 'sre-agent/cascading-failure' pod initializes 3 ECS
    services in a cascade topology (checkout → payment → db),
    When one ERROR_RATE_SURGE alert per service is fed to AlertCorrelationEngine,
    Then exactly 1 CorrelatedIncident is returned,
    And root_service equals 'ecs-checkout-svc' (earliest alert in the cascade),
    And is_cascade is True,
    And all 3 services appear in services_affected.

    Spec: docs/testing/localstack_e2e_live_specs.md §2 POD-002

    Cascade topology (stored in pod, mirrored in service graph):
        ecs-checkout-svc → ecs-payment-svc → ecs-db-svc
    """
    # ── Given ──────────────────────────────────────────────────────────────
    if not _pod_loaded(_POD_CASCADING_FAILURE, localstack_url):
        _provision_cascade_scenario_state(ecs_client)

    # Confirm pre-condition: all 3 services exist in the cluster
    pre_resp = ecs_client.describe_services(
        cluster=_POD_CASCADE_CLUSTER,
        services=_CASCADE_SERVICES,
    )
    active_services = [
        s["serviceName"]
        for s in pre_resp.get("services", [])
        if s.get("status") != "INACTIVE"
    ]
    assert set(active_services) == set(_CASCADE_SERVICES), (
        f"Pre-condition failed: expected services {_CASCADE_SERVICES} in "
        f"cluster '{_POD_CASCADE_CLUSTER}', found: {active_services}. "
        f"Failures: {pre_resp.get('failures', [])}"
    )

    # ── When ───────────────────────────────────────────────────────────────
    # Build the AlertCorrelationEngine with the cascade topology graph
    service_graph = _build_cascade_service_graph()
    engine = AlertCorrelationEngine(
        service_graph=service_graph,
        correlation_window_seconds=120,
    )

    # Construct 3 AnomalyAlerts — one per service — in cascade order
    # checkout fires first (root), payment and db follow 5s apart
    base_ts = datetime.now(timezone.utc)

    alert_checkout = AnomalyAlert(
        anomaly_type=AnomalyType.ERROR_RATE_SURGE,
        service="ecs-checkout-svc",
        namespace="prod",
        compute_mechanism=ComputeMechanism.KUBERNETES,
        timestamp=base_ts,
        deviation_sigma=12.5,
        description="ERROR_RATE_SURGE detected on checkout: 98% error rate",
    )
    alert_payment = AnomalyAlert(
        anomaly_type=AnomalyType.ERROR_RATE_SURGE,
        service="ecs-payment-svc",
        namespace="prod",
        compute_mechanism=ComputeMechanism.KUBERNETES,
        timestamp=base_ts + timedelta(seconds=5),
        deviation_sigma=11.0,
        description="ERROR_RATE_SURGE detected on payment: 95% error rate",
    )
    alert_db = AnomalyAlert(
        anomaly_type=AnomalyType.ERROR_RATE_SURGE,
        service="ecs-db-svc",
        namespace="prod",
        compute_mechanism=ComputeMechanism.KUBERNETES,
        timestamp=base_ts + timedelta(seconds=10),
        deviation_sigma=9.5,
        description="ERROR_RATE_SURGE detected on db: connection pool exhausted",
    )

    # Process all 3 alerts — they must all land in the SAME incident
    incident_checkout = await engine.process_alert(alert_checkout)
    incident_payment = await engine.process_alert(alert_payment)
    incident_db = await engine.process_alert(alert_db)

    # ── Then ───────────────────────────────────────────────────────────────
    # All 3 alerts must map to the same incident object
    assert incident_checkout.incident_id == incident_payment.incident_id, (
        "alert_payment should be correlated into the same incident as alert_checkout "
        "(ecs-payment-svc is downstream of ecs-checkout-svc in the service graph)"
    )
    assert incident_payment.incident_id == incident_db.incident_id, (
        "alert_db should be correlated into the same incident as alert_payment "
        "(ecs-db-svc is downstream of ecs-payment-svc in the service graph)"
    )

    final_incident: CorrelatedIncident = incident_db  # All point to the same object

    # Exactly 1 correlated incident with 3 alerts
    assert final_incident.alert_count == 3, (
        f"Expected 3 alerts in the incident, got {final_incident.alert_count}. "
        "Not all cascade alerts were correlated."
    )
    assert final_incident.service_count == 3, (
        f"Expected 3 distinct services in the incident, got {final_incident.service_count}. "
        f"services_affected: {final_incident.services_affected}"
    )
    assert final_incident.services_affected == set(_CASCADE_SERVICES), (
        f"Expected services_affected={set(_CASCADE_SERVICES)}, "
        f"got {final_incident.services_affected}"
    )

    # Root service must be the earliest alert = ecs-checkout-svc
    assert final_incident.root_service == _CASCADE_ROOT_SERVICE, (
        f"Expected root_service='{_CASCADE_ROOT_SERVICE}' (earliest alert in cascade), "
        f"got '{final_incident.root_service}'. Root cause heuristic uses earliest timestamp."
    )

    # Cascade flag must be set
    assert final_incident.is_cascade is True, (
        "Expected is_cascade=True — alerts from dependency-linked services within "
        "the correlation window must be classified as a cascading failure."
    )

    # Engine should hold exactly 1 active incident (no duplicate incidents created)
    assert len(engine.active_incidents) == 1, (
        f"Expected exactly 1 active incident, got {len(engine.active_incidents)}. "
        "Multiple incidents indicate the alerts were not correlated."
    )
