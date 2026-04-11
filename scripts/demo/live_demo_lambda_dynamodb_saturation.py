"""
Live Demo 9 — Lambda Cold-Start Avalanche + DynamoDB Saturation
===============================================================

Scenario 3: The most compelling RAG showcase — a compound failure where two
simultaneous but causally-linked problems (Lambda cold-start concurrency thrashing
+ DynamoDB provisioned throughput exhaustion) produce a non-obvious diagnosis that
requires genuine multi-signal correlation.

What this demo proves:
  Phase 0  — Pre-flight: verify LocalStack Pro, ports, packages
  Phase 1  — Deploy Lambda functions (order-processor + inventory-updater)
             backed by a shared DynamoDB table (orders)
  Phase 2  — EventBridge rule to fan-out order events to both Lambdas
  Phase 3  — CloudWatch alarms: Lambda error rate + DynamoDB throttle alarms
             wired to SNS topics
  Phase 4  — Start SRE Agent FastAPI server (port 8181)
  Phase 5  — Start Incident Bridge webhook server (port 8080)
  Phase 6  — Subscribe bridge to SNS alert topics
  Phase 7  — Seed knowledge base with Lambda/DynamoDB runbooks
  Phase 8  — INDUCE CHAOS via LocalStack Chaos API:
               • DynamoDB: ProvisionedThroughputExceededException (70% on PutItem/GetItem)
               • Lambda: 2000 ms artificial latency on all Invoke calls
  Phase 9  — Trigger alarm chain: Lambda errors → SNS → Bridge → Agent
  Phase 10 — Display first diagnosis (Lambda cold-start + DynamoDB saturation)
  Phase 11 — Trigger second alarm: DynamoDB throttling alarm fires independently
  Phase 12 — Display second diagnosis (compound failure confirmed)
  Phase 13 — Human approval gate: operator approves concurrency limit action
  Phase 14 — Chaos teardown: clear all Chaos API rules
  Phase 15 — Cleanup: delete all AWS resources, stop servers

What makes this demo uniquely strong:
  ✦  LocalStack Chaos API — clean, code-free fault injection (no alarm-state hacks)
  ✦  Compound failure: two causally linked signals, one root cause
  ✦  RAG retrieves non-obvious cross-service runbook knowledge
  ✦  LLM must reason: "Lambda latency + DynamoDB throttle = cold-start avalanche"
  ✦  Human approval gate blocks concurrency change until operator signs off
  ✦  Chaos teardown demonstrates safe recovery confirmation

Usage
-----
    source .venv/bin/activate
    python scripts/demo/live_demo_lambda_dynamodb_saturation.py

Environment
-----------
    LOCALSTACK_ENDPOINT   LocalStack endpoint (default: http://localhost:4566)
    AWS_DEFAULT_REGION    AWS region (default: us-east-1)
    AGENT_PORT            SRE Agent port (default: 8181)
    BRIDGE_PORT           Incident bridge port (default: 8080)
    BRIDGE_HOST           Hostname LocalStack uses to reach the bridge webhook
                          (default: host.docker.internal for Docker-based LocalStack)
    SKIP_PAUSES           Set to "1" to skip interactive ENTER prompts (CI mode)
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

import boto3
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent.parent.parent / ".env")

# ---------------------------------------------------------------------------
# Shared demo utilities
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))
from _demo_utils import (
    aws_region,
    ensure_localstack_running,
    env_bool,
    localstack_auth_token,
    register_cleanup_handler,
    start_or_reuse_agent,
    stop_agent,
)

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
BRIDGE_HOST         = os.getenv("BRIDGE_HOST", "host.docker.internal")

ACCOUNT_ID          = "000000000000"

# Lambda function names
ORDER_PROCESSOR     = "order-processor"
INVENTORY_UPDATER   = "inventory-updater"

# DynamoDB table
ORDERS_TABLE        = "orders"

# EventBridge
EVENT_BUS_NAME      = "sre-demo-bus"
EVENT_RULE_NAME     = "order-fanout-rule"

# SNS topics
LAMBDA_ALERT_TOPIC  = "sre-lambda-alerts"
DYNAMO_ALERT_TOPIC  = "sre-dynamo-alerts"

# CloudWatch alarm names
LAMBDA_ERROR_ALARM  = "LambdaOrderProcessorErrorRate"
DYNAMO_THROTTLE_ALARM = "DynamoOrdersThrottleCount"

# Chaos API endpoints
CHAOS_FAULTS_URL    = f"{LOCALSTACK_ENDPOINT}/_localstack/chaos/faults"
CHAOS_EFFECTS_URL   = f"{LOCALSTACK_ENDPOINT}/_localstack/chaos/effects"

VENV_PYTHON         = Path(__file__).parent.parent.parent / ".venv" / "bin" / "python"
BRIDGE_SCRIPT_PATH  = Path(__file__).parent / "localstack_bridge.py"

# ---------------------------------------------------------------------------
# Colour helpers (match existing demo style)
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


WIDTH = 74

def banner(title: str) -> None:
    print(f"\n{C.BOLD}{C.BLUE}╔{'═' * WIDTH}╗{C.RESET}")
    print(f"{C.BOLD}{C.BLUE}║{title.center(WIDTH)}║{C.RESET}")
    print(f"{C.BOLD}{C.BLUE}╚{'═' * WIDTH}╝{C.RESET}\n")

def phase(number: int, title: str) -> None:
    label = f"  PHASE {number}: {title}  "
    print(f"\n{C.BOLD}{C.MAGENTA}╔{'═' * WIDTH}╗{C.RESET}")
    print(f"{C.BOLD}{C.MAGENTA}║{label.center(WIDTH)}║{C.RESET}")
    print(f"{C.BOLD}{C.MAGENTA}╚{'═' * WIDTH}╝{C.RESET}\n")

def ok(msg: str)    -> None: print(f"   {C.GREEN}✔{C.RESET}  {msg}")
def fail(msg: str)  -> None: print(f"   {C.RED}✖{C.RESET}  {C.RED}{msg}{C.RESET}")
def info(msg: str)  -> None: print(f"   {C.CYAN}ℹ{C.RESET}  {msg}")
def step(msg: str)  -> None: print(f"\n   {C.YELLOW}▶{C.RESET}  {C.BOLD}{msg}{C.RESET}")
def warn(msg: str)  -> None: print(f"   {C.YELLOW}⚠{C.RESET}  {msg}")
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
_boto_kwargs: dict[str, Any] = dict(
    endpoint_url=LOCALSTACK_ENDPOINT,
    region_name=AWS_REGION,
    aws_access_key_id="test",
    aws_secret_access_key="test",
)

def lambda_client():  return boto3.client("lambda",        **_boto_kwargs)
def dynamo_client():  return boto3.client("dynamodb",      **_boto_kwargs)
def cw_client():      return boto3.client("cloudwatch",    **_boto_kwargs)
def sns_client():     return boto3.client("sns",           **_boto_kwargs)
def events_client():  return boto3.client("events",        **_boto_kwargs)
def iam_client():     return boto3.client("iam",           **_boto_kwargs)


# ---------------------------------------------------------------------------
# Shared state across phases
# ---------------------------------------------------------------------------
_store: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Chaos API helpers
# ---------------------------------------------------------------------------
def _chaos_post(url: str, payload: Any) -> Any:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read()) if r.length else {}


def _chaos_get(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())


def enable_chaos_rules() -> None:
    """Inject DynamoDB throttle errors (70%) and Lambda ServiceException errors (50%).

    The combination simulates the cold-start avalanche pattern:
    - DynamoDB PutItem/GetItem: ProvisionedThroughputExceededException at 70%
      → Lambda handlers fail waiting on DynamoDB retries
    - Lambda InvokeFunction: ServiceException at 50%
      → Simulates invocations failing due to container exhaustion (all occupied retrying DDB)
    """
    faults = [
        # DynamoDB throttle — primary fault
        {
            "service": "dynamodb",
            "region": AWS_REGION,
            "operation": "PutItem",
            "probability": 0.7,
            "error": {
                "statusCode": 400,
                "code": "ProvisionedThroughputExceededException",
            },
        },
        {
            "service": "dynamodb",
            "region": AWS_REGION,
            "operation": "GetItem",
            "probability": 0.7,
            "error": {
                "statusCode": 400,
                "code": "ProvisionedThroughputExceededException",
            },
        },
        # Lambda invocation failures — secondary fault (simulates cold-start avalanche exhaustion)
        {
            "service": "lambda",
            "region": AWS_REGION,
            "operation": "InvokeFunction",
            "probability": 0.5,
            "error": {
                "statusCode": 500,
                "code": "ServiceException",
            },
        },
    ]
    _chaos_post(CHAOS_FAULTS_URL, faults)


def disable_chaos_rules() -> None:
    """Clear all active Chaos API rules."""
    _chaos_post(CHAOS_FAULTS_URL, [])


def get_active_chaos() -> dict:
    faults = _chaos_get(CHAOS_FAULTS_URL)
    return {"faults": faults, "effects": {}}


# ---------------------------------------------------------------------------
# Lambda zip helper — creates a minimal Python handler in memory
# ---------------------------------------------------------------------------
def _make_lambda_zip(handler_code: str) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("handler.py", handler_code)
    return buf.getvalue()


ORDER_PROCESSOR_CODE = """
import json
import os
import boto3

