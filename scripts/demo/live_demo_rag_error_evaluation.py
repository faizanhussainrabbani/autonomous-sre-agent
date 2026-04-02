#!/usr/bin/env python3
"""
Live Demo 19 — LocalStack RAG Error Evaluation Marathon
========================================================

A complex end-to-end LocalStack demo that stresses the current RAG pipeline
with a stream of heterogeneous production-like errors and prints how each error
is evaluated.

What this demo proves:
  1. LocalStack alert fabric can be provisioned (CloudWatch alarms + SNS topic)
  2. The SRE Agent diagnose API can be run live and fed with enriched alert context
  3. The RAG pipeline can ingest multi-document runbooks via chunked ingestion
  4. Multiple error types are evaluated one-by-one with auditable outputs
  5. Retrieval-grounded and retrieval-miss/fallback paths can be distinguished
  6. A final scorecard summarizes severity, confidence, evidence usage, and
     evaluation path for every reported error

Usage
-----
    source .venv/bin/activate
    SKIP_PAUSES=1 .venv/bin/python scripts/demo/live_demo_rag_error_evaluation.py

Environment
-----------
    LOCALSTACK_ENDPOINT   LocalStack endpoint (default: http://localhost:4566)
    AWS_DEFAULT_REGION    AWS region (default: us-east-1)
    AGENT_PORT            SRE Agent port (default: 8181)
    SKIP_PAUSES           Set to "1" to skip interactive ENTER prompts
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import boto3
import httpx
from dotenv import load_dotenv

from _demo_utils import aws_region, env_bool

# Load .env from the project root for LocalStack credentials and API keys.
load_dotenv(Path(__file__).parent.parent.parent / ".env")

LOCALSTACK_ENDPOINT = os.getenv("LOCALSTACK_ENDPOINT", "http://localhost:4566")
AWS_REGION = aws_region("us-east-1")
AGENT_PORT = int(os.getenv("AGENT_PORT", "8181"))
AGENT_URL = f"http://127.0.0.1:{AGENT_PORT}"
SKIP_PAUSES = env_bool("SKIP_PAUSES", False)

ACCOUNT_ID = "000000000000"
SNS_TOPIC_NAME = "sre-rag-error-eval-alerts"
SNS_TOPIC_ARN = f"arn:aws:sns:{AWS_REGION}:{ACCOUNT_ID}:{SNS_TOPIC_NAME}"

VENV_UVICORN = Path(__file__).parent.parent.parent / ".venv" / "bin" / "uvicorn"

LOCALSTACK_AUTH_TOKEN = os.getenv("LOCALSTACK_AUTH_TOKEN") or os.getenv("LOCALSTACK_API_KEY")

_boto_kwargs = {
    "endpoint_url": LOCALSTACK_ENDPOINT,
    "region_name": AWS_REGION,
    "aws_access_key_id": "test",
    "aws_secret_access_key": "test",
}


def cw_client():
    return boto3.client("cloudwatch", **_boto_kwargs)


def sns_client():
    return boto3.client("sns", **_boto_kwargs)


class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"


def banner(title: str) -> None:
    width = 78
    print(f"\n{C.BOLD}{C.BLUE}+{'=' * width}+{C.RESET}")
    print(f"{C.BOLD}{C.BLUE}|{title.center(width)}|{C.RESET}")
    print(f"{C.BOLD}{C.BLUE}+{'=' * width}+{C.RESET}\n")


def phase(number: int, title: str) -> None:
    width = 78
    label = f" PHASE {number}: {title} "
    print(f"\n{C.BOLD}{C.MAGENTA}+{'-' * width}+{C.RESET}")
    print(f"{C.BOLD}{C.MAGENTA}|{label.center(width)}|{C.RESET}")
    print(f"{C.BOLD}{C.MAGENTA}+{'-' * width}+{C.RESET}\n")


def step(msg: str) -> None:
    print(f"\n   {C.YELLOW}>{C.RESET} {C.BOLD}{msg}{C.RESET}")


def ok(msg: str) -> None:
    print(f"   {C.GREEN}OK{C.RESET}  {msg}")


def info(msg: str) -> None:
    print(f"   {C.CYAN}..{C.RESET}  {msg}")


def fail(msg: str) -> None:
    print(f"   {C.RED}!!{C.RESET}  {C.RED}{msg}{C.RESET}")


def field(name: str, value: Any) -> None:
    print(f"   {C.DIM}{name}:{C.RESET} {value}")


def pause(prompt: str = "Press ENTER to continue...") -> None:
    if SKIP_PAUSES:
        print()
        return
    input(f"\n   {C.DIM}{prompt}{C.RESET}\n")


def abort(msg: str) -> None:
    fail(msg)
    _cleanup()
    sys.exit(1)


RUNBOOKS: list[dict[str, Any]] = [
    {
        "source": "runbooks/checkout-memory-pressure.md",
        "metadata": {"service": "checkout-service", "type": "runbook"},
        "content": (
            "# Checkout Service Memory Pressure\n\n"
            "## Symptoms\n"
            "- container_memory_rss rises above 90% of memory limit\n"
            "- OOM kill events with exit code 137\n"
            "- latency spikes due to pod restarts\n\n"
            "## Root Cause\n"
            "Memory leak in cart-session cache with unbounded key growth under flash sales.\n\n"
            "## Remediation\n"
            "1. Scale checkout deployment to add headroom\n"
            "2. Roll out leak fix and set bounded cache size\n"
            "3. Increase memory limit after profiling\n"
        ),
    },
    {
        "source": "runbooks/payment-error-rate-surge.md",
        "metadata": {"service": "payment-service", "type": "runbook"},
        "content": (
            "# Payment Service Error Rate Surge\n\n"
            "## Symptoms\n"
            "- 5xx error rate rises above 15%\n"
            "- upstream retries and timeout bursts\n"
            "- dependency failures from payment-provider gateway\n\n"
            "## Root Cause\n"
            "Retry amplification after provider API latency increase and thread pool saturation.\n\n"
            "## Remediation\n"
            "1. Enable backoff with jitter\n"
            "2. Reduce in-flight concurrency\n"
            "3. Use circuit breaker for provider requests\n"
        ),
    },
    {
        "source": "runbooks/inventory-disk-exhaustion.md",
        "metadata": {"service": "inventory-service", "type": "runbook"},
        "content": (
            "# Inventory Service Disk Exhaustion\n\n"
            "## Symptoms\n"
            "- /var volume utilization above 95%\n"
            "- write failures and WAL append errors\n"
            "- elevated request latency and intermittent 500 responses\n\n"
            "## Root Cause\n"
            "Log rotation misconfiguration and stale snapshots consuming local volume.\n\n"
            "## Remediation\n"
            "1. Clean stale snapshots and rotate logs\n"
            "2. Expand volume or move artifacts to object storage\n"
            "3. Add disk usage alerting thresholds\n"
        ),
    },
    {
        "source": "runbooks/auth-certificate-expiry.md",
        "metadata": {"service": "auth-service", "type": "runbook"},
        "content": (
            "# Auth Service Certificate Expiry\n\n"
            "## Symptoms\n"
            "- TLS handshake failures\n"
            "- certificate validity below 7 days\n"
            "- login and token refresh failures\n\n"
            "## Root Cause\n"
            "Certificate auto-renew failed due to issuer rate limit and stale DNS challenge records.\n\n"
            "## Remediation\n"
            "1. Force certificate renewal with fallback issuer\n"
            "2. Remove stale DNS challenge records\n"
            "3. Add renewal SLO and alerting\n"
        ),
    },
    {
        "source": "runbooks/checkout-latency-spike.md",
        "metadata": {"service": "checkout-service", "type": "postmortem"},
        "content": (
            "# Checkout Latency Spike Postmortem\n\n"
            "## Summary\n"
            "Latency p95 increased from 120ms to 2200ms during cache failover.\n\n"
            "## Root Cause\n"
            "Read path fallback to synchronous DB lookups after cache cluster partition.\n\n"
            "## Remediation\n"
            "1. Re-enable partial cache mode\n"
            "2. Add async warm-up for critical keys\n"
            "3. Protect DB with adaptive load shedding\n"
        ),
    },
]


ERROR_SCENARIOS: list[dict[str, Any]] = [
    {
        "id": "E1",
        "name": "Checkout memory pressure",
        "alarm_name": "CheckoutMemoryPressureHigh",
        "service": "checkout-service",
        "anomaly_type": "memory_pressure",
        "compute_mechanism": "container_instance",
        "metric_name": "container_memory_rss_gb",
        "operator": "GreaterThanOrEqualToThreshold",
        "threshold": 4.0,
        "current_value": 4.8,
        "baseline_value": 2.1,
        "deviation_sigma": 4.6,
        "description": (
            "Checkout service memory usage rose to 4.8GB from 2.1GB baseline and pods are being "
            "restarted with OOMKilled events."
        ),
        "metrics": [2.1, 2.3, 2.7, 3.5, 4.2, 4.8],
        "logs": [
            "ERROR OOMKilled exit=137 pod=checkout-7f8c9d memory_limit=4Gi",
            "WARN cart-session-cache entries exceeded configured max cardinality",
        ],
    },
    {
        "id": "E2",
        "name": "Payment error-rate surge",
        "alarm_name": "PaymentErrorRateSurge",
        "service": "payment-service",
        "anomaly_type": "error_rate_surge",
        "compute_mechanism": "container_instance",
        "metric_name": "http_5xx_rate_pct",
        "operator": "GreaterThanOrEqualToThreshold",
        "threshold": 15.0,
        "current_value": 22.5,
        "baseline_value": 1.8,
        "deviation_sigma": 6.3,
        "description": (
            "Payment service 5xx rate surged to 22.5% with provider timeout storms and retry bursts."
        ),
        "metrics": [1.8, 2.2, 4.8, 9.1, 16.7, 22.5],
        "logs": [
            "ERROR provider timeout after 30s request=pay_2k39",
            "WARN retry queue depth exceeded threshold queue=payment-retry size=842",
        ],
    },
    {
        "id": "E3",
        "name": "Inventory disk exhaustion",
        "alarm_name": "InventoryDiskExhaustion",
        "service": "inventory-service",
        "anomaly_type": "disk_exhaustion",
        "compute_mechanism": "container_instance",
        "metric_name": "disk_utilization_pct",
        "operator": "GreaterThanOrEqualToThreshold",
        "threshold": 90.0,
        "current_value": 97.0,
        "baseline_value": 63.0,
        "deviation_sigma": 5.1,
        "description": (
            "Inventory node disk utilization reached 97% and WAL writes are failing for SKU updates."
        ),
        "metrics": [63.0, 66.0, 71.0, 80.0, 90.0, 97.0],
        "logs": [
            "ERROR WAL append failed no space left on device",
            "WARN logrotate disabled due to invalid config at /etc/logrotate.d/inventory",
        ],
    },
    {
        "id": "E4",
        "name": "Auth certificate expiry",
        "alarm_name": "AuthCertificateExpiry",
        "service": "auth-service",
        "anomaly_type": "certificate_expiry",
        "compute_mechanism": "kubernetes",
        "metric_name": "certificate_days_remaining",
        "operator": "LessThanOrEqualToThreshold",
        "threshold": 7.0,
        "current_value": 2.0,
        "baseline_value": 30.0,
        "deviation_sigma": 7.8,
        "description": (
            "Auth service TLS certificate expires in 2 days and login TLS handshakes are intermittently failing."
        ),
        "metrics": [30.0, 20.0, 14.0, 9.0, 5.0, 2.0],
        "logs": [
            "ERROR tls handshake failed reason=certificate has expired or is not yet valid",
            "WARN cert-manager renewal challenge pending beyond expected SLA",
        ],
    },
    {
        "id": "E5",
        "name": "Checkout latency spike",
        "alarm_name": "CheckoutLatencySpike",
        "service": "checkout-service",
        "anomaly_type": "latency_spike",
        "compute_mechanism": "container_instance",
        "metric_name": "http_p95_latency_ms",
        "operator": "GreaterThanOrEqualToThreshold",
        "threshold": 1000.0,
        "current_value": 2250.0,
        "baseline_value": 120.0,
        "deviation_sigma": 8.1,
        "description": (
            "Checkout p95 latency increased from 120ms to 2250ms during cache failover and DB fallback."
        ),
        "metrics": [120.0, 150.0, 210.0, 600.0, 1400.0, 2250.0],
        "logs": [
            "WARN cache read timeout exceeded fallback_to_db=true",
            "ERROR db connection pool saturation active=200 waiting=480",
        ],
    },
    {
        "id": "E6",
        "name": "Unknown control-plane regression",
        "alarm_name": "MysteryEdgeRegression",
        "service": "mystery-edge-gateway",
        "anomaly_type": "multi_dimensional",
        "compute_mechanism": "virtual_machine",
        "metric_name": "quasar_flux_error_ratio",
        "operator": "GreaterThanOrEqualToThreshold",
        "threshold": 50.0,
        "current_value": 96.0,
        "baseline_value": 3.0,
        "deviation_sigma": 9.4,
        "description": (
            "Unknown quasar-flux parity drift across edge shards caused cross-plane handshake collapse "
            "with no known historical runbook match."
        ),
        "metrics": [3.0, 4.5, 10.0, 22.0, 51.0, 96.0],
        "logs": [
            "ERROR flux lattice mismatch shard=17 parity=delta-omega",
            "ERROR control-plane consensus failed mode=quasar-bridge failure_code=QX-771",
        ],
    },
]


PRESEED_SCENARIO: dict[str, Any] = {
    "id": "E0",
    "name": "Preseed novel retrieval-miss probe",
    "alarm_name": "PreseedNovelRetrievalMiss",
    "service": "preseed-novel-gateway",
    "anomaly_type": "multi_dimensional",
    "compute_mechanism": "virtual_machine",
    "metric_name": "novel_edge_failure_ratio",
    "operator": "GreaterThanOrEqualToThreshold",
    "threshold": 40.0,
    "current_value": 92.0,
    "baseline_value": 2.0,
    "deviation_sigma": 9.7,
    "description": (
        "Preseed control-plane drift with unknown signature before any runbooks are ingested. "
        "Used to validate retrieval-miss and fallback reasoning paths."
    ),
    "metrics": [2.0, 3.0, 8.0, 19.0, 41.0, 92.0],
    "logs": [
        "ERROR preseed drift detector reported unknown consensus vector hash",
        "ERROR edge-plane quorum collapse event code=PRESEED-X91",
    ],
}


_agent_proc: subprocess.Popen | None = None
_actual_topic_arn: str = SNS_TOPIC_ARN
_results: list[dict[str, Any]] = []


def _localstack_healthy() -> bool:
    import urllib.request

    try:
        with urllib.request.urlopen(f"{LOCALSTACK_ENDPOINT}/_localstack/health", timeout=3) as response:
            data = json.loads(response.read())
            return data.get("status") in {"running", "ok"} or bool(data.get("services"))
    except Exception:
        return False


def _start_localstack() -> None:
    step("LocalStack is not reachable, attempting auto-start")
    env = os.environ.copy()
    if LOCALSTACK_AUTH_TOKEN:
        env["LOCALSTACK_AUTH_TOKEN"] = LOCALSTACK_AUTH_TOKEN

    started = subprocess.run(
        ["localstack", "start", "-d"],
        env=env,
        capture_output=True,
        text=True,
    )
    if started.returncode not in (0, 1):
        abort(
            "localstack start failed "
            f"(exit={started.returncode}) stderr={started.stderr.strip()}"
        )

    info("Waiting for LocalStack health endpoint (up to 90s)")
    deadline = time.time() + 90
    while time.time() < deadline:
        if _localstack_healthy():
            ok(f"LocalStack running at {LOCALSTACK_ENDPOINT}")
            return
        time.sleep(3)
        print(".", end="", flush=True)
    print()
    abort("LocalStack did not become healthy within 90 seconds")


def _kill_port_if_busy(port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        in_use = sock.connect_ex(("127.0.0.1", port)) == 0
    if not in_use:
        ok(f"Port {port} is free")
        return

    result = subprocess.run(["lsof", "-ti", f":{port}"], capture_output=True, text=True)
    pids = [pid for pid in result.stdout.strip().split() if pid]
    if not pids:
        abort(f"Port {port} is busy, but owning process could not be identified")

    info(f"Port {port} busy, terminating PID(s): {', '.join(pids)}")
    subprocess.run(["kill", "-9", *pids], check=False, capture_output=True)
    time.sleep(1)
    ok(f"Port {port} released")


def phase0_preflight() -> None:
    phase(0, "Pre-flight and environment validation")

    step("Check LocalStack availability")
    if _localstack_healthy():
        ok(f"LocalStack reachable at {LOCALSTACK_ENDPOINT}")
    else:
        _start_localstack()

    step("Check required Python packages")
    missing = []
    for pkg in ("boto3", "httpx", "uvicorn", "fastapi"):
        try:
            __import__(pkg)
            ok(f"{pkg} available")
        except ImportError:
            missing.append(pkg)
            fail(f"{pkg} missing")
    if missing:
        abort(f"Install missing dependencies first: pip install {' '.join(missing)}")

    step("Check service ports")
    _kill_port_if_busy(AGENT_PORT)

    field("LocalStack endpoint", LOCALSTACK_ENDPOINT)
    field("AWS region", AWS_REGION)
    field("Agent URL", AGENT_URL)
    field("Scenarios", len(ERROR_SCENARIOS))
    pause("Pre-flight complete. Press ENTER to provision LocalStack alert fabric...")


def phase1_provision_localstack_alert_fabric() -> None:
    global _actual_topic_arn

    phase(1, "Provision LocalStack CloudWatch alarms and SNS topic")
    cloudwatch = cw_client()
    sns = sns_client()

    step("Create fresh SNS topic")
    try:
        sns.delete_topic(TopicArn=SNS_TOPIC_ARN)
    except Exception:
        pass
    topic_resp = sns.create_topic(Name=SNS_TOPIC_NAME)
    _actual_topic_arn = topic_resp["TopicArn"]
    ok(f"SNS topic ready: {_actual_topic_arn}")

    step("Create one CloudWatch alarm per error scenario")
    all_alarms = [PRESEED_SCENARIO["alarm_name"]] + [
        scenario["alarm_name"] for scenario in ERROR_SCENARIOS
    ]
    cloudwatch.delete_alarms(AlarmNames=all_alarms)

    for scenario in [PRESEED_SCENARIO] + ERROR_SCENARIOS:
        cloudwatch.put_metric_alarm(
            AlarmName=scenario["alarm_name"],
            MetricName=scenario["metric_name"],
            Namespace="SRE/LiveDemo",
            Statistic="Average",
            Period=60,
            EvaluationPeriods=1,
            Threshold=float(scenario["threshold"]),
            ComparisonOperator=scenario["operator"],
            AlarmActions=[_actual_topic_arn],
            Dimensions=[
                {"Name": "Service", "Value": scenario["service"]},
            ],
            AlarmDescription=(
                f"Demo alarm for {scenario['name']} routed to SRE error-evaluation topic"
            ),
            TreatMissingData="breaching",
        )
        ok(f"Alarm created: {scenario['alarm_name']}")

    pause("Alert fabric provisioned. Press ENTER to start the SRE Agent API...")


def phase2_start_agent() -> None:
    global _agent_proc

    phase(2, "Start SRE Agent FastAPI server")

    if not VENV_UVICORN.exists():
        abort(f"uvicorn executable not found at {VENV_UVICORN}")

    step("Launch uvicorn sre_agent.api.main:app")
    agent_log = open("/tmp/sre_agent_demo19.log", "w")
    _agent_proc = subprocess.Popen(
        [
            str(VENV_UVICORN),
            "sre_agent.api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(AGENT_PORT),
        ],
        cwd=str(Path(__file__).parent.parent.parent),
        stdout=agent_log,
        stderr=agent_log,
    )
    info(f"Agent PID: {_agent_proc.pid}")
    info("Agent logs: /tmp/sre_agent_demo19.log")

    step("Wait for /health")
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            with httpx.Client(timeout=2.0) as client:
                response = client.get(f"{AGENT_URL}/health")
                response.raise_for_status()
                status = response.json().get("status")
                if status in {"ok", "healthy"}:
                    ok(f"Agent is healthy: {status}")
                    pause("Agent ready. Press ENTER to ingest runbooks into RAG storage...")
                    return
        except Exception:
            time.sleep(1)

    try:
        logs = Path("/tmp/sre_agent_demo19.log").read_text()[-1200:]
    except Exception:
        logs = "<log unavailable>"
    abort(f"Agent did not become healthy. Tail logs:\n{logs}")


def _evaluate_scenario(scenario: dict[str, Any]) -> None:
    step(f"{scenario['id']} - {scenario['name']}")

    cloudwatch = cw_client()
    try:
        cloudwatch.set_alarm_state(
            AlarmName=scenario["alarm_name"],
            StateValue="ALARM",
            StateReason=(
                f"Synthetic incident for {scenario['service']}: "
                f"{scenario['metric_name']} crossed threshold"
            ),
        )
        ok(f"Alarm forced to ALARM: {scenario['alarm_name']}")
    except Exception as exc:
        fail(f"Alarm state update failed: {exc}")

    alert_id = str(uuid4())
    payload = _build_alert_payload(scenario, alert_id)

    started = time.time()
    try:
        diagnosis = _post_diagnosis(payload)
        elapsed = time.time() - started

        citations = diagnosis.get("citations") or []
        audit = diagnosis.get("audit_trail") or []
        path = _evaluation_path(diagnosis)

        ok(
            f"Diagnosis returned in {elapsed:.1f}s severity={diagnosis.get('severity')} "
            f"confidence={diagnosis.get('confidence')} citations={len(citations)}"
        )
        info(f"Path: {path}")
        info(f"Root cause: {str(diagnosis.get('root_cause', 'n/a'))[:140]}")
        info(f"Audit actions captured: {len(audit)}")

        _results.append(
            {
                "scenario": scenario,
                "alert_id": alert_id,
                "diagnosis": diagnosis,
                "elapsed": elapsed,
                "error": None,
            }
        )
    except Exception as exc:
        fail(f"Diagnosis failed: {exc}")
        _results.append(
            {
                "scenario": scenario,
                "alert_id": alert_id,
                "diagnosis": None,
                "elapsed": None,
                "error": str(exc),
            }
        )


def phase3_probe_retrieval_miss_before_seeding() -> None:
    phase(3, "Probe retrieval-miss path before runbook ingestion")

    info("No runbooks are ingested yet. This should probe retrieval-miss behavior.")
    _evaluate_scenario(PRESEED_SCENARIO)
    pause("Preseed probe complete. Press ENTER to ingest runbooks...")


def phase4_seed_rag_kb() -> None:
    phase(4, "Seed RAG knowledge base with multi-service runbooks")

    with httpx.Client(timeout=120.0) as client:
        for document in RUNBOOKS:
            step(f"Ingest {document['source']}")
            response = client.post(f"{AGENT_URL}/api/v1/diagnose/ingest", json=document)
            response.raise_for_status()
            body = response.json()
            ok(
                f"Stored source={body.get('source')} chunks={body.get('chunks')} "
                f"doc_id={body.get('doc_id')}"
            )

    pause("Knowledge base seeded. Press ENTER to replay the full error stream...")


def _correlated_signals_for_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    values = scenario["metrics"]
    count = len(values)

    timestamps = [
        (now - timedelta(minutes=(count - idx - 1))).isoformat()
        for idx in range(count)
    ]

    return {
        "service": scenario["service"],
        "compute_mechanism": scenario["compute_mechanism"],
        "time_window_start": timestamps[0],
        "time_window_end": timestamps[-1],
        "metrics": [
            {
                "name": scenario["metric_name"],
                "value": float(value),
                "timestamp": timestamp,
                "labels": {"service": scenario["service"]},
            }
            for value, timestamp in zip(values, timestamps)
        ],
        "logs": [
            {
                "timestamp": timestamps[-1],
                "message": line,
                "severity": "ERROR",
                "labels": {"service": scenario["service"]},
            }
            for line in scenario["logs"]
        ],
        "traces": [],
        "events": [],
    }


def _build_alert_payload(scenario: dict[str, Any], alert_id: str) -> dict[str, Any]:
    return {
        "alert": {
            "alert_id": alert_id,
            "anomaly_type": scenario["anomaly_type"],
            "service": scenario["service"],
            "compute_mechanism": scenario["compute_mechanism"],
            "metric_name": scenario["metric_name"],
            "current_value": float(scenario["current_value"]),
            "baseline_value": float(scenario["baseline_value"]),
            "deviation_sigma": float(scenario["deviation_sigma"]),
            "description": scenario["description"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "correlated_signals": _correlated_signals_for_scenario(scenario),
        }
    }


def _post_diagnosis(payload: dict[str, Any]) -> dict[str, Any]:
    with httpx.Client(timeout=150.0) as client:
        response = client.post(f"{AGENT_URL}/api/v1/diagnose", json=payload)
        response.raise_for_status()
        return response.json()


def phase5_replay_error_stream() -> None:
    phase(5, "Replay multi-error stream and capture diagnosis output")

    for scenario in ERROR_SCENARIOS:
        _evaluate_scenario(scenario)

        pause("Press ENTER to continue to the next reported error...")


def _contains_action(audit_trail: list[Any], action: str) -> bool:
    return any(action in str(entry) for entry in audit_trail)


def _evaluation_path(diagnosis: dict[str, Any]) -> str:
    audit = diagnosis.get("audit_trail") or []
    citations = diagnosis.get("citations") or []

    if _contains_action(audit, "validation:root_cause_unresolved"):
        return "unresolved_escalation"
    if _contains_action(audit, "fallback:general_inference_started"):
        return "rag_miss_fallback"
    if citations:
        return "rag_grounded"
    return "novel_escalation"


def phase6_print_evaluation_scorecard() -> None:
    phase(6, "RAG evaluation scorecard across all reported errors")

    headers = [
        "ID",
        "Service",
        "Severity",
        "Conf",
        "Evidence",
        "Approval",
        "Path",
        "Status",
    ]
    widths = [4, 22, 8, 6, 8, 10, 22, 8]

    def fmt_row(values: list[str]) -> str:
        return " | ".join(value.ljust(width)[:width] for value, width in zip(values, widths))

    print("   " + fmt_row(headers))
    print("   " + "-+-".join("-" * width for width in widths))

    total = len(_results)
    passed = 0
    rag_grounded = 0
    fallback_count = 0
    unresolved_count = 0
    approval_count = 0

    for entry in _results:
        scenario = entry["scenario"]
        diagnosis = entry["diagnosis"]
        error = entry["error"]

        if error or diagnosis is None:
            row = [
                scenario["id"],
                scenario["service"],
                "n/a",
                "n/a",
                "0",
                "n/a",
                "request_failed",
                "FAILED",
            ]
            print("   " + fmt_row(row))
            continue

        path = _evaluation_path(diagnosis)
        evidence_count = len(diagnosis.get("citations") or [])
        confidence = diagnosis.get("confidence")
        requires_approval = diagnosis.get("requires_approval")

        if path == "rag_grounded":
            rag_grounded += 1
        elif path == "rag_miss_fallback":
            fallback_count += 1
        elif path == "unresolved_escalation":
            unresolved_count += 1

        if requires_approval:
            approval_count += 1

        passed += 1
        row = [
            scenario["id"],
            scenario["service"],
            str(diagnosis.get("severity", "n/a")),
            f"{float(confidence):.2f}" if confidence is not None else "n/a",
            str(evidence_count),
            "yes" if requires_approval else "no",
            path,
            "SUCCESS",
        ]
        print("   " + fmt_row(row))

    print()
    field("Errors reported", total)
    field("Diagnoses completed", passed)
    field("Diagnoses failed", total - passed)
    field("RAG-grounded evaluations", rag_grounded)
    field("Fallback evaluations", fallback_count)
    field("Unresolved escalations", unresolved_count)
    field("Human-approval required", approval_count)

    if total - passed > 0:
        fail("One or more errors were not evaluated successfully")
    else:
        ok("Every reported error was evaluated and captured in the scorecard")

    pause("Scorecard complete. Press ENTER to clean up LocalStack resources...")


def _cleanup_localstack_resources() -> None:
    cloudwatch = cw_client()
    sns = sns_client()

    alarm_names = [PRESEED_SCENARIO["alarm_name"]] + [
        scenario["alarm_name"] for scenario in ERROR_SCENARIOS
    ]

    try:
        cloudwatch.delete_alarms(AlarmNames=alarm_names)
        ok("Deleted CloudWatch alarms")
    except Exception as exc:
        info(f"Alarm cleanup skipped: {exc}")

    for topic_arn in {_actual_topic_arn, SNS_TOPIC_ARN}:
        try:
            sns.delete_topic(TopicArn=topic_arn)
            ok(f"Deleted SNS topic: {topic_arn}")
        except Exception:
            pass


def _cleanup_agent_process() -> None:
    global _agent_proc

    if _agent_proc and _agent_proc.poll() is None:
        try:
            _agent_proc.terminate()
            _agent_proc.wait(timeout=5)
            ok(f"Stopped agent process {_agent_proc.pid}")
        except Exception:
            _agent_proc.kill()
            info(f"Force-killed agent process {_agent_proc.pid}")
    _agent_proc = None


def _cleanup() -> None:
    phase(7, "Cleanup")
    _cleanup_localstack_resources()
    _cleanup_agent_process()
    info("Agent log available at /tmp/sre_agent_demo19.log")


def _handle_sigint(_sig: int, _frame: Any) -> None:
    print(f"\n{C.YELLOW}Interrupted by user, running cleanup...{C.RESET}")
    _cleanup()
    sys.exit(130)


def main() -> None:
    signal.signal(signal.SIGINT, _handle_sigint)

    banner("Live Demo 19 - LocalStack RAG Error Evaluation Marathon")
    field("LocalStack endpoint", LOCALSTACK_ENDPOINT)
    field("AWS region", AWS_REGION)
    field("Agent URL", AGENT_URL)
    field("Interactive pauses", "OFF" if SKIP_PAUSES else "ON")
    field("Error scenarios", len(ERROR_SCENARIOS))

    pause("Press ENTER to begin the end-to-end run...")

    try:
        phase0_preflight()
        phase1_provision_localstack_alert_fabric()
        phase2_start_agent()
        phase3_probe_retrieval_miss_before_seeding()
        phase4_seed_rag_kb()
        phase5_replay_error_stream()
        phase6_print_evaluation_scorecard()
    finally:
        _cleanup()

    print()
    ok("Demo complete")
    info("Showcased multi-error RAG evaluation path for every reported incident")


if __name__ == "__main__":
    main()
