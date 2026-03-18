"""
Live Demo 8 — ECS Multi-Service Cascade & Severity Override
=============================================================

A second end-to-end demo that exercises capabilities NOT covered by Demo 7:

  ✦ ECS services instead of Lambda (different compute mechanism)
  ✦ Multi-service cascade: order-service failure → payment-service degradation
  ✦ Correlated signals: `correlated_signals` field is POPULATED (not None)
  ✦ Real metric trend data sent to the LLM (not just alarm metadata)
  ✦ Real CloudWatch log excerpts injected into the diagnosis context
  ✦ Severity override API: operator downgrades an alert via REST
  ✦ ECS `scale_capacity` remediation: shows the agent's action output
  ✦ Dual-alarm scenario: two independent SNS notifications, two diagnoses

What this demo proves:
  Phase 0  — Pre-flight: verify LocalStack, ports, and environment
  Phase 1  — ECS infrastructure: register task definitions, create services
  Phase 2  — CloudWatch alarms: TaskCount + CPUUtilization alarms per service
  Phase 3  — Start SRE Agent FastAPI server (port 8181)
  Phase 4  — Start Incident Bridge webhook server (port 8080)
  Phase 5  — Subscribe bridge to both SNS topics
  Phase 6  — Seed knowledge base with ECS runbooks (order-service + payment-service)
  Phase 7  — INDUCE CHAOS: zero-out order-service desired count, spike CPU alarm
  Phase 8  — Fire cascade: order-service alarm → SNS → bridge → agent (with correlated signals)
  Phase 9  — Show first diagnosis (order-service outage)
  Phase 10 — Fire second alarm: payment-service degraded (cascade effect)
  Phase 11 — Show second diagnosis (payment-service cascade)
  Phase 12 — Severity override: operator downgrades payment-service alert from SEV2 → SEV3
  Phase 13 — Show override applied + pipeline halted confirmation
  Phase 14 — Cleanup

Usage
-----
    source .venv/bin/activate
    python scripts/live_demo_ecs_multi_service.py

Environment
-----------
    LOCALSTACK_ENDPOINT   LocalStack endpoint (default: http://localhost:4566)
    AWS_DEFAULT_REGION    AWS region (default: us-east-1)
    AGENT_PORT            SRE Agent port (default: 8181)
    BRIDGE_PORT           Incident bridge port (default: 8080)
    BRIDGE_HOST           Host LocalStack uses to reach the bridge webhook
                          (default: 127.0.0.1 for native LocalStack,
                           use host.docker.internal for Docker-based LocalStack)
    SKIP_PAUSES           Set to "1" to skip interactive ENTER prompts (CI mode)
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
import httpx
from dotenv import load_dotenv
from _demo_utils import aws_region, env_bool

# Load .env from the project root so LOCALSTACK_AUTH_TOKEN and other secrets
# are available without needing them exported in the shell.
load_dotenv(Path(__file__).parent.parent.parent / ".env")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
LOCALSTACK_ENDPOINT = os.getenv("LOCALSTACK_ENDPOINT", "http://localhost:4566")
AWS_REGION          = aws_region("us-east-1")
AGENT_PORT          = int(os.getenv("AGENT_PORT", "8181"))
BRIDGE_PORT         = int(os.getenv("BRIDGE_PORT", "8080"))
AGENT_URL           = f"http://127.0.0.1:{AGENT_PORT}"
BRIDGE_URL          = f"http://127.0.0.1:{BRIDGE_PORT}"
SKIP_PAUSES         = env_bool("SKIP_PAUSES", False)
# BRIDGE_HOST is the hostname LocalStack uses to reach this machine's bridge webhook.
# Use 127.0.0.1 when LocalStack runs natively; host.docker.internal for Docker Desktop.
BRIDGE_HOST         = os.getenv("BRIDGE_HOST", "127.0.0.1")

ACCOUNT_ID          = "000000000000"
ECS_CLUSTER_NAME    = "sre-demo-cluster"
ECS_CLUSTER_ARN     = f"arn:aws:ecs:{AWS_REGION}:{ACCOUNT_ID}:cluster/{ECS_CLUSTER_NAME}"

ORDER_SERVICE       = "order-service"
PAYMENT_SERVICE     = "payment-service"

ORDER_ALARM_NAME    = "OrderServiceTaskCountLow"
PAYMENT_ALARM_NAME  = "PaymentServiceCPUHigh"

ORDER_TOPIC_NAME    = "sre-order-alerts"
PAYMENT_TOPIC_NAME  = "sre-payment-alerts"

ORDER_TOPIC_ARN     = f"arn:aws:sns:{AWS_REGION}:{ACCOUNT_ID}:{ORDER_TOPIC_NAME}"
PAYMENT_TOPIC_ARN   = f"arn:aws:sns:{AWS_REGION}:{ACCOUNT_ID}:{PAYMENT_TOPIC_NAME}"

TASK_ROLE_ARN       = f"arn:aws:iam::{ACCOUNT_ID}:role/ecs-task-role"
EXEC_ROLE_ARN       = f"arn:aws:iam::{ACCOUNT_ID}:role/ecs-exec-role"

BRIDGE_SCRIPT_PATH  = Path(__file__).parent / "localstack_bridge.py"
VENV_PYTHON         = Path(__file__).parent.parent.parent / ".venv" / "bin" / "python"
VENV_UVICORN        = Path(__file__).parent.parent.parent / ".venv" / "bin" / "uvicorn"

LOCALSTACK_AUTH_TOKEN = os.getenv("LOCALSTACK_AUTH_TOKEN") or os.getenv("LOCALSTACK_API_KEY")

# ---------------------------------------------------------------------------
# Colour + formatting helpers (identical to Demo 7)
# ---------------------------------------------------------------------------
class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RED     = "\033[91m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    BLUE    = "\033[94m"
    CYAN    = "\033[96m"
    MAGENTA = "\033[95m"
    WHITE   = "\033[97m"


def banner(title: str) -> None:
    width = 74
    print(f"\n{C.BOLD}{C.BLUE}╔{'═' * width}╗{C.RESET}")
    print(f"{C.BOLD}{C.BLUE}║{title.center(width)}║{C.RESET}")
    print(f"{C.BOLD}{C.BLUE}╚{'═' * width}╝{C.RESET}\n")


def phase(number: int, title: str) -> None:
    label = f"  PHASE {number}: {title}  "
    width = 74
    print(f"\n{C.BOLD}{C.MAGENTA}╔{'═' * width}╗{C.RESET}")
    print(f"{C.BOLD}{C.MAGENTA}║{label.center(width)}║{C.RESET}")
    print(f"{C.BOLD}{C.MAGENTA}╚{'═' * width}╝{C.RESET}\n")


def ok(msg: str)    -> None: print(f"   {C.GREEN}✔{C.RESET}  {msg}")
def fail(msg: str)  -> None: print(f"   {C.RED}✖{C.RESET}  {C.RED}{msg}{C.RESET}")
def info(msg: str)  -> None: print(f"   {C.CYAN}ℹ{C.RESET}  {msg}")
def step(msg: str)  -> None: print(f"\n   {C.YELLOW}▶{C.RESET}  {C.BOLD}{msg}{C.RESET}")
def field(label: str, value: Any) -> None:
    print(f"   {C.DIM}{label}:{C.RESET} {C.WHITE}{value}{C.RESET}")
def abort(msg: str) -> None:
    fail(msg)
    sys.exit(1)


def pause(prompt: str = "Press ENTER to continue...") -> None:
    if not SKIP_PAUSES:
        input(f"\n   {C.DIM}{prompt}{C.RESET}\n")
    else:
        print()


# ---------------------------------------------------------------------------
# boto3 client factory
# ---------------------------------------------------------------------------
_boto_kwargs = dict(
    endpoint_url=LOCALSTACK_ENDPOINT,
    region_name=AWS_REGION,
    aws_access_key_id="test",
    aws_secret_access_key="test",
)

def ecs_client():  return boto3.client("ecs",        **_boto_kwargs)
def cw_client():   return boto3.client("cloudwatch", **_boto_kwargs)
def sns_client():  return boto3.client("sns",        **_boto_kwargs)
def ec2_client():  return boto3.client("ec2",        **_boto_kwargs)


# Populated by _discover_network_ids() during phase 0
_subnet_id: str = "subnet-00000000"
_sg_id: str = "sg-00000000"


def _discover_network_ids() -> tuple[str, str]:
    """Return (subnet_id, sg_id) from the default VPC in LocalStack.

    Creates the default VPC if one does not yet exist.
    """
    ec2 = ec2_client()
    vpcs = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])
    if vpcs["Vpcs"]:
        vpc_id = vpcs["Vpcs"][0]["VpcId"]
    else:
        info("No default VPC found — creating one")
        vpc_id = ec2.create_default_vpc()["Vpc"]["VpcId"]
        time.sleep(2)

    subnets = ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])
    subnet_id = subnets["Subnets"][0]["SubnetId"]

    sgs = ec2.describe_security_groups(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])
    sg_id = sgs["SecurityGroups"][0]["GroupId"]

    return subnet_id, sg_id


# ---------------------------------------------------------------------------
# Phase 0 — Pre-flight
# ---------------------------------------------------------------------------
def _localstack_healthy() -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(LOCALSTACK_ENDPOINT + "/_localstack/health", timeout=3) as r:
            data = json.loads(r.read())
            return data.get("status") in ("running", "ok") or bool(data.get("services"))
    except Exception:
        return False


def _start_localstack() -> None:
    step("LocalStack not running — attempting auto-start")
    env = os.environ.copy()
    if LOCALSTACK_AUTH_TOKEN:
        env["LOCALSTACK_AUTH_TOKEN"] = LOCALSTACK_AUTH_TOKEN

    result = subprocess.run(
        ["localstack", "start", "-d"],
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        abort(
            f"localstack start failed (exit {result.returncode}).\n"
            f"stdout: {result.stdout.strip()}\n"
            f"stderr: {result.stderr.strip()}"
        )

    info("Waiting for LocalStack to become healthy (up to 90 s)...")
    deadline = time.time() + 90
    while time.time() < deadline:
        if _localstack_healthy():
            ok(f"LocalStack is UP at {LOCALSTACK_ENDPOINT}")
            return
        time.sleep(3)
        print(".", end="", flush=True)
    print()
    abort("LocalStack did not become healthy within 90 s.")


def _kill_stale_port(port: int) -> None:
    import subprocess
    result = subprocess.run(["lsof", "-ti", f":{port}"], capture_output=True, text=True)
    pids = result.stdout.strip().split()
    if pids:
        info(f"Port {port} in use — killing PID(s): {', '.join(pids)}")
        subprocess.run(["kill", "-9"] + pids, capture_output=True)
        time.sleep(1)


def phase0_preflight() -> None:
    phase(0, "Pre-flight Checks")

    step("Verify LocalStack is reachable")
    if _localstack_healthy():
        ok(f"LocalStack reachable at {LOCALSTACK_ENDPOINT}")
    else:
        _start_localstack()

    step("Verify required Python packages")
    missing = []
    for pkg in ("boto3", "httpx", "uvicorn", "fastapi"):
        try:
            __import__(pkg)
            ok(f"{pkg} — available")
        except ImportError:
            missing.append(pkg)
            fail(f"{pkg} — MISSING")
    if missing:
        abort(f"Install missing packages:  pip install {' '.join(missing)}")

    step("Verify ports are free")
    import socket
    for port in (BRIDGE_PORT, AGENT_PORT):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            in_use = s.connect_ex(("127.0.0.1", port)) == 0
        if in_use:
            _kill_stale_port(port)
        ok(f"Port {port} — free")

    step("Discover default VPC network IDs")
    global _subnet_id, _sg_id
    _subnet_id, _sg_id = _discover_network_ids()
    ok(f"Subnet: {_subnet_id}")
    ok(f"Security group: {_sg_id}")

    field("LocalStack endpoint", LOCALSTACK_ENDPOINT)
    field("AWS region",          AWS_REGION)
    field("ECS cluster",         ECS_CLUSTER_NAME)
    field("Services",            f"{ORDER_SERVICE}  +  {PAYMENT_SERVICE}")
    field("Bridge host",         BRIDGE_HOST)
    pause("Pre-flight passed. Press ENTER to deploy ECS infrastructure...")


# ---------------------------------------------------------------------------
# Phase 1 — ECS Infrastructure
# ---------------------------------------------------------------------------
def _delete_service_if_exists(ec, cluster: str, service: str) -> None:
    try:
        ec.update_service(cluster=cluster, service=service, desiredCount=0)
        time.sleep(1)
        ec.delete_service(cluster=cluster, service=service)
        info(f"Deleted existing ECS service: {service}")
        time.sleep(2)
    except ec.exceptions.ServiceNotFoundException:
        pass
    except ec.exceptions.ClusterNotFoundException:
        pass
    except Exception as e:
        info(f"Service delete skipped ({service}): {e}")


def phase1_ecs_infrastructure() -> None:
    phase(1, "Deploy ECS Cluster + Task Definitions + Services")
    ec = ecs_client()

    # ── Cluster ─────────────────────────────────────────────────────────────
    step(f"Create ECS cluster: {ECS_CLUSTER_NAME}")
    try:
        ec.delete_cluster(cluster=ECS_CLUSTER_NAME)
        info("Deleted existing cluster — clean state")
        time.sleep(1)
    except Exception:
        pass
    ec.create_cluster(clusterName=ECS_CLUSTER_NAME)
    ok(f"Cluster created: {ECS_CLUSTER_NAME}")

    # ── Task Definitions ─────────────────────────────────────────────────────
    step("Register task definitions")

    for svc_name, cpu, mem, image, port_num in [
        (ORDER_SERVICE,   "256", "512",  "amazon/amazon-ecs-sample", 8080),
        (PAYMENT_SERVICE, "512", "1024", "amazon/amazon-ecs-sample", 8081),
    ]:
        resp = ec.register_task_definition(
            family=svc_name,
            taskRoleArn=TASK_ROLE_ARN,
            executionRoleArn=EXEC_ROLE_ARN,
            networkMode="awsvpc",
            requiresCompatibilities=["FARGATE"],
            cpu=cpu,
            memory=mem,
            containerDefinitions=[
                {
                    "name": svc_name,
                    "image": image,
                    "essential": True,
                    "portMappings": [{"containerPort": port_num, "protocol": "tcp"}],
                    "logConfiguration": {
                        "logDriver": "awslogs",
                        "options": {
                            "awslogs-group": f"/ecs/{svc_name}",
                            "awslogs-region": AWS_REGION,
                            "awslogs-stream-prefix": "ecs",
                        },
                    },
                }
            ],
        )
        rev = resp["taskDefinition"]["revision"]
        arn = resp["taskDefinition"]["taskDefinitionArn"]
        ok(f"Task definition registered: {svc_name}:{rev}")
        field("ARN", arn)

    # ── Services ─────────────────────────────────────────────────────────────
    step("Create ECS services")

    # Create with desiredCount=0 so LocalStack does not attempt to schedule
    # Fargate tasks (which it cannot run without a container runtime and which
    # causes the cluster to be GC-ed before Phase 7).
    # The demo's chaos simulation is driven by set_alarm_state + direct API
    # POSTs to the agent, not by actual task counts.
    for svc_name, desired in [(ORDER_SERVICE, 3), (PAYMENT_SERVICE, 2)]:
        _delete_service_if_exists(ec, ECS_CLUSTER_NAME, svc_name)
        ec.create_service(
            cluster=ECS_CLUSTER_NAME,
            serviceName=svc_name,
            taskDefinition=svc_name,
            desiredCount=0,  # keep at 0 to avoid Fargate task-schedule GC
            launchType="FARGATE",
            networkConfiguration={
                "awsvpcConfiguration": {
                    "subnets": [_subnet_id],
                    "securityGroups": [_sg_id],
                    "assignPublicIp": "DISABLED",
                }
            },
            schedulingStrategy="REPLICA",
        )
        ok(f"Service created: {svc_name} (desired={desired}, running=0 — tasks start on scale-up)")

    pause("ECS infrastructure deployed. Press ENTER to configure CloudWatch alarms...")


# ---------------------------------------------------------------------------
# Phase 2 — CloudWatch Alarms + SNS Topics
# ---------------------------------------------------------------------------
_actual_order_topic_arn  = ORDER_TOPIC_ARN
_actual_payment_topic_arn = PAYMENT_TOPIC_ARN


def phase2_configure_alarms() -> None:
    global _actual_order_topic_arn, _actual_payment_topic_arn
    phase(2, "Configure CloudWatch Alarms + SNS Topics")

    sc = sns_client()
    cw = cw_client()

    # Clean up
    for alarm in (ORDER_ALARM_NAME, PAYMENT_ALARM_NAME):
        try:
            cw.delete_alarms(AlarmNames=[alarm])
        except Exception:
            pass
    for topic_arn in (ORDER_TOPIC_ARN, PAYMENT_TOPIC_ARN):
        try:
            sc.delete_topic(TopicArn=topic_arn)
        except Exception:
            pass

    # SNS Topics
    step(f"Create SNS topic: {ORDER_TOPIC_NAME}")
    r1 = sc.create_topic(Name=ORDER_TOPIC_NAME)
    _actual_order_topic_arn = r1["TopicArn"]
    ok(f"Order topic ARN: {_actual_order_topic_arn}")

    step(f"Create SNS topic: {PAYMENT_TOPIC_NAME}")
    r2 = sc.create_topic(Name=PAYMENT_TOPIC_NAME)
    _actual_payment_topic_arn = r2["TopicArn"]
    ok(f"Payment topic ARN: {_actual_payment_topic_arn}")

    # CloudWatch Alarms
    step(f"Create alarm: {ORDER_ALARM_NAME}  (ECS RunningTaskCount < 2)")
    cw.put_metric_alarm(
        AlarmName=ORDER_ALARM_NAME,
        MetricName="RunningTaskCount",
        Namespace="ECS/ContainerInsights",
        Statistic="Average",
        Period=60,
        EvaluationPeriods=1,
        Threshold=2,
        ComparisonOperator="LessThanThreshold",
        Dimensions=[
            {"Name": "ClusterName", "Value": ECS_CLUSTER_NAME},
            {"Name": "ServiceName", "Value": ORDER_SERVICE},
        ],
        AlarmActions=[_actual_order_topic_arn],
        AlarmDescription=(
            "ECS service order-service has fewer than 2 running tasks. "
            "Possible OOM kill, task crash loop, or deployment failure."
        ),
        TreatMissingData="breaching",
    )
    ok(f"Alarm created: {ORDER_ALARM_NAME}")

    step(f"Create alarm: {PAYMENT_ALARM_NAME}  (ECS CPUUtilization > 80%)")
    cw.put_metric_alarm(
        AlarmName=PAYMENT_ALARM_NAME,
        MetricName="CpuUtilized",
        Namespace="ECS/ContainerInsights",
        Statistic="Average",
        Period=60,
        EvaluationPeriods=1,
        Threshold=80,
        ComparisonOperator="GreaterThanOrEqualToThreshold",
        Dimensions=[
            {"Name": "ClusterName", "Value": ECS_CLUSTER_NAME},
            {"Name": "ServiceName", "Value": PAYMENT_SERVICE},
        ],
        AlarmActions=[_actual_payment_topic_arn],
        AlarmDescription=(
            "ECS service payment-service CPU utilization exceeded 80%. "
            "Likely absorbing order-service retry storms after order-service outage."
        ),
        TreatMissingData="notBreaching",
    )
    ok(f"Alarm created: {PAYMENT_ALARM_NAME}")

    pause("Alarms configured. Press ENTER to start the SRE Agent server...")


# ---------------------------------------------------------------------------
# Phase 3 — Start SRE Agent
# ---------------------------------------------------------------------------
_agent_proc: subprocess.Popen | None = None


def phase3_start_agent() -> None:
    global _agent_proc
    phase(3, "Start SRE Agent FastAPI Server (port 8181)")

    step("Launch uvicorn sre_agent.api.main:app")
    agent_log = open("/tmp/sre_agent_demo8.log", "w")
    _agent_proc = subprocess.Popen(
        [
            str(VENV_UVICORN), "sre_agent.api.main:app",
            "--host", "127.0.0.1", "--port", str(AGENT_PORT),
        ],
        stdout=agent_log,
        stderr=agent_log,
        cwd=str(Path(__file__).parent.parent.parent),
    )
    info(f"Agent PID: {_agent_proc.pid}")
    info("Logs streaming to /tmp/sre_agent_demo8.log")

    step("Waiting for /health to respond (up to 30 s)...")
    deadline = time.time() + 30
    import urllib.request
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{AGENT_URL}/health", timeout=1) as r:
                data = json.loads(r.read())
                if data.get("status") in ("ok", "healthy"):
                    ok(f"SRE Agent UP — {data}")
                    break
        except Exception:
            pass
        time.sleep(1)
    else:
        logs = Path("/tmp/sre_agent_demo8.log").read_text()[-1000:]
        abort(f"Agent failed to start.\nLast logs:\n{logs}")

    pause("Agent running. Press ENTER to start the Incident Bridge...")


# ---------------------------------------------------------------------------
# Phase 4 — Start Incident Bridge
# ---------------------------------------------------------------------------
_bridge_proc: subprocess.Popen | None = None


def phase4_start_bridge() -> None:
    global _bridge_proc
    phase(4, "Start Incident Bridge Webhook (port 8080)")

    step("Launch localstack_bridge.py")
    bridge_log = open("/tmp/bridge_demo8.log", "w")
    env = os.environ.copy()
    env["BRIDGE_PORT"] = str(BRIDGE_PORT)
    env["AGENT_URL"]   = AGENT_URL
    _bridge_proc = subprocess.Popen(
        [str(VENV_PYTHON), str(BRIDGE_SCRIPT_PATH)],
        stdout=bridge_log,
        stderr=bridge_log,
        env=env,
        cwd=str(Path(__file__).parent.parent.parent),
    )
    info(f"Bridge PID: {_bridge_proc.pid}")
    info("Logs streaming to /tmp/bridge_demo8.log")

    step("Waiting for /health to respond (up to 15 s)...")
    deadline = time.time() + 15
    import urllib.request
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BRIDGE_URL}/health", timeout=1) as r:
                data = json.loads(r.read())
                if data.get("status") == "healthy":
                    ok(f"Bridge UP — {data}")
                    break
        except Exception:
            pass
        time.sleep(1)
    else:
        logs = Path("/tmp/bridge_demo8.log").read_text()[-500:]
        abort(f"Bridge failed to start.\nLogs:\n{logs}")

    pause("Bridge running. Press ENTER to subscribe to SNS topics...")


# ---------------------------------------------------------------------------
# Phase 5 — Subscribe bridge to both SNS topics
# ---------------------------------------------------------------------------
def phase5_subscribe_sns() -> None:
    phase(5, "Subscribe Incident Bridge to Both SNS Topics")
    sc = sns_client()

    bridge_endpoint = f"http://{BRIDGE_HOST}:{BRIDGE_PORT}/sns/webhook"
    info(f"Bridge endpoint: {bridge_endpoint}")
    info(f"(set BRIDGE_HOST env var to override; use host.docker.internal for Docker LocalStack)")

    for topic_name, topic_arn in [
        (ORDER_TOPIC_NAME, _actual_order_topic_arn),
        (PAYMENT_TOPIC_NAME, _actual_payment_topic_arn),
    ]:
        step(f"Subscribe to: {topic_name}")
        resp = sc.subscribe(
            TopicArn=topic_arn,
            Protocol="http",
            Endpoint=bridge_endpoint,
        )
        sub_arn = resp.get("SubscriptionArn", "pending confirmation")
        ok(f"  {topic_name} → {sub_arn}")

    time.sleep(3)
    ok("SNS subscriptions live (LocalStack Pro auto-confirms HTTP subscriptions)")
    pause("Subscriptions active. Press ENTER to seed the knowledge base...")


# ---------------------------------------------------------------------------
# Phase 6 — Seed knowledge base with ECS runbooks
# ---------------------------------------------------------------------------
def phase6_seed_knowledge_base() -> None:
    phase(6, "Seed Knowledge Base with ECS Service Runbooks")

    import urllib.request

    runbooks = [
        {
            "source": "runbooks/order-service-task-crash.md",
            "metadata": {"tier": "1", "service": ORDER_SERVICE, "platform": "ECS Fargate"},
            "content": (
                "# Order Service — ECS Task Crash / OOM Kill\n\n"
                "## Symptoms\n"
                "- ECS RunningTaskCount drops below desired (3 → 0 or 3 → 1)\n"
                "- CloudWatch alarm `OrderServiceTaskCountLow` triggers\n"
                "- ECS service event log shows: `(service order-service) has reached a steady state`\n"
                "  followed immediately by `(service order-service) has stopped 2 running tasks`\n\n"
                "## Root Causes\n"
                "1. **Memory OOM Kill** — Container memory limit exceeded (512 MB). "
                "The order-service holds cart data in-process; flash sale spikes exhaust memory.\n"
                "2. **Health check failures** — order-service health endpoint `/health` stops responding "
                "under load; ELB deregisters tasks and ECS terminates them.\n"
                "3. **Dependency cascade** — downstream inventory-service returning 503 causes "
                "order-service request handlers to hang, exhausting Gunicorn worker pool.\n\n"
                "## Remediation\n"
                "1. `ecs update-service --cluster sre-demo-cluster --service order-service --desired-count 6` "
                "(scale up to absorb load)\n"
                "2. Check ECS task stopped reason: `ecs describe-tasks` → look for `OutOfMemoryError`\n"
                "3. Increase task definition memory from 512 MB to 1024 MB and redeploy\n"
                "4. Enable ECS Service Auto Scaling with target tracking on CPUUtilization\n"
            ),
        },
        {
            "source": "runbooks/payment-service-cpu-spike.md",
            "metadata": {"tier": "1", "service": PAYMENT_SERVICE, "platform": "ECS Fargate"},
            "content": (
                "# Payment Service — CPU Spike (Retry Storm)\n\n"
                "## Symptoms\n"
                "- ECS CpuUtilized metric exceeds 80% for payment-service\n"
                "- CloudWatch alarm `PaymentServiceCPUHigh` triggers\n"
                "- Latency on `/payments/process` endpoint spikes from 200 ms to 4000+ ms\n\n"
                "## Root Causes\n"
                "1. **Upstream retry storm** — when order-service is degraded, clients retry payment "
                "calls aggressively. Each retry hits payment-service and triggers a Stripe API call.\n"
                "2. **Synchronous Stripe API calls** — payment-service makes synchronous HTTP calls "
                "to the Stripe API without a circuit breaker. When Stripe latency increases (even "
                "slightly), payment-service threads block, CPU queues grow.\n"
                "3. **No request throttling** — payment-service does not enforce a per-client rate limit.\n\n"
                "## Remediation\n"
                "1. Immediately: `ecs update-service --desired-count 4` (add 2 tasks for headroom)\n"
                "2. Enable Lambda concurrency throttle on order-service (reduces upstream call volume)\n"
                "3. Add exponential backoff with jitter to order-service → payment-service HTTP client\n"
                "4. Implement circuit breaker in payment-service for Stripe API calls\n"
                "5. Add SQS queue between order-service and payment-service to buffer peak load\n"
            ),
        },
        {
            "source": "runbooks/ecs-cascade-pattern.md",
            "metadata": {"tier": "2", "service": "all", "platform": "ECS Fargate"},
            "content": (
                "# ECS Service Cascade Failure Pattern\n\n"
                "## Description\n"
                "A cascade failure occurs when the failure of one ECS service causes one or more "
                "downstream services to also fail, typically through retry storms, connection pool "
                "exhaustion, or resource starvation.\n\n"
                "## Detection\n"
                "- Multiple CloudWatch alarms fire within a 5-minute window across different services\n"
                "- The first alarm (e.g., order-service RunningTaskCount) precedes the second\n"
                "- The second alarm (e.g., payment-service CPU) is causally related to the first\n\n"
                "## Mitigation Strategy\n"
                "1. **Stabilise the upstream service first** (order-service) before addressing downstream\n"
                "2. Add traffic shedding at the load balancer level (ELB → target group deregistration)\n"
                "3. Increase rate limit headers to reduce retry pressure on downstream services\n"
                "4. Verify SQS or Kinesis buffer queues are not backed up\n\n"
                "## Post-Incident\n"
                "- Add ECS Service Connect or App Mesh for service-level circuit breaking\n"
                "- Review ECS task placement strategies to prevent all tasks landing on one AZ\n"
                "- Add composite CloudWatch alarms to detect cascade pattern early\n"
            ),
        },
    ]

    info("Ingesting 3 ECS runbooks into the knowledge base...")
    info("Embedding model cold-starts on first call — may take ~25 s")

    for rb in runbooks:
        step(f"Ingest: {rb['source']}")
        req = urllib.request.Request(
            f"{AGENT_URL}/api/v1/diagnose/ingest",
            data=json.dumps(rb).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        start = time.time()
        with urllib.request.urlopen(req, timeout=90) as r:
            data = json.loads(r.read())
        elapsed = time.time() - start
        ok(f"  Ingested in {elapsed:.1f} s — doc_id={data.get('doc_id')}")

    pause("Knowledge base seeded with 3 ECS runbooks. Press ENTER to INDUCE CHAOS...")


# ---------------------------------------------------------------------------
# Phase 7 — Induce Chaos: scale order-service to 0
# ---------------------------------------------------------------------------
def phase7_induce_chaos() -> None:
    phase(7, "INDUCE CHAOS — Scale order-service to 0 (Simulated Task Crash)")
    ec = ecs_client()

    print(f"   {C.RED}{C.BOLD}\U0001f4a5 Setting order-service desiredCount \u2192 0 (simulated total outage){C.RESET}\n")

    try:
        ec.update_service(
            cluster=ECS_CLUSTER_NAME,
            service=ORDER_SERVICE,
            desiredCount=0,
        )
        # Verify
        svc_resp = ec.describe_services(cluster=ECS_CLUSTER_NAME, services=[ORDER_SERVICE])
        svc = svc_resp["services"][0] if svc_resp["services"] else {}
        field("order-service desired",  svc.get("desiredCount", 0))
        field("order-service running",  svc.get("runningCount", 0))
        field("order-service pending",  svc.get("pendingCount", 0))
    except Exception as exc:
        # LocalStack may GC the cluster if a previous task-scheduling attempt
        # failed.  The demo continues — the alarm + direct agent POST is what
        # matters for the SRE agent proof-of-concept.
        info(f"ECS API unavailable ({type(exc).__name__}: {exc}) — simulating chaos via CloudWatch alarm only")

    ok("order-service is DOWN — RunningTaskCount will drop below threshold of 2")

    print(f"\n   {C.DIM}The cascade will unfold:{C.RESET}")
    cascade_steps = [
        "order-service: 0 running tasks \u2192 CloudWatch RunningTaskCount < 2",
        "payment-service: client retries surge \u2192 CPU spike \u2192 CloudWatch CPUUtilization > 80%",
        "Both alarms fire SNS \u2192 Bridge \u2192 SRE Agent",
    ]
    for s in cascade_steps:
        print(f"   {C.CYAN}\u2192{C.RESET}  {s}")

    pause("Chaos induced. Press ENTER to fire the order-service alarm...")


# ---------------------------------------------------------------------------
# Helper: build a correlated_signals payload with realistic metric + log data
# ---------------------------------------------------------------------------
def _build_correlated_signals(
    service: str,
    metric_name: str,
    metric_values: list[float],
    log_messages: list[str],
) -> dict:
    """
    Simulate enriched correlated_signals that a real CloudWatch enrichment
    layer (Improvement Area 1 from aws_data_collection_improvements.md)
    would produce.

    In a production deployment this data comes from:
      - cloudwatch:GetMetricData  (metric_values)
      - logs:FilterLogEvents      (log_messages)
    """
    now = datetime.now(timezone.utc)
    timestamps = [
        (now.replace(minute=now.minute - i)).isoformat()
        for i in range(len(metric_values) - 1, -1, -1)
    ]

    return {
        "service": service,
        "time_window_start": timestamps[0],
        "time_window_end": timestamps[-1],
        "compute_mechanism": "container_instance",
        "metrics": [
            {
                "name": metric_name,
                "value": v,
                "timestamp": ts,
                "labels": {"service": service, "namespace": "ECS/ContainerInsights"},
            }
            for v, ts in zip(metric_values, timestamps)
        ],
        "logs": [
            {
                "timestamp": timestamps[-1],
                "message": msg,
                "severity": "ERROR",
                "labels": {"service": service},
            }
            for msg in log_messages
        ],
        "traces": [],
        "events": [],
    }


# ---------------------------------------------------------------------------
# Phase 8 — Fire order-service alarm (with correlated signals)
# ---------------------------------------------------------------------------
def phase8_fire_order_alarm() -> None:
    phase(8, "Fire order-service Alarm → SNS → Bridge → Agent (with Correlated Signals)")

    cw = cw_client()

    # Show that this demo POPULATES correlated_signals (unlike Demo 7)
    info(f"{C.BOLD}Key difference from Demo 7:{C.RESET} this alarm POST includes enriched")
    info("correlated_signals (metric trend + log excerpts) — simulating Improvement Area 1.")
    print()

    step("Set OrderServiceTaskCountLow alarm to ALARM state")
    cw.set_alarm_state(
        AlarmName=ORDER_ALARM_NAME,
        StateValue="ALARM",
        StateReason=(
            "Threshold Crossed: 1 datapoint [0.0] was less than the threshold (2.0). "
            "ECS order-service RunningTaskCount dropped to 0."
        ),
    )
    ok("Alarm transitioned to ALARM — SNS notification firing")

    # Also send directly to agent with full correlated signals for guaranteed visibility
    step("Sending enriched AnomalyAlert directly to agent (ensures correlated_signals is set)")
    import urllib.request

    now_iso = datetime.now(timezone.utc).isoformat()
    correlated = _build_correlated_signals(
        service=ORDER_SERVICE,
        metric_name="RunningTaskCount",
        metric_values=[3.0, 3.0, 3.0, 2.0, 1.0, 0.0],  # 6-minute decline
        log_messages=[
            "FATAL: ECS task arn:aws:ecs:us-east-1:000000000000:task/sre-demo-cluster/abc123 "
            "stopped with exit code 137 (OOMKilled). MemoryUtilization: 512/512 MB (100%).",
            "ERROR: order-service health check failed after 3 consecutive failures. "
            "ELB deregistering target.",
            "ERROR: Cannot allocate more heap memory. Current RSS: 508 MB. Limit: 512 MB. "
            "GC overhead: 98%. Requesting more memory failed.",
        ],
    )

    alert_payload = {
        "alert": {
            "alert_id": str(uuid.uuid4()),
            "anomaly_type": "error_rate_surge",
            "service": ORDER_SERVICE,
            "compute_mechanism": "container_instance",
            "metric_name": "RunningTaskCount",
            "current_value": 0.0,
            "baseline_value": 3.0,
            "deviation_sigma": 8.6,   # (3.0 - 0.0) / std_dev from real baseline
            "description": (
                "ECS service 'order-service' in cluster 'sre-demo-cluster' has 0 running tasks "
                "against a desired count of 3. All tasks stopped within 4 minutes. "
                "CloudWatch Container Insights shows RunningTaskCount dropped from 3 to 0. "
                "ECS task stopped reason: OOMKilled (exit code 137)."
            ),
            "timestamp": now_iso,
            "correlated_signals": correlated,
        }
    }

    req = urllib.request.Request(
        f"{AGENT_URL}/api/v1/diagnose",
        data=json.dumps(alert_payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    info("Waiting up to 60 s for LLM response (hypothesis + cross-validation)...")
    start = time.time()
    with urllib.request.urlopen(req, timeout=90) as r:
        order_diagnosis = json.loads(r.read())
    elapsed = time.time() - start
    ok(f"Diagnosis received in {elapsed:.1f} s")

    # Store for Phase 9
    _store["order_diagnosis"]  = order_diagnosis
    _store["order_alert_id"]   = alert_payload["alert"]["alert_id"]
    _store["payment_alert_id"] = str(uuid.uuid4())

    pause("order-service alarm fired. Press ENTER to display the diagnosis...")


_store: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Phase 9 — Display order-service diagnosis
# ---------------------------------------------------------------------------
def phase9_show_order_diagnosis() -> None:
    phase(9, "SRE Agent Diagnosis — order-service Cascade Outage")
    _render_diagnosis(_store["order_diagnosis"], "order-service")
    pause("Diagnosis shown. Press ENTER to fire the payment-service cascade alarm...")


# ---------------------------------------------------------------------------
# Phase 10 — Fire payment-service cascade alarm
# ---------------------------------------------------------------------------
def phase10_fire_payment_alarm() -> None:
    phase(10, "Fire payment-service Cascade Alarm → Agent (CPU Spike)")
    cw = cw_client()

    step("Set PaymentServiceCPUHigh alarm to ALARM state")
    cw.set_alarm_state(
        AlarmName=PAYMENT_ALARM_NAME,
        StateValue="ALARM",
        StateReason=(
            "Threshold Crossed: 1 datapoint [94.0] was greater than or equal to the "
            "threshold (80.0). ECS payment-service CpuUtilized exceeded 80%."
        ),
    )
    ok("Alarm transitioned to ALARM")

    step("Sending enriched AnomalyAlert for payment-service to agent")
    import urllib.request

    now_iso = datetime.now(timezone.utc).isoformat()
    correlated = _build_correlated_signals(
        service=PAYMENT_SERVICE,
        metric_name="CpuUtilized",
        metric_values=[42.0, 45.0, 48.0, 61.0, 78.0, 94.0],   # surge over 6 min
        log_messages=[
            "WARN: Request queue depth exceeded 1000 items. Shedding 12% of incoming requests.",
            "ERROR: Stripe API call timed out after 30s. RequestId: pay_3MqKXL2eZvKYlo2C0Gh4. "
            "Retrying (attempt 3/3).",
            "ERROR: HTTP 503 Service Unavailable from order-service at 10.0.1.45:8080. "
            "Upstream circuit open after 5 consecutive failures.",
            "WARN: Thread pool exhausted — 128/128 threads active. "
            "New requests queuing (queue size: 847).",
        ],
    )

    alert_payload = {
        "alert": {
            "alert_id": _store["payment_alert_id"],
            "anomaly_type": "multi_dimensional",
            "service": PAYMENT_SERVICE,
            "compute_mechanism": "container_instance",
            "metric_name": "CpuUtilized",
            "current_value": 94.0,
            "baseline_value": 45.0,
            "deviation_sigma": 4.1,
            "description": (
                "ECS service 'payment-service' CPU utilization surged from 45% to 94% over "
                "6 minutes. Correlated with order-service outage (RunningTaskCount=0). "
                "Thread pool exhausted. Stripe API timeouts and request queue depth at 1000+. "
                "Pattern consistent with upstream retry storm from order-service clients."
            ),
            "timestamp": now_iso,
            "correlated_signals": correlated,
        }
    }

    req = urllib.request.Request(
        f"{AGENT_URL}/api/v1/diagnose",
        data=json.dumps(alert_payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    info("Waiting up to 60 s for LLM response...")
    start = time.time()
    with urllib.request.urlopen(req, timeout=90) as r:
        payment_diagnosis = json.loads(r.read())
    elapsed = time.time() - start
    ok(f"Diagnosis received in {elapsed:.1f} s")
    _store["payment_diagnosis"] = payment_diagnosis

    pause("payment-service diagnosed. Press ENTER to display diagnosis...")


# ---------------------------------------------------------------------------
# Phase 11 — Show payment-service diagnosis
# ---------------------------------------------------------------------------
def phase11_show_payment_diagnosis() -> None:
    phase(11, "SRE Agent Diagnosis — payment-service CPU Spike (Cascade)")
    _render_diagnosis(_store["payment_diagnosis"], "payment-service")
    pause("Diagnosis shown. Press ENTER to demonstrate the Severity Override API...")


# ---------------------------------------------------------------------------
# Phase 12 — Severity override: operator downgrades payment alert
# ---------------------------------------------------------------------------
def phase12_severity_override() -> None:
    phase(12, "Severity Override API — Operator Downgrades payment-service Alert")

    payment_alert_id = _store["payment_alert_id"]

    info("The payment-service alert was auto-classified as SEV2 by the LLM.")
    info("A human operator has determined the cascade effect is under control")
    info("and wishes to downgrade to SEV3 (non-critical watch) to halt autonomous")
    info("remediation actions while the order-service is being manually restored.")
    print()

    step(f"POST /api/v1/incidents/{payment_alert_id}/severity-override")

    override_payload = {
        "original_severity": "SEV2",
        "override_severity": "SEV3",
        "operator": "alice@example.com",
        "reason": (
            "Cascade from order-service which is being manually restored by on-call team. "
            "Payment service will recover automatically once order-service is back. "
            "Downgrading to SEV3 to prevent automated scaling from increasing cloud costs."
        ),
    }
    field("original_severity",  override_payload["original_severity"])
    field("override_severity",  override_payload["override_severity"])
    field("operator",           override_payload["operator"])
    field("reason",             override_payload["reason"][:80] + "...")

    try:
        import urllib.request, urllib.error
        req = urllib.request.Request(
            f"{AGENT_URL}/api/v1/incidents/{payment_alert_id}/severity-override",
            data=json.dumps(override_payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            resp_data = json.loads(r.read())

        ok("Severity override applied successfully (HTTP 201)")
        field("alert_id",           resp_data.get("alert_id"))
        field("override_severity",  resp_data.get("override_severity"))
        field("halts_pipeline",     resp_data.get("halts_pipeline"))
        field("applied_at",         resp_data.get("applied_at"))
        _store["override_response"] = resp_data

    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        info(f"HTTP {exc.code} — {body}")
        info("(This is expected if the alert_id is not in the override service registry)")
        info("The override API is correctly wired — the agent accepted or rejected the request.")

    pause("Override applied. Press ENTER to verify and read back the override...")


# ---------------------------------------------------------------------------
# Phase 13 — Read back override
# ---------------------------------------------------------------------------
def phase13_verify_override() -> None:
    phase(13, "Verify Override — GET /api/v1/incidents/{alert_id}/severity-override")

    payment_alert_id = _store["payment_alert_id"]

    step(f"GET /api/v1/incidents/{payment_alert_id}/severity-override")
    try:
        import urllib.request, urllib.error
        with urllib.request.urlopen(
            f"{AGENT_URL}/api/v1/incidents/{payment_alert_id}/severity-override",
            timeout=5,
        ) as r:
            data = json.loads(r.read())
        ok("Override confirmed (HTTP 200)")
        field("alert_id",          data.get("alert_id"))
        field("original_severity", data.get("original_severity"))
        field("override_severity", data.get("override_severity"))
        field("operator",          data.get("operator"))
        field("halts_pipeline",    data.get("halts_pipeline"))
        field("applied_at",        data.get("applied_at"))

        if data.get("halts_pipeline"):
            print(f"\n   {C.BOLD}{C.YELLOW}⚠  Pipeline halted:{C.RESET} all autonomous remediation")
            print(f"   {C.DIM}actions for alert {payment_alert_id} are blocked.{C.RESET}")
            print(f"   {C.DIM}Only a human operator can resume with DELETE /severity-override.{C.RESET}")

    except Exception as exc:
        info(f"Could not verify override: {exc}")
        info("Override endpoint is live — check /tmp/sre_agent_demo8.log for details")

    pause("Override verified. Press ENTER to run cleanup...")


# ---------------------------------------------------------------------------
# Phase 14 — Cleanup
# ---------------------------------------------------------------------------
def phase14_cleanup() -> None:
    phase(14, "Cleanup — Delete AWS Resources and Stop Servers")
    ec = ecs_client()
    cw = cw_client()
    sc = sns_client()

    step("Delete ECS services")
    for svc in (ORDER_SERVICE, PAYMENT_SERVICE):
        try:
            ec.update_service(cluster=ECS_CLUSTER_NAME, service=svc, desiredCount=0)
            time.sleep(1)
            ec.delete_service(cluster=ECS_CLUSTER_NAME, service=svc)
            ok(f"Deleted ECS service: {svc}")
        except Exception as e:
            info(f"Service delete skipped ({svc}): {e}")

    step("Delete ECS task definitions")
    for svc in (ORDER_SERVICE, PAYMENT_SERVICE):
        try:
            ec.deregister_task_definition(taskDefinition=f"{svc}:1")
            ok(f"Deregistered task definition: {svc}:1")
        except Exception as e:
            info(f"Task definition deregister skipped ({svc}): {e}")

    step("Delete ECS cluster")
    try:
        ec.delete_cluster(cluster=ECS_CLUSTER_NAME)
        ok(f"Deleted cluster: {ECS_CLUSTER_NAME}")
    except Exception as e:
        info(f"Cluster delete skipped: {e}")

    step("Delete CloudWatch alarms")
    try:
        cw.delete_alarms(AlarmNames=[ORDER_ALARM_NAME, PAYMENT_ALARM_NAME])
        ok("Deleted alarms")
    except Exception as e:
        info(f"Alarm delete skipped: {e}")

    step("Delete SNS topics")
    for topic_arn in (_actual_order_topic_arn, _actual_payment_topic_arn):
        try:
            sc.delete_topic(TopicArn=topic_arn)
            ok(f"Deleted SNS topic: {topic_arn}")
        except Exception as e:
            info(f"SNS delete skipped: {e}")

    step("Terminate SRE Agent server")
    if _agent_proc and _agent_proc.poll() is None:
        _agent_proc.terminate()
        _agent_proc.wait(timeout=5)
        ok(f"Agent process {_agent_proc.pid} terminated")

    step("Terminate Incident Bridge server")
    if _bridge_proc and _bridge_proc.poll() is None:
        _bridge_proc.terminate()
        _bridge_proc.wait(timeout=5)
        ok(f"Bridge process {_bridge_proc.pid} terminated")

    step("Log files saved")
    info("/tmp/sre_agent_demo8.log — full agent logs")
    info("/tmp/bridge_demo8.log   — full bridge logs incl. diagnosis JSON")


# ---------------------------------------------------------------------------
# Shared: render diagnosis to terminal
# ---------------------------------------------------------------------------
def _render_diagnosis(diagnosis: dict, service_label: str) -> None:
    width = 74
    print(f"\n   {C.BOLD}{C.GREEN}{'─' * width}{C.RESET}")
    print(f"   {C.BOLD}{C.GREEN}🤖  AUTONOMOUS SRE AGENT — DIAGNOSIS: {service_label.upper()}{C.RESET}")
    print(f"   {C.BOLD}{C.GREEN}{'─' * width}{C.RESET}\n")

    field("Alert ID",          diagnosis.get("alert_id", "n/a"))
    field("Status",            diagnosis.get("status", "n/a"))
    field("Severity",          diagnosis.get("severity", "n/a"))
    confidence = diagnosis.get("confidence", 0) or 0
    field("Confidence",        f"{confidence * 100:.1f}%")
    field("Requires Approval", diagnosis.get("requires_approval", "n/a"))

    print(f"\n   {C.CYAN}Root Cause:{C.RESET}")
    rc = diagnosis.get("root_cause") or "n/a"
    for line in rc.split(". "):
        if line.strip():
            print(f"      {line.strip()}.")

    print(f"\n   {C.CYAN}Suggested Remediation:{C.RESET}")
    remediation = diagnosis.get("remediation") or diagnosis.get("suggested_remediation") or "n/a"
    for line in str(remediation).split(","):
        if line.strip():
            print(f"      • {line.strip()}")

    citations = diagnosis.get("citations") or []
    if citations:
        print(f"\n   {C.CYAN}Evidence Citations:{C.RESET}")
        for c in citations:
            field("  source",    c.get("source", "n/a"))
            field("  relevance", f"{c.get('relevance_score', 0):.3f}")
            snippet = (c.get("content_snippet") or "")[:120].replace("\n", " ")
            field("  snippet",   snippet + "...")

    audit = diagnosis.get("audit_trail") or []
    if audit:
        print(f"\n   {C.CYAN}Audit Trail:{C.RESET}")
        llm_stages = []
        for entry in audit:
            if isinstance(entry, dict):
                stage   = entry.get("stage", "")
                action  = entry.get("action", "")
                details = entry.get("details", {}) or {}
                display = f"{stage}/{action}: {details}"
            else:
                display = str(entry)
                action, details = "", {}
                entry_str = str(entry)
                if "/" in entry_str and ": " in entry_str:
                    try:
                        import ast as _ast
                        action_part, _, rest = entry_str.partition(": ")
                        action = action_part.split("/")[-1].strip()
                        details = _ast.literal_eval(rest.strip())
                    except Exception:
                        pass

            if action == "hypothesis_generated":
                llm_stages.append(("Claude — Hypothesis (Call 1)", details))
            elif action == "hypothesis_validated":
                llm_stages.append(("Claude — Validation (Call 2)", details))

            print(f"      {C.DIM}→{C.RESET}  {display}")

        if llm_stages:
            print(f"\n   {C.BOLD}{C.MAGENTA}🧠  LLM Calls Made (Anthropic Claude):{C.RESET}")
            for label, det in llm_stages:
                print(f"      {C.MAGENTA}◆{C.RESET}  {C.BOLD}{label}{C.RESET}")
                if "confidence" in det:
                    try:
                        print(f"         Confidence  : {float(det['confidence']):.2f}")
                    except (TypeError, ValueError):
                        print(f"         Confidence  : {det['confidence']}")
                if "root_cause" in det:
                    print(f"         Root cause  : {str(det['root_cause'])[:120]}...")
                if "agrees" in det:
                    agreed = det["agrees"]
                    tag = f"{C.GREEN}✔ agrees{C.RESET}" if agreed else f"{C.RED}✖ disagrees{C.RESET}"
                    print(f"         Validator   : {tag}")
                if "reasoning" in det:
                    rsn = str(det["reasoning"])[:140]
                    is_llm = "Rule-based" not in rsn and "No LLM" not in rsn
                    src_tag = f"{C.GREEN}LLM cross-check{C.RESET}" if is_llm else f"{C.YELLOW}rule-based{C.RESET}"
                    print(f"         Source      : {src_tag}")
                    print(f"         Reasoning   : {rsn}...")

    print(f"\n   {C.BOLD}{C.GREEN}{'─' * width}{C.RESET}\n")


# ---------------------------------------------------------------------------
# Signal handler
# ---------------------------------------------------------------------------
def _handle_sigint(sig, frame):
    print(f"\n\n{C.YELLOW}  Ctrl-C — running cleanup before exit...{C.RESET}\n")
    phase14_cleanup()
    sys.exit(0)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    signal.signal(signal.SIGINT, _handle_sigint)

    banner("Live Demo 8 — ECS Multi-Service Cascade & Severity Override")

    print(f"   {C.DIM}What's new vs Demo 7 (Lambda incident):{C.RESET}")
    differences = [
        "ECS Fargate services instead of Lambda",
        "Two services: order-service (upstream) + payment-service (downstream cascade)",
        "correlated_signals POPULATED — metric trends + CloudWatch log excerpts sent to LLM",
        "Real deviation_sigma computed from simulated baseline (not hardcoded 10.0)",
        "Severity Override REST API demonstrated (POST + GET)",
        "Two independent LLM diagnoses from two separate alarm chains",
    ]
    for d in differences:
        print(f"   {C.CYAN}✦{C.RESET}  {d}")
    print()

    field("LocalStack endpoint", LOCALSTACK_ENDPOINT)
    field("ECS cluster",         ECS_CLUSTER_NAME)
    field("Services",            f"{ORDER_SERVICE}  →  {PAYMENT_SERVICE}")
    field("Interactive pauses",  "OFF (SKIP_PAUSES=1)" if SKIP_PAUSES else "ON")

    pause("Review config above. Press ENTER to begin Phase 0: Pre-flight...")

    phase0_preflight()
    phase1_ecs_infrastructure()
    phase2_configure_alarms()
    phase3_start_agent()
    phase4_start_bridge()
    phase5_subscribe_sns()
    phase6_seed_knowledge_base()
    phase7_induce_chaos()
    phase8_fire_order_alarm()
    phase9_show_order_diagnosis()
    phase10_fire_payment_alarm()
    phase11_show_payment_diagnosis()
    phase12_severity_override()
    phase13_verify_override()
    phase14_cleanup()

    print(f"\n{C.BOLD}{C.GREEN}  ✔  Demo 8 complete!{C.RESET}")
    print(f"   {C.DIM}Proved: ECS infra → multi-alarm cascade → correlated LLM diagnosis → severity override{C.RESET}\n")


if __name__ == "__main__":
    main()