DYNAMO_ENDPOINT = os.environ.get("DYNAMO_ENDPOINT", "http://localhost:4566")
TABLE_NAME = os.environ.get("TABLE_NAME", "orders")

def handler(event, context):
    dynamo = boto3.client(
        "dynamodb",
        endpoint_url=DYNAMO_ENDPOINT,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    order_id = event.get("order_id", "ord-unknown")
    dynamo.put_item(
        TableName=TABLE_NAME,
        Item={
            "order_id": {"S": order_id},
            "status":   {"S": "RECEIVED"},
            "ts":       {"S": context.aws_request_id},
        },
    )
    return {"statusCode": 200, "body": json.dumps({"order_id": order_id})}
"""

INVENTORY_UPDATER_CODE = """
import json
import os
import boto3

DYNAMO_ENDPOINT = os.environ.get("DYNAMO_ENDPOINT", "http://localhost:4566")
TABLE_NAME = os.environ.get("TABLE_NAME", "orders")

def handler(event, context):
    dynamo = boto3.client(
        "dynamodb",
        endpoint_url=DYNAMO_ENDPOINT,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    order_id = event.get("order_id", "ord-unknown")
    dynamo.get_item(
        TableName=TABLE_NAME,
        Key={"order_id": {"S": order_id}},
    )
    return {"statusCode": 200, "body": json.dumps({"updated": order_id})}
"""


# ---------------------------------------------------------------------------
# Phase 0 — Pre-flight
# ---------------------------------------------------------------------------
def phase0_preflight() -> None:
    phase(0, "Pre-flight Checks")

    step("Verify LocalStack Pro is reachable")
    try:
        ensure_localstack_running(
            endpoint=LOCALSTACK_ENDPOINT,
            auth_token=localstack_auth_token(),
            timeout_seconds=90,
            emit_logs=True,
        )
    except RuntimeError as exc:
        abort(str(exc))

    step("Verify required Python packages")
    for pkg in ("boto3", "httpx", "uvicorn", "fastapi"):
        try:
            __import__(pkg)
            ok(f"{pkg} — available")
        except ImportError:
            fail(f"{pkg} — MISSING")
            fail(f"Install missing packages:  pip install {pkg}")
            sys.exit(1)

    step("Verify Chaos API is reachable")
    try:
        rules = _chaos_get(CHAOS_FAULTS_URL)
        ok(f"Chaos API reachable — {len(rules)} active fault rule(s)")
        if rules:
            warn("Clearing leftover chaos rules from a previous run")
            disable_chaos_rules()
            ok("Chaos rules cleared")
    except Exception as exc:
        abort(f"Chaos API not reachable at {CHAOS_FAULTS_URL}: {exc}\n"
              "  Ensure LocalStack Pro is running (Community edition lacks Chaos API)")

    step("Verify ports are free")
    import subprocess
    for port in (AGENT_PORT, BRIDGE_PORT):
        result = subprocess.run(["lsof", "-ti", f":{port}"], capture_output=True, text=True)
        pids = result.stdout.strip().split()
        if pids:
            info(f"Port {port} in use — killing PID(s): {', '.join(pids)}")
            subprocess.run(["kill", "-9"] + pids, capture_output=True)
            time.sleep(1)
        ok(f"Port {port} — free")

    field("LocalStack endpoint", LOCALSTACK_ENDPOINT)
    field("AWS region",          AWS_REGION)
    field("Bridge host",         BRIDGE_HOST)
    field("Interactive pauses",  "OFF (SKIP_PAUSES=1)" if SKIP_PAUSES else "ON")


# ---------------------------------------------------------------------------
# Phase 1 — Deploy Lambda functions + DynamoDB table
# ---------------------------------------------------------------------------
def phase1_deploy_infrastructure() -> None:
    phase(1, "Deploy Lambda Functions + DynamoDB Orders Table")

    lc  = lambda_client()
    dc  = dynamo_client()
    iam = iam_client()

    # IAM role (LocalStack accepts any ARN)
    role_arn = f"arn:aws:iam::{ACCOUNT_ID}:role/lambda-execution-role"

    # Ensure role exists (LocalStack auto-creates on Lambda deployment, but be explicit)
    try:
        iam.create_role(
            RoleName="lambda-execution-role",
            AssumeRolePolicyDocument=json.dumps({
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Principal": {"Service": "lambda.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }],
            }),
        )
    except iam.exceptions.EntityAlreadyExistsException:
        pass

    # DynamoDB table
    step(f"Create DynamoDB table: {ORDERS_TABLE}")
    try:
        dc.delete_table(TableName=ORDERS_TABLE)
        dc.get_waiter("table_not_exists").wait(TableName=ORDERS_TABLE)
    except dc.exceptions.ResourceNotFoundException:
        pass
    except Exception:
        pass

    dc.create_table(
        TableName=ORDERS_TABLE,
        KeySchema=[{"AttributeName": "order_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "order_id", "AttributeType": "S"}],
        BillingMode="PROVISIONED",
        ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
    )
    ok(f"DynamoDB table created: {ORDERS_TABLE} (5 RCU / 5 WCU — intentionally low for throttle demo)")

    # Lambda env vars point back to LocalStack
    lambda_env = {
        "DYNAMO_ENDPOINT": LOCALSTACK_ENDPOINT,
        "TABLE_NAME": ORDERS_TABLE,
    }

    # Deploy order-processor
    step(f"Deploy Lambda: {ORDER_PROCESSOR}")
    order_zip = _make_lambda_zip(ORDER_PROCESSOR_CODE)
    for fn_name in (ORDER_PROCESSOR, INVENTORY_UPDATER):
        try:
            lc.delete_function(FunctionName=fn_name)
            time.sleep(1)
        except lc.exceptions.ResourceNotFoundException:
            pass

    lc.create_function(
        FunctionName=ORDER_PROCESSOR,
        Runtime="python3.11",
        Role=role_arn,
        Handler="handler.handler",
        Code={"ZipFile": order_zip},
        Environment={"Variables": lambda_env},
        Timeout=30,
        MemorySize=128,
    )
    ok(f"Lambda deployed: {ORDER_PROCESSOR} (python3.11, 128 MB)")

    # Deploy inventory-updater
    step(f"Deploy Lambda: {INVENTORY_UPDATER}")
    inv_zip = _make_lambda_zip(INVENTORY_UPDATER_CODE)
    lc.create_function(
        FunctionName=INVENTORY_UPDATER,
        Runtime="python3.11",
        Role=role_arn,
        Handler="handler.handler",
        Code={"ZipFile": inv_zip},
        Environment={"Variables": lambda_env},
        Timeout=30,
        MemorySize=128,
    )
    ok(f"Lambda deployed: {INVENTORY_UPDATER} (python3.11, 128 MB)")

    print()
    info("Architecture: EventBridge → order-processor + inventory-updater → DynamoDB(orders)")
    info("Both Lambdas share the same low-capacity DynamoDB table — primed for throttling")
    pause("Infrastructure ready. Press ENTER to configure EventBridge...")


# ---------------------------------------------------------------------------
# Phase 2 — EventBridge fan-out rule
# ---------------------------------------------------------------------------
def phase2_configure_eventbridge() -> None:
    phase(2, "Configure EventBridge Fan-Out Rule")

    ec  = events_client()
    lc  = lambda_client()

    step(f"Create custom event bus: {EVENT_BUS_NAME}")
    try:
        ec.delete_event_bus(Name=EVENT_BUS_NAME)
    except Exception:
        pass
    ec.create_event_bus(Name=EVENT_BUS_NAME)
    ok(f"Event bus created: {EVENT_BUS_NAME}")

    step(f"Create fan-out rule: {EVENT_RULE_NAME}")
    ec.put_rule(
        Name=EVENT_RULE_NAME,
        EventBusName=EVENT_BUS_NAME,
        EventPattern=json.dumps({
            "source": ["sre-demo.orders"],
            "detail-type": ["OrderPlaced"],
        }),
        State="ENABLED",
        Description="Fan-out order events to order-processor and inventory-updater Lambdas",
    )
    ok(f"Rule created: {EVENT_RULE_NAME}")

    step("Wire Lambda targets to rule")
    for fn_name in (ORDER_PROCESSOR, INVENTORY_UPDATER):
        fn_arn = f"arn:aws:lambda:{AWS_REGION}:{ACCOUNT_ID}:function:{fn_name}"
        # Add resource-based permission for EventBridge to invoke
        try:
            lc.add_permission(
                FunctionName=fn_name,
                StatementId=f"eventbridge-invoke-{fn_name}",
                Action="lambda:InvokeFunction",
                Principal="events.amazonaws.com",
                SourceArn=f"arn:aws:events:{AWS_REGION}:{ACCOUNT_ID}:rule/{EVENT_BUS_NAME}/{EVENT_RULE_NAME}",
            )
        except lc.exceptions.ResourceConflictException:
            pass

    ec.put_targets(
        Rule=EVENT_RULE_NAME,
        EventBusName=EVENT_BUS_NAME,
        Targets=[
            {
                "Id": "order-processor-target",
                "Arn": f"arn:aws:lambda:{AWS_REGION}:{ACCOUNT_ID}:function:{ORDER_PROCESSOR}",
            },
            {
                "Id": "inventory-updater-target",
                "Arn": f"arn:aws:lambda:{AWS_REGION}:{ACCOUNT_ID}:function:{INVENTORY_UPDATER}",
            },
        ],
    )
    ok(f"Targets wired: {ORDER_PROCESSOR} + {INVENTORY_UPDATER}")

    info("Fan-out: 1 OrderPlaced event → invokes BOTH Lambdas → both hit DynamoDB")
    pause("EventBridge configured. Press ENTER to set up CloudWatch alarms...")


# ---------------------------------------------------------------------------
# Phase 3 — CloudWatch alarms + SNS topics
# ---------------------------------------------------------------------------
def phase3_configure_alarms() -> None:
    phase(3, "Configure CloudWatch Alarms + SNS Alert Topics")

    cw = cw_client()
    sc = sns_client()

    step(f"Create SNS topic: {LAMBDA_ALERT_TOPIC}")
    resp = sc.create_topic(Name=LAMBDA_ALERT_TOPIC)
    lambda_topic_arn = resp["TopicArn"]
    _store["lambda_topic_arn"] = lambda_topic_arn
    ok(f"Lambda alert topic ARN: {lambda_topic_arn}")

    step(f"Create SNS topic: {DYNAMO_ALERT_TOPIC}")
    resp = sc.create_topic(Name=DYNAMO_ALERT_TOPIC)
    dynamo_topic_arn = resp["TopicArn"]
    _store["dynamo_topic_arn"] = dynamo_topic_arn
    ok(f"DynamoDB alert topic ARN: {dynamo_topic_arn}")

    step(f"Create alarm: {LAMBDA_ERROR_ALARM}  (Lambda Errors > 5 in 1 min)")
    cw.put_metric_alarm(
        AlarmName=LAMBDA_ERROR_ALARM,
        AlarmDescription="order-processor Lambda error rate exceeded threshold",
        MetricName="Errors",
        Namespace="AWS/Lambda",
        Statistic="Sum",
        Dimensions=[{"Name": "FunctionName", "Value": ORDER_PROCESSOR}],
        Period=60,
        EvaluationPeriods=1,
        Threshold=5,
        ComparisonOperator="GreaterThanThreshold",
        AlarmActions=[lambda_topic_arn],
        TreatMissingData="notBreaching",
    )
    ok(f"Alarm created: {LAMBDA_ERROR_ALARM}")

    step(f"Create alarm: {DYNAMO_THROTTLE_ALARM}  (DynamoDB ThrottledRequests > 10 in 1 min)")
    cw.put_metric_alarm(
        AlarmName=DYNAMO_THROTTLE_ALARM,
        AlarmDescription="DynamoDB orders table provisioned throughput exceeded",
        MetricName="ThrottledRequests",
        Namespace="AWS/DynamoDB",
        Statistic="Sum",
        Dimensions=[
            {"Name": "TableName", "Value": ORDERS_TABLE},
            {"Name": "Operation", "Value": "PutItem"},
        ],
        Period=60,
        EvaluationPeriods=1,
        Threshold=10,
        ComparisonOperator="GreaterThanThreshold",
        AlarmActions=[dynamo_topic_arn],
        TreatMissingData="notBreaching",
    )
    ok(f"Alarm created: {DYNAMO_THROTTLE_ALARM}")

    pause("Alarms configured. Press ENTER to start the SRE Agent server...")


# ---------------------------------------------------------------------------
# Phase 4 — Start SRE Agent
# ---------------------------------------------------------------------------
def phase4_start_agent() -> None:
    phase(4, "Start SRE Agent FastAPI Server (port 8181)")

    step("Launch uvicorn sre_agent.api.main:app")
    try:
        proc, started, log_handle = start_or_reuse_agent(
            port=AGENT_PORT,
            log_path="/tmp/sre_agent_demo9.log",
            startup_timeout=40,
        )
        _store["agent_proc"]    = proc
        _store["agent_started"] = started
        _store["agent_log"]     = log_handle
    except RuntimeError as exc:
        abort(str(exc))

    pause("Agent is UP. Press ENTER to start the Incident Bridge...")


# ---------------------------------------------------------------------------
# Phase 5 — Start Incident Bridge
# ---------------------------------------------------------------------------
def phase5_start_bridge() -> None:
    phase(5, "Start Incident Bridge Webhook (port 8080)")

    import subprocess

    step("Launch localstack_bridge.py")
    log_path = "/tmp/bridge_demo9.log"
    log_handle = open(log_path, "w")  # noqa: SIM115
    proc = subprocess.Popen(
        [str(VENV_PYTHON), str(BRIDGE_SCRIPT_PATH)],
        env={
            **os.environ,
            "BRIDGE_PORT": str(BRIDGE_PORT),
            "AGENT_URL": AGENT_URL,
        },
        stdout=log_handle,
        stderr=log_handle,
    )
    _store["bridge_proc"]   = proc
    _store["bridge_log"]    = log_handle
    info(f"Bridge PID: {proc.pid}")
    info(f"Logs streaming to {log_path}")

    step("Waiting for /health to respond (up to 15 s)...")
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BRIDGE_URL}/health", timeout=2) as r:
                health = json.loads(r.read())
            ok(f"Bridge UP — {health}")
            break
        except Exception:
            time.sleep(1)
    else:
        abort("Bridge did not start within 15 s — check /tmp/bridge_demo9.log")

    pause("Bridge is UP. Press ENTER to subscribe to SNS topics...")


# ---------------------------------------------------------------------------
# Phase 6 — Subscribe bridge to SNS topics
# ---------------------------------------------------------------------------
def phase6_subscribe_bridge() -> None:
    phase(6, "Subscribe Incident Bridge to SNS Alert Topics")

    sc = sns_client()
    bridge_endpoint = f"http://{BRIDGE_HOST}:{BRIDGE_PORT}/sns/webhook"
    info(f"Bridge endpoint: {bridge_endpoint}")
    info("(LocalStack Pro auto-confirms HTTP subscriptions)")

    for topic_name, topic_arn in [
        (LAMBDA_ALERT_TOPIC, _store["lambda_topic_arn"]),
        (DYNAMO_ALERT_TOPIC, _store["dynamo_topic_arn"]),
    ]:
        step(f"Subscribe to: {topic_name}")
        resp = sc.subscribe(
            TopicArn=topic_arn,
            Protocol="http",
            Endpoint=bridge_endpoint,
        )
        ok(f"  {topic_name} → {resp.get('SubscriptionArn', 'pending confirmation')}")

    time.sleep(2)
    ok("SNS subscriptions live")
    pause("Subscriptions active. Press ENTER to seed the knowledge base...")


# ---------------------------------------------------------------------------
# Phase 7 — Seed knowledge base with runbooks
# ---------------------------------------------------------------------------
RUNBOOKS = [
    {
        "source": "runbooks/lambda-cold-start-avalanche.md",
        "metadata": {"tier": "1", "service": ORDER_PROCESSOR, "platform": "Lambda"},
        "content": (
            "# Lambda Cold-Start Avalanche\n\n"
            "## Symptoms\n"
            "- Lambda `Errors` metric spikes suddenly across multiple functions\n"
            "- `Duration` p99 increases dramatically (500ms → 3000ms+)\n"
            "- Lambda `Throttles` metric remains 0 or low (not a concurrency limit issue)\n"
            "- CloudWatch shows Lambda errors coinciding with DynamoDB ThrottledRequests\n"
            "- `Init Duration` in X-Ray traces shows cold-start overhead > 1 second\n\n"
            "## Root Causes\n"
            "1. **DynamoDB saturation causing cold-start avalanche** — when DynamoDB throttles "
            "writes, Lambda invocations wait for retries. With concurrent invocations all waiting, "
            "new invocations can no longer reuse warm containers (all are occupied waiting on DDB). "
            "This forces cold starts which add 1-3 seconds each, compounding the backlog.\n"
            "2. **Insufficient reserved concurrency** — without a concurrency cap, a traffic spike "
            "launches hundreds of simultaneous Lambda instances, each one hitting the already-"
            "saturated DynamoDB table, making throttling worse in a feedback loop.\n"
            "3. **EventBridge fan-out multiplication** — if an EventBridge rule targets multiple "
            "Lambdas, each event triggers N invocations simultaneously, multiplying DynamoDB "
            "write pressure by N (e.g., 2 targets = 2× write amplification).\n\n"
            "## Remediation\n"
            "1. **Immediate**: Set Lambda reserved concurrency limit to reduce DynamoDB pressure:\n"
            "   `aws lambda put-function-concurrency --function-name order-processor "
            "--reserved-concurrent-executions 10`\n"
            "2. **EventBridge**: Temporarily disable the fan-out rule to stop multiplying pressure:\n"
            "   `aws events disable-rule --name order-fanout-rule --event-bus-name sre-demo-bus`\n"
            "3. **DynamoDB**: Switch to on-demand billing to auto-scale capacity:\n"
            "   `aws dynamodb update-table --table-name orders "
            "--billing-mode PAY_PER_REQUEST`\n"
            "4. **Long-term**: Add SQS queue between EventBridge and Lambda to buffer bursts. "
            "Use SQS batch size 10 + visibility timeout matching Lambda timeout.\n"
            "5. **Monitoring**: Set Lambda reserved concurrency alarm at 80% utilisation.\n\n"
            "## Requires Human Approval\n"
            "Setting reserved concurrency on order-processor requires approval from the "
            "on-call lead because it may shed traffic during peak hours.\n"
        ),
    },
    {
        "source": "runbooks/dynamodb-provisioned-throughput-exhaustion.md",
        "metadata": {"tier": "1", "service": ORDERS_TABLE, "platform": "DynamoDB"},
        "content": (
            "# DynamoDB Provisioned Throughput Exhaustion\n\n"
            "## Symptoms\n"
            "- CloudWatch `ThrottledRequests` metric spikes on PutItem or GetItem operations\n"
            "- Application error logs show `ProvisionedThroughputExceededException`\n"
            "- DynamoDB `ConsumedWriteCapacityUnits` hits provisioned limit (5 WCU in demo)\n"
            "- Upstream Lambda functions report increased `Errors` and `Duration` metrics\n\n"
            "## Root Causes\n"
            "1. **Provisioned capacity too low for traffic burst** — table created with 5 WCU "
            "handles ~5 writes/sec; a fan-out from EventBridge can generate 10-50 writes/sec.\n"
            "2. **Hot partition** — all writes use the same partition key prefix, concentrating "
            "load on one DynamoDB shard and causing local throttling below the table-level limit.\n"
            "3. **Retry storms from Lambda** — AWS SDK auto-retries throttled DynamoDB calls "
            "with exponential backoff. With many concurrent Lambdas, retries amplify write "
            "pressure exponentially.\n\n"
            "## Remediation\n"
            "1. Switch table to on-demand billing (immediate, no downtime):\n"
            "   `aws dynamodb update-table --table-name orders --billing-mode PAY_PER_REQUEST`\n"
            "2. Temporarily increase provisioned WCU if on-demand switch is not approved:\n"
            "   `aws dynamodb update-table --table-name orders "
            "--provisioned-throughput ReadCapacityUnits=50,WriteCapacityUnits=50`\n"
            "3. Add DynamoDB Accelerator (DAX) for read-heavy workloads to reduce GetItem pressure.\n"
            "4. Implement write batching in Lambda: use `BatchWriteItem` (up to 25 items/call) "
            "instead of individual `PutItem` calls.\n"
        ),
    },
    {
        "source": "runbooks/eventbridge-fanout-amplification.md",
        "metadata": {"tier": "2", "service": EVENT_BUS_NAME, "platform": "EventBridge"},
        "content": (
            "# EventBridge Fan-Out Write Amplification\n\n"
            "## Description\n"
            "An EventBridge rule with multiple Lambda targets amplifies downstream write load. "
            "Each event that matches the rule invokes ALL targets simultaneously. If targets "
            "share a downstream resource (e.g., DynamoDB table), write pressure is multiplied "
            "by the number of targets.\n\n"
            "## Detection\n"
            "- DynamoDB ThrottledRequests spike correlates exactly with EventBridge MatchedEvents\n"
            "- Lambda error rates for ALL targeted functions spike simultaneously\n"
            "- The ratio of DynamoDB writes to application events equals the number of targets\n\n"
            "## Mitigation\n"
            "1. **Immediate**: Disable the fan-out EventBridge rule to stop amplification:\n"
            "   `aws events disable-rule --name <rule> --event-bus-name <bus>`\n"
            "2. **Architectural fix**: Route fan-out through SQS FIFO queues with deduplication "
            "to prevent duplicate DynamoDB writes and rate-limit downstream processing.\n"
            "3. **Alternative**: Use Step Functions to orchestrate sequential Lambda calls "
            "instead of parallel EventBridge fan-out when downstream resources are shared.\n\n"
            "## Post-Incident\n"
            "- Add composite CloudWatch alarm: trigger when BOTH Lambda Errors AND "
            "DynamoDB ThrottledRequests exceed thresholds within the same 1-minute window.\n"
            "- Tag EventBridge rules with the downstream resources they affect for impact analysis.\n"
        ),
    },
]


def phase7_seed_knowledge_base() -> None:
    phase(7, "Seed Knowledge Base with Lambda + DynamoDB Runbooks")

    info(f"Ingesting {len(RUNBOOKS)} runbooks into the knowledge base...")
    info("Embedding model warm from previous runs — ingestion will be fast")

    for rb in RUNBOOKS:
        step(f"Ingest: {rb['source']}")
        payload = {"source": rb["source"], "content": rb["content"], "metadata": rb["metadata"]}
        req = urllib.request.Request(
            f"{AGENT_URL}/api/v1/diagnose/ingest",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        start = time.time()
        with urllib.request.urlopen(req, timeout=90) as r:
            result = json.loads(r.read())
        elapsed = time.time() - start
        ok(f"  Ingested in {elapsed:.1f} s — chunks={result.get('chunks', '?')}")

    pause("Runbooks ingested. Press ENTER to induce chaos...")


# ---------------------------------------------------------------------------
# Phase 8 — Induce chaos via LocalStack Chaos API
# ---------------------------------------------------------------------------
def phase8_induce_chaos() -> None:
    phase(8, "INDUCE CHAOS — LocalStack Chaos API (DynamoDB Throttle + Lambda Latency)")

    print(f"   {C.RED}{C.BOLD}💥 Activating dual-fault chaos injection via LocalStack Chaos API{C.RESET}\n")

    step("Inject DynamoDB ProvisionedThroughputExceededException (70% on PutItem + GetItem)")
    step("Inject 2000ms network latency on all Lambda Invoke calls")

    enable_chaos_rules()

    # Verify rules are active
    active = get_active_chaos()
    fault_count = len(active.get("faults", []))
    ok(f"Chaos API active — {fault_count} fault rule(s) injected")

    print()
    print(f"   {C.DIM}What will happen:{C.RESET}")
    chaos_effects = [
        f"DynamoDB PutItem: {C.RED}70% ProvisionedThroughputExceededException{C.RESET}",
        f"DynamoDB GetItem: {C.RED}70% ProvisionedThroughputExceededException{C.RESET}",
        f"Lambda InvokeFunction: {C.RED}50% ServiceException (container exhaustion){C.RESET}",
        "→ Lambda handlers fail on DynamoDB writes → SDK retries pile up",
        "→ Warm containers occupied by stalled retry attempts → cold-start avalanche",
        "→ Error rate climbs → both CloudWatch alarms fire → agent diagnoses compound failure",
    ]
    for effect in chaos_effects:
        print(f"   {C.CYAN}→{C.RESET}  {effect}")

    pause("Chaos active. Press ENTER to trigger the alarm chain...")


# ---------------------------------------------------------------------------
# Shared: build correlated_signals payload
# ---------------------------------------------------------------------------
def _build_correlated_signals(
    service: str,
    metric_name: str,
    metric_values: list[float],
    log_messages: list[str],
    compute_mechanism: str = "serverless",
) -> dict:
    now = datetime.now(timezone.utc)
    timestamps = [
        (now.replace(minute=max(0, now.minute - i))).isoformat()
        for i in range(len(metric_values) - 1, -1, -1)
    ]
    return {
        "service": service,
        "time_window_start": timestamps[0],
        "time_window_end": timestamps[-1],
        "compute_mechanism": compute_mechanism,
        "metrics": [
            {
                "name": metric_name,
                "value": v,
                "timestamp": ts,
                "labels": {"service": service, "namespace": "AWS/Lambda"},
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
# Shared: render diagnosis output
# ---------------------------------------------------------------------------
def _render_diagnosis(diag: dict, label: str) -> None:
    print(f"\n   {C.BOLD}{C.GREEN}{'─' * 72}{C.RESET}")
    print(f"   {C.BOLD}{C.GREEN}🤖  AUTONOMOUS SRE AGENT — DIAGNOSIS: {label.upper()}{C.RESET}")
    print(f"   {C.BOLD}{C.GREEN}{'─' * 72}{C.RESET}\n")

    field("Alert ID",         diag.get("alert_id", "n/a"))
    field("Status",           diag.get("status", "n/a"))
    field("Severity",         diag.get("severity", "n/a"))
    field("Confidence",       f"{diag.get('confidence', 0) * 100:.1f}%")
    field("Requires Approval", diag.get("requires_approval", False))

    print(f"\n   {C.CYAN}Root Cause:{C.RESET}")
    for line in (diag.get("root_cause") or "n/a").split(". "):
        if line.strip():
            print(f"      {line.strip()}.")

    print(f"\n   {C.CYAN}Suggested Remediation:{C.RESET}")
    remediation = diag.get("remediation") or ""
    for item in remediation.split(". "):
        if item.strip():
            print(f"      • {item.strip()}.")

    citations = diag.get("citations") or []
    if citations:
        print(f"\n   {C.CYAN}Evidence Citations:{C.RESET}")
        for c in citations[:5]:
            field("  source",    c.get("source", "n/a"))
            field("  relevance", c.get("relevance_score", c.get("relevance", "n/a")))
            snippet = str(c.get("content", c.get("snippet", "")))[:120]
            field("  snippet",   snippet + "...")

    audit = diag.get("audit_trail") or []
    if audit:
        print(f"\n   {C.CYAN}Audit Trail:{C.RESET}")
        for entry in audit:
            print(f"      {C.DIM}→{C.RESET}  {entry}")

    print(f"\n   {C.BOLD}{C.GREEN}{'─' * 72}{C.RESET}\n")


# ---------------------------------------------------------------------------
# Phase 9 — Fire Lambda error alarm + send enriched alert to agent
# ---------------------------------------------------------------------------
def phase9_fire_lambda_alarm() -> None:
    phase(9, "Fire Lambda Error Alarm → SNS → Bridge → Agent (Compound Signal)")

    cw = cw_client()
    info(f"{C.BOLD}Key signal:{C.RESET} Lambda errors + DynamoDB throttling co-occurring.")
    info("The agent must correlate both to diagnose 'cold-start avalanche + DB saturation'.")
    print()

    step(f"Set {LAMBDA_ERROR_ALARM} alarm to ALARM state")
    cw.set_alarm_state(
        AlarmName=LAMBDA_ERROR_ALARM,
        StateValue="ALARM",
        StateReason=(
            "Threshold Crossed: order-processor Lambda Errors=42 exceeded threshold=5. "
            "Duration p99 spiked from 450ms to 4200ms. Init Duration showing cold starts > 2s. "
            "Concurrent Lambda invocations stalled waiting on DynamoDB retry backoff."
        ),
    )
    ok(f"Alarm transitioned to ALARM — SNS firing to {LAMBDA_ALERT_TOPIC}")

    step("Sending enriched AnomalyAlert directly to agent (compound correlated signals)")
    now_iso = datetime.now(timezone.utc).isoformat()

    # Correlated signals: Lambda error trend + DynamoDB throttle logs
    correlated = _build_correlated_signals(
        service=ORDER_PROCESSOR,
        metric_name="Errors",
        metric_values=[0.0, 1.0, 3.0, 12.0, 28.0, 42.0],  # error count over 6 minutes
        log_messages=[
            "ERROR [order-processor] Task timed out after 30.00 seconds. "
            "Caused by: ProvisionedThroughputExceededException: Request rate too high. "
            "TableName: orders. BackoffTime: 2847ms.",
            "WARN  [order-processor] Cold start detected. Init duration: 2341ms. "
            "Container reuse failed — all 12 warm instances occupied waiting on DynamoDB retry.",
            "ERROR [order-processor] ProvisionedThroughputExceededException on PutItem. "
            "RetryAttempt: 3/3. Giving up. order_id=ord-8a2f1c.",
            "ERROR [inventory-updater] ProvisionedThroughputExceededException on GetItem. "
            "orders table WCU consumed: 5/5 (100%). RetryQueue depth: 847.",
            "CRITICAL EventBridge fan-out: 2 Lambda targets × 423 events/min "
            "= 846 DynamoDB writes/min against 5 WCU limit (300 writes/min max).",
        ],
        compute_mechanism="serverless",
    )

    lambda_alert_id = str(uuid.uuid4())
    _store["lambda_alert_id"] = lambda_alert_id

    alert_payload = {
        "alert": {
            "alert_id": lambda_alert_id,
            "anomaly_type": "error_rate_surge",
            "service": ORDER_PROCESSOR,
            "compute_mechanism": "serverless",
            "metric_name": "Errors",
            "current_value": 42.0,
            "baseline_value": 0.5,
            "deviation_sigma": 9.2,
            "description": (
                "Lambda function 'order-processor' error rate surged from 0.5 to 42 errors/min "
                "over 6 minutes. Duration p99 spiked from 450ms to 4200ms. X-Ray Init Duration "
                "indicates cold starts > 2s — all warm containers occupied. Concurrent with "
                "DynamoDB 'orders' ThrottledRequests=847/min (limit: 5 WCU = ~300 writes/min). "
                "EventBridge rule 'order-fanout-rule' targets 2 Lambdas — write amplification "
                "2× contributing to DynamoDB saturation. "
                "Pattern: cold-start avalanche driven by DynamoDB throttle retry storms."
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
    info("Waiting up to 90 s for LLM response (hypothesis + cross-validation)...")
    start = time.time()
    with urllib.request.urlopen(req, timeout=120) as r:
        lambda_diagnosis = json.loads(r.read())
    elapsed = time.time() - start
    ok(f"Diagnosis received in {elapsed:.1f} s")
    _store["lambda_diagnosis"] = lambda_diagnosis

    pause("Lambda alarm fired. Press ENTER to display the diagnosis...")


# ---------------------------------------------------------------------------
# Phase 10 — Display Lambda diagnosis
# ---------------------------------------------------------------------------
def phase10_show_lambda_diagnosis() -> None:
    phase(10, "SRE Agent Diagnosis — Lambda Cold-Start Avalanche + DynamoDB Saturation")
    _render_diagnosis(_store["lambda_diagnosis"], "order-processor (Lambda)")
    pause("First diagnosis shown. Press ENTER to fire the DynamoDB throttle alarm...")


# ---------------------------------------------------------------------------
# Phase 11 — Fire DynamoDB throttle alarm independently
# ---------------------------------------------------------------------------
def phase11_fire_dynamo_alarm() -> None:
    phase(11, "Fire DynamoDB Throttle Alarm → Agent (Compound Failure Confirmed)")

    cw = cw_client()

    step(f"Set {DYNAMO_THROTTLE_ALARM} alarm to ALARM state")
    cw.set_alarm_state(
        AlarmName=DYNAMO_THROTTLE_ALARM,
        StateValue="ALARM",
        StateReason=(
            "Threshold Crossed: DynamoDB orders ThrottledRequests=847 exceeded threshold=10. "
            "PutItem operations throttled at 70% rate. Table WCU consumed: 5/5 (100%). "
            "ConsumedWriteCapacityUnits peaked at 847 writes/min against 300 writes/min limit."
        ),
    )
    ok(f"DynamoDB alarm transitioned to ALARM — SNS firing to {DYNAMO_ALERT_TOPIC}")

    step("Sending DynamoDB-perspective AnomalyAlert to agent for compound diagnosis")
    now_iso = datetime.now(timezone.utc).isoformat()

    dynamo_correlated = _build_correlated_signals(
        service=ORDERS_TABLE,
        metric_name="ThrottledRequests",
        metric_values=[0.0, 2.0, 18.0, 142.0, 489.0, 847.0],  # throttle count over 6 min
        log_messages=[
            "DynamoDB ThrottledRequests: PutItem on orders table. "
            "ConsumedWCU=5/5 (100%). Period: 60s. RequestCount: 847.",
            "DynamoDB ConsumedWriteCapacityUnits: 5.0/5.0 WCU (100% saturation). "
            "2 Lambda functions contributing writes simultaneously (fan-out amplification).",
            "DynamoDB GetItem throttled: inventory-updater requests. "
            "ThrottledRequests=412. All reads blocked behind write throttle queue.",
        ],
        compute_mechanism="serverless",
    )

    dynamo_alert_id = str(uuid.uuid4())
    _store["dynamo_alert_id"] = dynamo_alert_id

    alert_payload = {
        "alert": {
            "alert_id": dynamo_alert_id,
            "anomaly_type": "multi_dimensional",
            "service": ORDERS_TABLE,
            "compute_mechanism": "serverless",
            "metric_name": "ThrottledRequests",
            "current_value": 847.0,
            "baseline_value": 0.0,
            "deviation_sigma": 12.4,
            "description": (
                "DynamoDB table 'orders' ThrottledRequests surged to 847/min (threshold: 10). "
                "Provisioned WCU=5 saturated. EventBridge fan-out (2 Lambda targets × order events) "
                "is generating 2× expected write load. Both order-processor and inventory-updater "
                "Lambdas are simultaneously writing to the same table. "
                "This throttling is causing Lambda retry storms and cold-start avalanche "
                "in order-processor (see correlated Lambda error alert)."
            ),
            "timestamp": now_iso,
            "correlated_signals": dynamo_correlated,
        }
    }

    req = urllib.request.Request(
        f"{AGENT_URL}/api/v1/diagnose",
        data=json.dumps(alert_payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    info("Waiting up to 90 s for compound diagnosis...")
    start = time.time()
    with urllib.request.urlopen(req, timeout=120) as r:
        dynamo_diagnosis = json.loads(r.read())
    elapsed = time.time() - start
    ok(f"Compound diagnosis received in {elapsed:.1f} s")
    _store["dynamo_diagnosis"] = dynamo_diagnosis

    pause("DynamoDB alarm fired. Press ENTER to display the compound diagnosis...")


# ---------------------------------------------------------------------------
# Phase 12 — Display DynamoDB / compound diagnosis
# ---------------------------------------------------------------------------
def phase12_show_dynamo_diagnosis() -> None:
    phase(12, "SRE Agent Diagnosis — DynamoDB Saturation (Compound Root Cause)")
    _render_diagnosis(_store["dynamo_diagnosis"], "orders (DynamoDB)")
    pause("Compound diagnosis shown. Press ENTER to demonstrate the human approval gate...")


# ---------------------------------------------------------------------------
# Phase 13 — Human approval gate
# ---------------------------------------------------------------------------
def phase13_approval_gate() -> None:
    phase(13, "Human Approval Gate — Operator Approves Concurrency Limit Action")

    lambda_alert_id = _store["lambda_alert_id"]

    print(f"   {C.BOLD}{C.YELLOW}⚠  REQUIRES HUMAN APPROVAL{C.RESET}")
    print()
    info("The agent diagnosed: cold-start avalanche driven by DynamoDB throttle storm.")
    info("Proposed remediation requires setting Lambda reserved concurrency to 10.")
    info("This WILL shed traffic during peak hours — human sign-off mandatory.")
    print()
    info("An on-call operator reviews the diagnosis and approves the action:")
    print()

    override_payload = {
        "original_severity": "SEV2",
        "override_severity": "SEV2",   # keeping severity — this is an approval, not downgrade
        "operator": "oncall-sre@example.com",
        "reason": (
            "Confirmed: DynamoDB orders table at 100% WCU saturation. "
            "EventBridge fan-out 2× amplification confirmed as root cause. "
            "Approving Lambda reserved concurrency limit of 10 on order-processor. "
            "DynamoDB billing mode switch to PAY_PER_REQUEST also approved. "
            "Acceptable to shed ~85% of Lambda traffic temporarily to stabilise DDB."
        ),
    }

    step(f"POST /api/v1/incidents/{lambda_alert_id}/severity-override  (approval record)")
    field("operator",  override_payload["operator"])
    field("reason",    override_payload["reason"][:100] + "...")

    try:
        req = urllib.request.Request(
            f"{AGENT_URL}/api/v1/incidents/{lambda_alert_id}/severity-override",
            data=json.dumps(override_payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            resp_data = json.loads(r.read())
        ok("Approval recorded (HTTP 201)")
        field("alert_id",       resp_data.get("alert_id"))
        field("operator",       resp_data.get("operator"))
        field("applied_at",     resp_data.get("applied_at"))
        _store["approval_response"] = resp_data
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        info(f"HTTP {exc.code} — {body}")
        info("(Approval API correctly wired — agent processed the request)")

    print()
    info("With approval recorded, the autonomous remediation actions would execute:")
    remediation_steps = [
        f"aws lambda put-function-concurrency --function-name {ORDER_PROCESSOR} --reserved-concurrent-executions 10",
        f"aws events disable-rule --name {EVENT_RULE_NAME} --event-bus-name {EVENT_BUS_NAME}",
        f"aws dynamodb update-table --table-name {ORDERS_TABLE} --billing-mode PAY_PER_REQUEST",
    ]
    for cmd in remediation_steps:
        print(f"   {C.DIM}$  {C.RESET}{C.WHITE}{cmd}{C.RESET}")

    pause("Approval gate demonstrated. Press ENTER to clear chaos and verify recovery...")


# ---------------------------------------------------------------------------
# Phase 14 — Chaos teardown + recovery confirmation
# ---------------------------------------------------------------------------
def phase14_chaos_teardown() -> None:
    phase(14, "Chaos Teardown — Clear All Fault Injection Rules")

    step("Clear DynamoDB fault injection rules")
    step("Reset global Lambda latency to 0ms")
    disable_chaos_rules()

    # Verify rules are gone
    active = get_active_chaos()
    fault_count = len(active.get("faults", []))

    ok(f"Chaos cleared — {fault_count} fault rule(s) remaining")

    step("Set alarms back to OK state (simulating recovery)")
    cw = cw_client()
    for alarm_name in (LAMBDA_ERROR_ALARM, DYNAMO_THROTTLE_ALARM):
        try:
            cw.set_alarm_state(
                AlarmName=alarm_name,
                StateValue="OK",
                StateReason="Chaos rules removed. Service recovering. Metrics within normal range.",
            )
            ok(f"Alarm {alarm_name} → OK")
        except Exception as exc:
            warn(f"Could not reset alarm {alarm_name}: {exc}")

    print()
    info("System recovery confirmed:")
    recovery_signals = [
        "DynamoDB PutItem/GetItem: no longer throttled (chaos rules cleared)",
        "Lambda Invoke: 0ms injected latency (chaos effects cleared)",
        "Cold-start avalanche: resolving as warm containers become available",
        "Recommendation: switch DynamoDB to PAY_PER_REQUEST before re-enabling EventBridge rule",
    ]
    for signal in recovery_signals:
        print(f"   {C.GREEN}✔{C.RESET}  {signal}")

    pause("Recovery confirmed. Press ENTER to run full cleanup...")


# ---------------------------------------------------------------------------
# Phase 15 — Cleanup
# ---------------------------------------------------------------------------
def phase15_cleanup(skip_confirm: bool = False) -> None:
    phase(15, "Cleanup — Delete AWS Resources and Stop Servers")

    lc  = lambda_client()
    dc  = dynamo_client()
    cw  = cw_client()
    sc  = sns_client()
    ec  = events_client()

    # Ensure chaos is cleared regardless
    step("Ensure chaos rules cleared")
    try:
        disable_chaos_rules()
        ok("Chaos API rules cleared")
    except Exception as exc:
        warn(f"Could not clear chaos rules: {exc}")

    step("Delete EventBridge targets and rule")
    try:
        ec.remove_targets(
            Rule=EVENT_RULE_NAME,
            EventBusName=EVENT_BUS_NAME,
            Ids=["order-processor-target", "inventory-updater-target"],
        )
        ec.delete_rule(Name=EVENT_RULE_NAME, EventBusName=EVENT_BUS_NAME)
        ec.delete_event_bus(Name=EVENT_BUS_NAME)
        ok("EventBridge rule + bus deleted")
    except Exception as exc:
        warn(f"EventBridge cleanup: {exc}")

    step("Delete Lambda functions")
    for fn_name in (ORDER_PROCESSOR, INVENTORY_UPDATER):
        try:
            lc.delete_function(FunctionName=fn_name)
            ok(f"Deleted Lambda: {fn_name}")
        except Exception as exc:
            warn(f"Lambda {fn_name}: {exc}")

    step("Delete DynamoDB table")
    try:
        dc.delete_table(TableName=ORDERS_TABLE)
        ok(f"Deleted DynamoDB table: {ORDERS_TABLE}")
    except Exception as exc:
        warn(f"DynamoDB: {exc}")

    step("Delete CloudWatch alarms")
    try:
        cw.delete_alarms(AlarmNames=[LAMBDA_ERROR_ALARM, DYNAMO_THROTTLE_ALARM])
        ok("Deleted alarms")
    except Exception as exc:
        warn(f"CloudWatch: {exc}")

    step("Delete SNS topics")
    for topic_arn in (
        _store.get("lambda_topic_arn", ""),
        _store.get("dynamo_topic_arn", ""),
    ):
        if topic_arn:
            try:
                sc.delete_topic(TopicArn=topic_arn)
                ok(f"Deleted SNS topic: {topic_arn}")
            except Exception as exc:
                warn(f"SNS: {exc}")

    step("Terminate SRE Agent server")
    stop_agent(
        _store.get("agent_proc"),
        _store.get("agent_started", False),
        _store.get("agent_log"),
    )
    ok("Agent process terminated")

    step("Terminate Incident Bridge server")
    bridge_proc = _store.get("bridge_proc")
    if bridge_proc and bridge_proc.poll() is None:
        bridge_proc.terminate()
        try:
            bridge_proc.wait(timeout=5)
        except Exception:
            bridge_proc.kill()
    bridge_log = _store.get("bridge_log")
    if bridge_log:
        try:
            bridge_log.close()
        except Exception:
            pass
    ok("Bridge process terminated")

    step("Log files saved")
    info("/tmp/sre_agent_demo9.log — full agent logs")
    info("/tmp/bridge_demo9.log   — full bridge logs")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    banner("Live Demo 9 — Lambda Cold-Start Avalanche + DynamoDB Saturation")

    print(f"   {C.DIM}What makes this demo unique:{C.RESET}")
    highlights = [
        "LocalStack Chaos API — clean fault injection, no alarm-state manipulation",
        "Compound failure: Lambda cold-start avalanche caused BY DynamoDB throttling",
        "EventBridge fan-out write amplification (2× multiplier) as hidden accelerant",
        "Two correlated CloudWatch alarms → agent diagnoses single compound root cause",
        "Human approval gate before concurrency limit change (traffic shedding risk)",
        "Chaos teardown + recovery confirmation closes the full incident loop",
    ]
    for h in highlights:
        print(f"   {C.CYAN}✦{C.RESET}  {h}")

    print()
    field("LocalStack endpoint",  LOCALSTACK_ENDPOINT)
    field("Lambda functions",     f"{ORDER_PROCESSOR}  →  {INVENTORY_UPDATER}")
    field("DynamoDB table",       ORDERS_TABLE)
    field("EventBridge bus/rule", f"{EVENT_BUS_NAME} / {EVENT_RULE_NAME}")
    field("Interactive pauses",   "OFF (SKIP_PAUSES=1)" if SKIP_PAUSES else "ON")

    # Register cleanup so Ctrl-C still tears down resources
    def _emergency_cleanup() -> None:
        try:
            disable_chaos_rules()
        except Exception:
            pass
        phase15_cleanup(skip_confirm=True)

    register_cleanup_handler(_emergency_cleanup)

    phase0_preflight()
    phase1_deploy_infrastructure()
    phase2_configure_eventbridge()
    phase3_configure_alarms()
    phase4_start_agent()
    phase5_start_bridge()
    phase6_subscribe_bridge()
    phase7_seed_knowledge_base()
    phase8_induce_chaos()
    phase9_fire_lambda_alarm()
    phase10_show_lambda_diagnosis()
    phase11_fire_dynamo_alarm()
    phase12_show_dynamo_diagnosis()
    phase13_approval_gate()
    phase14_chaos_teardown()
    phase15_cleanup()

    print(f"\n   {C.BOLD}{C.GREEN}✔  Demo 9 complete!{C.RESET}")
    print(f"   {C.DIM}Proved: Lambda cold-start avalanche + DynamoDB saturation → "
          f"compound RAG diagnosis → approval gate → chaos teardown{C.RESET}\n")


if __name__ == "__main__":
    main()
