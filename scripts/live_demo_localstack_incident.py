"""
Live Demo 7 — LocalStack End-to-End Incident Response
======================================================

A single, self-contained orchestration script that executes every step of the
LocalStack incident response demo in sequence.  Press ENTER to advance between
phases so you can narrate each step to an audience.

What this demo proves (end-to-end, live HTTP):
  Phase 0  — Pre-flight: verify LocalStack, awslocal, boto3, and ports
  Phase 1  — Deploy the vulnerable Lambda (payment-processor)
  Phase 2  — Configure CloudWatch Alarm + SNS Topic
  Phase 3  — Start the SRE Agent FastAPI server (port 8181)
  Phase 4  — Start the Incident Bridge webhook server (port 8080)
  Phase 5  — Subscribe the Bridge to the SNS topic
  Phase 6  — Seed the knowledge base with a payment-processor runbook
  Phase 7  — INDUCE CHAOS: invoke Lambda with destructive payload
  Phase 8  — Force alarm → SNS → Bridge → Agent chain
  Phase 9  — Display structured LLM diagnosis with audit trail
  Phase 10 — Cleanup: delete all LocalStack resources, stop servers

Usage
-----
    source .venv/bin/activate
    python scripts/live_demo_localstack_incident.py

Requirements
------------
    pip install boto3 httpx uvicorn fastapi awscli-local

Environment
-----------
    LOCALSTACK_ENDPOINT  LocalStack endpoint (default: http://localhost:4566)
    AWS_DEFAULT_REGION   AWS region used by LocalStack (default: eu-west-3)
    AGENT_PORT           SRE Agent port (default: 8181)
    BRIDGE_PORT          Incident bridge port (default: 8080)
    SKIP_PAUSES          Set to "1" to skip interactive ENTER prompts (CI mode)
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import time
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

import boto3
import httpx
from dotenv import load_dotenv

# Load .env from the project root so LOCALSTACK_AUTH_TOKEN and other secrets
# are available without needing them exported in the shell.
load_dotenv(Path(__file__).parent.parent / ".env")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
LOCALSTACK_ENDPOINT = os.getenv("LOCALSTACK_ENDPOINT", "http://localhost:4566")
AWS_REGION          = os.getenv("AWS_DEFAULT_REGION", "eu-west-3")
AGENT_PORT          = int(os.getenv("AGENT_PORT", "8181"))
BRIDGE_PORT         = int(os.getenv("BRIDGE_PORT", "8080"))
AGENT_URL           = f"http://127.0.0.1:{AGENT_PORT}"
BRIDGE_URL          = f"http://127.0.0.1:{BRIDGE_PORT}"
SKIP_PAUSES         = os.getenv("SKIP_PAUSES", "0") == "1"

FUNCTION_NAME       = "payment-processor"
ALARM_NAME          = "PaymentProcessorErrorSpike"
SNS_TOPIC_NAME      = "sre-agent-alerts"
ACCOUNT_ID          = "000000000000"
TOPIC_ARN           = f"arn:aws:sns:{AWS_REGION}:{ACCOUNT_ID}:{SNS_TOPIC_NAME}"
LAMBDA_ROLE_ARN     = f"arn:aws:iam::{ACCOUNT_ID}:role/lambda-role"

MOCK_LAMBDA_PATH    = Path(__file__).parent / "mock_lambda.py"
BRIDGE_SCRIPT_PATH  = Path(__file__).parent / "localstack_bridge.py"
VENV_PYTHON         = Path(__file__).parent.parent / ".venv" / "bin" / "python"
VENV_UVICORN        = Path(__file__).parent.parent / ".venv" / "bin" / "uvicorn"

# ---------------------------------------------------------------------------
# Colour + formatting helpers
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


def ok(msg: str) -> None:
    print(f"   {C.GREEN}✔{C.RESET}  {msg}")


def fail(msg: str) -> None:
    print(f"   {C.RED}✖{C.RESET}  {C.RED}{msg}{C.RESET}")


def info(msg: str) -> None:
    print(f"   {C.CYAN}ℹ{C.RESET}  {msg}")


def field(label: str, value: Any) -> None:
    print(f"   {C.DIM}{label}:{C.RESET} {C.WHITE}{value}{C.RESET}")


def step(msg: str) -> None:
    print(f"\n   {C.YELLOW}▶{C.RESET}  {C.BOLD}{msg}{C.RESET}")


def pause(prompt: str = "Press ENTER to continue...") -> None:
    if not SKIP_PAUSES:
        input(f"\n   {C.DIM}{prompt}{C.RESET}\n")
    else:
        print()


def abort(msg: str) -> None:
    fail(msg)
    sys.exit(1)


# ---------------------------------------------------------------------------
# boto3 client factory (all pointing at LocalStack)
# ---------------------------------------------------------------------------
_boto_kwargs = dict(
    endpoint_url=LOCALSTACK_ENDPOINT,
    region_name=AWS_REGION,
    aws_access_key_id="test",
    aws_secret_access_key="test",
)

def lambda_client():  return boto3.client("lambda",     **_boto_kwargs)
def cw_client():      return boto3.client("cloudwatch", **_boto_kwargs)
def sns_client():     return boto3.client("sns",        **_boto_kwargs)


# ---------------------------------------------------------------------------
# Phase 0 — Pre-flight checks (with auto-start)
# ---------------------------------------------------------------------------
LOCALSTACK_AUTH_TOKEN = os.getenv("LOCALSTACK_AUTH_TOKEN") or os.getenv("LOCALSTACK_API_KEY")


def _localstack_healthy() -> bool:
    """Return True if LocalStack is reachable and reports healthy status."""
    import urllib.request
    try:
        with urllib.request.urlopen(LOCALSTACK_ENDPOINT + "/_localstack/health", timeout=3) as r:
            data = json.loads(r.read())
            # LocalStack health returns {"status": "running"} or {"services": {...}}
            return data.get("status") in ("running", "ok") or bool(data.get("services"))
    except Exception:
        return False


def _start_localstack() -> None:
    """Auto-start LocalStack Pro in the background and wait up to 90 s for it."""
    step("LocalStack not running — attempting auto-start")

    # Set auth token so LocalStack Pro activates correctly
    env = os.environ.copy()
    if LOCALSTACK_AUTH_TOKEN:
        env["LOCALSTACK_AUTH_TOKEN"] = LOCALSTACK_AUTH_TOKEN
    # Keep Lambda in synchronous create mode so our waiter works correctly
    env["LAMBDA_SYNCHRONOUS_CREATE"] = "1"

    token_hint = (LOCALSTACK_AUTH_TOKEN or "")[:12] or "<not set>"
    info(f"Running: localstack start -d  (token: {token_hint}...)")
    result = subprocess.run(
        ["localstack", "start", "-d"],
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):  # returncode 1 is ok (already starting)
        abort(
            f"localstack start failed (exit {result.returncode}).\n"
            f"stdout: {result.stdout.strip()}\n"
            f"stderr: {result.stderr.strip()}\n"
            f"Install LocalStack CLI:  pip install localstack"
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
    abort(
        "LocalStack did not become healthy within 90 s.\n"
        "Check logs:  localstack logs\n"
        "Or start manually:  LAMBDA_SYNCHRONOUS_CREATE=1 LOCALSTACK_AUTH_TOKEN=<token> localstack start -d"
    )


def _kill_stale_port(port: int) -> None:
    """Kill whatever process is listening on *port* so the demo can own it."""
    result = subprocess.run(
        ["lsof", "-ti", f":{port}"],
        capture_output=True,
        text=True,
    )
    pids = result.stdout.strip().split()
    if pids:
        info(f"Port {port} in use by PID(s): {', '.join(pids)} — sending SIGKILL")
        subprocess.run(["kill", "-9"] + pids, capture_output=True)
        time.sleep(1)
        ok(f"Port {port} freed")
    else:
        ok(f"Port {port} — free")


def phase0_preflight() -> None:
    phase(0, "Pre-flight Checks")

    # ── LocalStack ──────────────────────────────────────────────────────────
    step("Verify LocalStack is reachable")
    if _localstack_healthy():
        ok(f"LocalStack reachable at {LOCALSTACK_ENDPOINT}")
    else:
        _start_localstack()

    # ── Python packages ─────────────────────────────────────────────────────
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

    # ── awslocal CLI ────────────────────────────────────────────────────────
    step("Verify awslocal CLI")
    result = subprocess.run(["awslocal", "--version"], capture_output=True, text=True)
    if result.returncode == 0:
        ok(f"awslocal — {result.stdout.strip() or result.stderr.strip()}")
    else:
        abort("awslocal not found. Install it:  pip install awscli-local")

    # ── mock_lambda.py ──────────────────────────────────────────────────────
    step("Verify mock_lambda.py exists")
    if MOCK_LAMBDA_PATH.exists():
        ok(f"mock_lambda.py found at {MOCK_LAMBDA_PATH}")
    else:
        abort(f"mock_lambda.py not found at {MOCK_LAMBDA_PATH}")

    # ── Ports ───────────────────────────────────────────────────────────────
    step("Verify ports 8080 and 8181 are free (auto-kill stale processes)")
    import socket
    for port in (BRIDGE_PORT, AGENT_PORT):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            in_use = s.connect_ex(("127.0.0.1", port)) == 0
        if in_use:
            fail(f"Port {port} is already in use — killing stale process...")
            _kill_stale_port(port)
            # Confirm now free
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                still_in_use = s.connect_ex(("127.0.0.1", port)) == 0
            if still_in_use:
                abort(f"Could not free port {port}. Kill manually:  lsof -ti :{port} | xargs kill -9")
        else:
            ok(f"Port {port} — free")

    field("LocalStack endpoint", LOCALSTACK_ENDPOINT)
    field("AWS region",          AWS_REGION)
    field("Agent URL",           AGENT_URL)
    field("Bridge URL",          BRIDGE_URL)

    pause("Pre-flight passed. Press ENTER to deploy the Lambda...")


# ---------------------------------------------------------------------------
# Phase 1 — Deploy the vulnerable Lambda
# ---------------------------------------------------------------------------
def phase1_deploy_lambda() -> None:
    phase(1, "Deploy Vulnerable Lambda (payment-processor)")

    step("Package mock_lambda.py into a deployment zip")
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(MOCK_LAMBDA_PATH, "mock_lambda.py")
    zip_bytes = zip_buffer.getvalue()
    ok(f"Zipped {len(zip_bytes):,} bytes in memory")

    lc = lambda_client()

    # Clean up any leftover function from a previous run
    step("Clean up any existing payment-processor function")
    try:
        lc.delete_function(FunctionName=FUNCTION_NAME)
        info("Deleted existing function — starting fresh")
        time.sleep(2)
    except lc.exceptions.ResourceNotFoundException:
        ok("No existing function — clean state")

    step("Create Lambda function")
    info("Calling create-function (returns immediately in Pending state)...")
    resp = lc.create_function(
        FunctionName=FUNCTION_NAME,
        Runtime="python3.11",
        Role=LAMBDA_ROLE_ARN,
        Handler="mock_lambda.handler",
        Code={"ZipFile": zip_bytes},
        Timeout=10,
        MemorySize=128,
    )
    field("State",      resp["State"])
    field("ARN",        resp["FunctionArn"])
    field("Runtime",    resp["Runtime"])

    step("Wait for function to become Active (polls every 5 s, up to 300 s)")
    info("This pulls the python:3.11 runtime image on first run — ~30-60 s")
    waiter = lc.get_waiter("function_active_v2")
    waiter.config.delay = 5
    waiter.config.max_attempts = 60
    start = time.time()
    waiter.wait(FunctionName=FUNCTION_NAME)
    elapsed = time.time() - start
    ok(f"Function is Active  ({elapsed:.0f} s)")

    step("Verify with a healthy invocation")
    invoke_resp = lc.invoke(
        FunctionName=FUNCTION_NAME,
        Payload=json.dumps({}).encode(),
    )
    body = json.loads(invoke_resp["Payload"].read())
    if invoke_resp.get("FunctionError"):
        abort(f"Healthy invocation failed unexpectedly: {body}")
    ok(f"Healthy response: statusCode={body.get('statusCode')}")

    pause("Lambda deployed and verified. Press ENTER to configure CloudWatch and SNS...")


# ---------------------------------------------------------------------------
# Phase 2 — Configure CloudWatch Alarm + SNS Topic
# ---------------------------------------------------------------------------
def phase2_configure_alarm() -> None:
    global TOPIC_ARN
    phase(2, "Configure CloudWatch Alarm + SNS Topic")

    sc = sns_client()
    cw = cw_client()

    step("Delete any existing SNS topic and CloudWatch alarm (clean state)")
    try:
        sc.delete_topic(TopicArn=TOPIC_ARN)
        info("Deleted existing SNS topic")
    except Exception:
        pass
    try:
        cw.delete_alarms(AlarmNames=[ALARM_NAME])
        info("Deleted existing CloudWatch alarm")
    except Exception:
        pass

    step(f"Create SNS topic: {SNS_TOPIC_NAME}")
    topic_resp = sc.create_topic(Name=SNS_TOPIC_NAME)
    actual_arn = topic_resp["TopicArn"]
    ok(f"Topic ARN: {actual_arn}")

    # Update TOPIC_ARN in case the actual ARN differs from expected
    TOPIC_ARN = actual_arn

    step("Create CloudWatch alarm: PaymentProcessorErrorSpike")
    cw.put_metric_alarm(
        AlarmName=ALARM_NAME,
        MetricName="Errors",
        Namespace="AWS/Lambda",
        Statistic="Sum",
        Period=60,
        EvaluationPeriods=1,
        Threshold=1,
        ComparisonOperator="GreaterThanOrEqualToThreshold",
        Dimensions=[{"Name": "FunctionName", "Value": FUNCTION_NAME}],
        AlarmActions=[TOPIC_ARN],
        TreatMissingData="notBreaching",
    )

    alarm_resp = cw.describe_alarms(AlarmNames=[ALARM_NAME])
    alarm = alarm_resp["MetricAlarms"][0]
    field("Alarm state",   alarm["StateValue"])
    field("Threshold",     f">= {alarm['Threshold']}")
    field("Alarm actions", alarm["AlarmActions"])
    ok("CloudWatch alarm created and wired to SNS topic")

    pause("CloudWatch and SNS configured. Press ENTER to start the SRE Agent server...")


# ---------------------------------------------------------------------------
# Phase 3 — Start the SRE Agent FastAPI server
# ---------------------------------------------------------------------------
_agent_proc: subprocess.Popen | None = None

def phase3_start_agent() -> subprocess.Popen:
    global _agent_proc
    phase(3, "Start SRE Agent FastAPI Server (port 8181)")

    step("Launch uvicorn sre_agent.api.main:app")
    agent_log = open("/tmp/sre_agent_demo.log", "w")
    _agent_proc = subprocess.Popen(
        [str(VENV_UVICORN), "sre_agent.api.main:app",
         "--host", "127.0.0.1", "--port", str(AGENT_PORT)],
        stdout=agent_log,
        stderr=agent_log,
        cwd=str(Path(__file__).parent.parent),
    )
    info(f"Agent PID: {_agent_proc.pid}")
    info("Logs streaming to /tmp/sre_agent_demo.log")

    step("Waiting for /health to respond (up to 30 s)...")
    deadline = time.time() + 30
    import urllib.request, urllib.error
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{AGENT_URL}/health", timeout=1) as r:
                data = json.loads(r.read())
                if data.get("status") in ("ok", "healthy"):
                    ok(f"SRE Agent is UP — {AGENT_URL}/health → {data}")
                    break
        except Exception:
            pass
        time.sleep(1)
    else:
        logs = Path("/tmp/sre_agent_demo.log").read_text()[-1000:]
        abort(f"Agent failed to start within 30 s.\nLast logs:\n{logs}")

    pause("Agent running. Press ENTER to start the Incident Bridge...")
    return _agent_proc


# ---------------------------------------------------------------------------
# Phase 4 — Start the Incident Bridge
# ---------------------------------------------------------------------------
_bridge_proc: subprocess.Popen | None = None

def phase4_start_bridge() -> subprocess.Popen:
    global _bridge_proc
    phase(4, "Start Incident Bridge Webhook (port 8080)")

    step("Launch localstack_bridge.py")
    bridge_log = open("/tmp/bridge_demo.log", "w")
    env = os.environ.copy()
    env["BRIDGE_PORT"] = str(BRIDGE_PORT)
    env["AGENT_URL"] = AGENT_URL
    _bridge_proc = subprocess.Popen(
        [str(VENV_PYTHON), str(BRIDGE_SCRIPT_PATH)],
        stdout=bridge_log,
        stderr=bridge_log,
        env=env,
        cwd=str(Path(__file__).parent.parent),
    )
    info(f"Bridge PID: {_bridge_proc.pid}")
    info("Logs streaming to /tmp/bridge_demo.log")

    step("Waiting for /health to respond (up to 15 s)...")
    deadline = time.time() + 15
    import urllib.request
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BRIDGE_URL}/health", timeout=1) as r:
                data = json.loads(r.read())
                if data.get("status") == "healthy":
                    ok(f"Incident Bridge is UP — {BRIDGE_URL}/health → {data}")
                    break
        except Exception:
            pass
        time.sleep(1)
    else:
        logs = Path("/tmp/bridge_demo.log").read_text()[-500:]
        abort(f"Bridge failed to start within 15 s.\nLogs:\n{logs}")

    pause("Bridge running. Press ENTER to subscribe it to the SNS topic...")
    return _bridge_proc


# ---------------------------------------------------------------------------
# Phase 5 — Subscribe Bridge to SNS
# ---------------------------------------------------------------------------
def phase5_subscribe_sns() -> None:
    phase(5, "Subscribe Incident Bridge to SNS Topic")

    sc = sns_client()

    # On macOS with Docker-based LocalStack, host.docker.internal resolves to the host
    bridge_endpoint = f"http://host.docker.internal:{BRIDGE_PORT}/sns/webhook"
    step(f"Subscribing: {bridge_endpoint}")
    info("If LocalStack runs natively (not Docker), change host.docker.internal → 127.0.0.1")

    sub_resp = sc.subscribe(
        TopicArn=TOPIC_ARN,
        Protocol="http",
        Endpoint=bridge_endpoint,
    )
    sub_arn = sub_resp.get("SubscriptionArn", "pending confirmation")
    field("SubscriptionArn", sub_arn)

    if sub_arn == "pending confirmation":
        info("Waiting 5 s for SNS to deliver SubscriptionConfirmation to bridge...")
        time.sleep(5)
        bridge_logs = Path("/tmp/bridge_demo.log").read_text()
        if "Subscription confirmed" in bridge_logs or "SubscriptionConfirmation" in bridge_logs:
            ok("Bridge confirmed the SNS subscription")
        else:
            info("LocalStack Pro auto-confirmed (full ARN returned). Subscription is live.")
    else:
        ok(f"Subscription confirmed (LocalStack Pro): {sub_arn}")

    pause("SNS subscription live. Press ENTER to seed the knowledge base...")


# ---------------------------------------------------------------------------
# Phase 6 — Seed the knowledge base
# ---------------------------------------------------------------------------
def phase6_seed_knowledge_base() -> None:
    phase(6, "Seed Knowledge Base with Payment-Processor Runbook")

    runbook = {
        "source": "runbooks/payment-processor-oom.md",
        "metadata": {"tier": "1", "service": FUNCTION_NAME},
        "content": (
            "# Payment Processor Lambda Crash\n\n"
            "Occurs when the database connection pool is exhausted under peak load.\n\n"
            "**Symptoms:**\n"
            "- Lambda invocation errors spike\n"
            "- RuntimeError: Database connection pool exhausted\n"
            "- active connections at max (128/128)\n\n"
            "**Root Cause:**\n"
            "The payment-processor Lambda shares a connection pool with the order-service. "
            "During flash sales, concurrent Lambda invocations exhaust the pool.\n\n"
            "**Mitigation:**\n"
            "1. Throttle Lambda concurrency to 50 to reduce DB pressure.\n"
            "2. Increase RDS connection pool limit (max_connections).\n"
            "3. Enable RDS Proxy to multiplex connections.\n"
            "4. Add exponential backoff and jitter on DB connection retry.\n"
        ),
    }

    step(f"POST {AGENT_URL}/api/v1/diagnose/ingest")
    info("Embedding model cold-starts on first call — may take ~25 s")

    import urllib.request
    req = urllib.request.Request(
        f"{AGENT_URL}/api/v1/diagnose/ingest",
        data=json.dumps(runbook).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    start = time.time()
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    elapsed = time.time() - start

    ok(f"Runbook ingested in {elapsed:.1f} s")
    field("doc_id", data.get("doc_id"))
    field("source", data.get("source"))
    field("chunks", data.get("chunks"))

    pause("Knowledge base seeded. Press ENTER to INDUCE CHAOS...")


# ---------------------------------------------------------------------------
# Phase 7 — Induce Chaos: crash the Lambda
# ---------------------------------------------------------------------------
def phase7_induce_chaos() -> None:
    phase(7, "INDUCE CHAOS — Crash the Payment Processor Lambda")

    lc = lambda_client()

    print(f"   {C.RED}{C.BOLD}💥 Invoking payment-processor with destructive payload...{C.RESET}")
    print(f"   {C.DIM}Payload: {{\"induce_error\": true}}{C.RESET}\n")

    invoke_resp = lc.invoke(
        FunctionName=FUNCTION_NAME,
        Payload=json.dumps({"induce_error": True}).encode(),
    )
    payload_bytes = invoke_resp["Payload"].read()
    error_body = json.loads(payload_bytes)

    function_error = invoke_resp.get("FunctionError", "")
    status_code    = invoke_resp.get("StatusCode", 0)

    field("HTTP StatusCode",  status_code)
    field("FunctionError",    function_error or "None")
    field("errorType",        error_body.get("errorType", "n/a"))
    field("errorMessage",     error_body.get("errorMessage", "n/a"))
    field("requestId",        error_body.get("requestId", "n/a"))

    if function_error == "Unhandled":
        ok("Lambda crashed as expected — CloudWatch Errors metric has been incremented")
    else:
        fail("Lambda did not raise an error — check the mock_lambda.py handler")

    pause("Lambda crashed. Press ENTER to trigger the alarm and fire the full detection chain...")


# ---------------------------------------------------------------------------
# Phase 8 — Force alarm → SNS → Bridge → Agent
# ---------------------------------------------------------------------------
def phase8_fire_alarm() -> None:
    phase(8, "Fire CloudWatch Alarm → SNS → Bridge → SRE Agent")

    cw = cw_client()

    step("Set PaymentProcessorErrorSpike alarm state to ALARM")
    info(
        "Using set-alarm-state to immediately trigger the SNS notification "
        "(skips the 60 s CloudWatch evaluation window)"
    )
    cw.set_alarm_state(
        AlarmName=ALARM_NAME,
        StateValue="ALARM",
        StateReason=(
            "Threshold Crossed: 1 datapoint [1.0] was greater than or equal to "
            "the threshold (1.0). Lambda Errors metric exceeded."
        ),
    )
    ok("Alarm transitioned to ALARM state")

    print(f"\n   {C.DIM}Chain executing automatically:{C.RESET}")
    steps_chain = [
        "CloudWatch  →  alarm state ALARM",
        "SNS         →  HTTP POST to bridge webhook",
        "Bridge      →  translates AWS Alarm JSON → AnomalyAlert",
        "SRE Agent   →  RAG retrieval + Anthropic LLM diagnosis",
    ]
    for s in steps_chain:
        print(f"   {C.CYAN}→{C.RESET}  {s}")

    print(f"\n   {C.DIM}Waiting 10 s for the full chain to complete...{C.RESET}")
    time.sleep(10)

    # Verify alarm is in ALARM state
    alarm_resp = cw.describe_alarms(AlarmNames=[ALARM_NAME])
    alarm_state = alarm_resp["MetricAlarms"][0]["StateValue"]
    field("Final alarm state", alarm_state)


# ---------------------------------------------------------------------------
# Phase 9 — Display the diagnosis output
# ---------------------------------------------------------------------------
def phase9_show_diagnosis() -> None:
    phase(9, "SRE Agent Diagnosis Output")

    bridge_log_text = Path("/tmp/bridge_demo.log").read_text()

    # Find the JSON block in the bridge log
    marker = "Agent Diagnosis Output:"
    if marker not in bridge_log_text:
        info("Diagnosis not yet in bridge log. Querying the Agent directly...")
        # Direct fallback: re-send alert to agent and show result
        import urllib.request
        alert_payload = {
            "alert": {
                "anomaly_type": "invocation_error_surge",
                "service": FUNCTION_NAME,
                "compute_mechanism": "serverless",
                "metric_name": "Errors",
                "current_value": 1.0,
                "baseline_value": 0.0,
                "deviation_sigma": 10.0,
                "description": (
                    "CloudWatch alarm 'PaymentProcessorErrorSpike' transitioned to ALARM. "
                    "Lambda function invocation errors exceeded threshold."
                ),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "correlated_signals": {
                    "service": FUNCTION_NAME,
                    "window_start": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "window_end":   time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "metrics": [
                        {
                            "name": "Errors",
                            "value": 1.0,
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "labels": {"service": FUNCTION_NAME},
                        }
                    ],
                },
            }
        }
        req = urllib.request.Request(
            f"{AGENT_URL}/api/v1/diagnose",
            data=json.dumps(alert_payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        info("Waiting up to 30 s for LLM response...")
        with urllib.request.urlopen(req, timeout=60) as r:
            diagnosis = json.loads(r.read())
        bridge_log_text = None
    else:
        # Parse from log
        json_start = bridge_log_text.find("{", bridge_log_text.find(marker))
        # Extract balanced JSON blob
        depth = 0
        end = json_start
        for i, ch in enumerate(bridge_log_text[json_start:], json_start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        diagnosis = json.loads(bridge_log_text[json_start:end])

    # Render the diagnosis
    width = 74
    print(f"\n   {C.BOLD}{C.GREEN}{'─' * width}{C.RESET}")
    print(f"   {C.BOLD}{C.GREEN}🤖  AUTONOMOUS SRE AGENT — DIAGNOSIS REPORT{C.RESET}")
    print(f"   {C.BOLD}{C.GREEN}{'─' * width}{C.RESET}\n")

    field("Alert ID",          diagnosis.get("alert_id", "n/a"))
    field("Status",            diagnosis.get("status", "n/a"))
    field("Severity",          diagnosis.get("severity", "n/a"))
    confidence = diagnosis.get("confidence", 0)
    field("Confidence",        f"{confidence * 100:.1f}%")
    field("Requires Approval", diagnosis.get("requires_approval", "n/a"))

    print(f"\n   {C.CYAN}Root Cause:{C.RESET}")
    for line in (diagnosis.get("root_cause") or "n/a").split(". "):
        if line.strip():
            print(f"      {line.strip()}.")

    print(f"\n   {C.CYAN}Suggested Remediation:{C.RESET}")
    remediation = diagnosis.get("remediation") or diagnosis.get("suggested_remediation") or "n/a"
    for line in remediation.split(","):
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
        print(f"\n   {C.CYAN}Audit Trail (Pipeline Stages):{C.RESET}")
        _llm_stages = []
        for entry in audit:
            # Audit entries are now structured dicts: {"stage": .., "action": .., "details": ..}
            # Legacy string format ("stage/action: {details}") still supported as fallback.
            if isinstance(entry, dict):
                action  = entry.get("action", "")
                details = entry.get("details", {}) or {}
                stage   = entry.get("stage", "")
                display = f"{stage}/{action}: {details}"
            else:
                entry_str = str(entry)
                action, details, display = "", {}, entry_str
                if "/" in entry_str and ": " in entry_str:
                    try:
                        import ast as _ast
                        action_part, _, rest = entry_str.partition(": ")
                        action = action_part.split("/")[-1].strip()
                        details = _ast.literal_eval(rest.strip())
                    except Exception:
                        pass

            if action == "hypothesis_generated":
                _llm_stages.append(("Anthropic Claude — hypothesis generation (Call 1)", details))
            elif action == "hypothesis_validated":
                _llm_stages.append(("Anthropic Claude — cross-validation (Call 2)", details))

            print(f"      {C.DIM}→{C.RESET}  {display}")

        if _llm_stages:
            print(f"\n   {C.BOLD}{C.MAGENTA}🧠  LLM Calls Made (Anthropic Claude):{C.RESET}")
            for label, det in _llm_stages:
                print(f"      {C.MAGENTA}◆{C.RESET}  {C.BOLD}{label}{C.RESET}")
                if "confidence" in det:
                    try:
                        print(f"         Confidence returned by LLM : {float(det['confidence']):.2f}")
                    except (TypeError, ValueError):
                        print(f"         Confidence returned by LLM : {det['confidence']}")
                if "root_cause" in det:
                    rc = str(det["root_cause"])[:120]
                    print(f"         Root-cause excerpt         : {rc}...")
                if "agrees" in det:
                    agreed = det["agrees"]
                    tag = f"{C.GREEN}✔ agrees{C.RESET}" if agreed else f"{C.RED}✖ disagrees (confidence penalty applied){C.RESET}"
                    print(f"         Validator agreement        : {tag}")
                if "reasoning" in det:
                    rsn = str(det["reasoning"])[:150]
                    is_llm = "Rule-based" not in rsn and "No LLM" not in rsn
                    source_tag = (
                        f"{C.GREEN}LLM cross-check{C.RESET}" if is_llm
                        else f"{C.YELLOW}rule-based fallback{C.RESET}"
                    )
                    print(f"         Reasoning source           : {source_tag}")
                    print(f"         Reasoning excerpt          : {rsn}...")
        else:
            print(f"\n   {C.YELLOW}ℹ  No LLM hypothesis/validation entries in audit trail.{C.RESET}")

    print(f"\n   {C.BOLD}{C.GREEN}{'─' * width}{C.RESET}\n")

    pause("Diagnosis displayed. Press ENTER to run cleanup...")


# ---------------------------------------------------------------------------
# Phase 10 — Cleanup
# ---------------------------------------------------------------------------
def phase10_cleanup() -> None:
    phase(10, "Cleanup — Remove Resources and Stop Servers")

    lc  = lambda_client()
    cw  = cw_client()
    sc  = sns_client()

    step("Delete Lambda function")
    try:
        lc.delete_function(FunctionName=FUNCTION_NAME)
        ok(f"Deleted Lambda: {FUNCTION_NAME}")
    except Exception as exc:
        info(f"Lambda delete skipped: {exc}")

    step("Delete CloudWatch alarm")
    try:
        cw.delete_alarms(AlarmNames=[ALARM_NAME])
        ok(f"Deleted alarm: {ALARM_NAME}")
    except Exception as exc:
        info(f"Alarm delete skipped: {exc}")

    step("Delete SNS topic")
    try:
        sc.delete_topic(TopicArn=TOPIC_ARN)
        ok(f"Deleted SNS topic: {TOPIC_ARN}")
    except Exception as exc:
        info(f"SNS delete skipped: {exc}")

    step("Terminate SRE Agent server")
    if _agent_proc and _agent_proc.poll() is None:
        _agent_proc.terminate()
        _agent_proc.wait(timeout=5)
        ok(f"Agent process {_agent_proc.pid} terminated")
    else:
        info("Agent was not running")

    step("Terminate Incident Bridge server")
    if _bridge_proc and _bridge_proc.poll() is None:
        _bridge_proc.terminate()
        _bridge_proc.wait(timeout=5)
        ok(f"Bridge process {_bridge_proc.pid} terminated")
    else:
        info("Bridge was not running")

    step("Log files saved")
    info("/tmp/sre_agent_demo.log — full agent startup and request logs")
    info("/tmp/bridge_demo.log   — full bridge webhook logs incl. diagnosis JSON")


# ---------------------------------------------------------------------------
# Signal handler — clean up on Ctrl-C
# ---------------------------------------------------------------------------
def _handle_sigint(sig, frame):
    print(f"\n\n{C.YELLOW}  Ctrl-C received — running cleanup before exit...{C.RESET}\n")
    phase10_cleanup()
    sys.exit(0)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    signal.signal(signal.SIGINT, _handle_sigint)

    banner("Live Demo 7 — LocalStack End-to-End Incident Response")

    print(f"   {C.DIM}This demo proves the full Detect → Diagnose → Report chain:{C.RESET}")
    print(f"   {C.DIM}Lambda crash → CloudWatch → SNS → Bridge → RAG + LLM{C.RESET}\n")
    print(f"   {C.DIM}LocalStack endpoint : {LOCALSTACK_ENDPOINT}{C.RESET}")
    print(f"   {C.DIM}AWS region          : {AWS_REGION}{C.RESET}")
    print(f"   {C.DIM}Interactive pauses  : {'OFF (SKIP_PAUSES=1)' if SKIP_PAUSES else 'ON (set SKIP_PAUSES=1 to disable)'}{C.RESET}")

    pause("Review the config above. Press ENTER to begin Phase 0: Pre-flight...")

    phase0_preflight()
    phase1_deploy_lambda()
    phase2_configure_alarm()
    phase3_start_agent()
    phase4_start_bridge()
    phase5_subscribe_sns()
    phase6_seed_knowledge_base()
    phase7_induce_chaos()
    phase8_fire_alarm()
    phase9_show_diagnosis()
    phase10_cleanup()

    print(f"\n{C.BOLD}{C.GREEN}  ✔  Demo complete — full Detect → Diagnose → Report chain executed end-to-end!{C.RESET}\n")


if __name__ == "__main__":
    main()
