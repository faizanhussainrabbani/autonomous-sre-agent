#!/usr/bin/env python3
"""Live Demo 20 - Unknown Incident Safety Net.

Executive narrative:
1. A LocalStack Lambda incident is triggered without a matching runbook.
2. The agent responds safely and requests human governance.
3. After runbook ingestion, the same LocalStack pattern is re-evaluated with grounded evidence.

Usage:
    SKIP_PAUSES=1 python3 scripts/demo/live_demo_20_unknown_incident_safety_net.py
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4

import boto3
import httpx

from _demo_utils import (
    aws_region,
    banner,
    boto_localstack_kwargs,
    ensure_localstack_running,
    env_bool,
    fail,
    field,
    info,
    localstack_auth_token,
    localstack_endpoint,
    ok,
    pause_if_interactive,
    phase,
    step,
)


AGENT_PORT = int(os.getenv("AGENT_PORT", "8181"))
AGENT_URL = f"http://127.0.0.1:{AGENT_PORT}"
SKIP_PAUSES = env_bool("SKIP_PAUSES", False)
REPO_ROOT = Path(__file__).parent.parent.parent
VENV_UVICORN = REPO_ROOT / ".venv" / "bin" / "uvicorn"
LOG_PATH = Path("/tmp/sre_agent_demo20.log")
LOCALSTACK_ENDPOINT = localstack_endpoint()
AWS_REGION = aws_region("us-east-1")
ACCOUNT_ID = "000000000000"
FUNCTION_NAME = "quantum-edge-gateway"
LAMBDA_ROLE_ARN = f"arn:aws:iam::{ACCOUNT_ID}:role/lambda-role"


class DemoError(RuntimeError):
    pass


def pause(prompt: str) -> None:
    pause_if_interactive(SKIP_PAUSES, prompt)


def require_llm_key() -> None:
    if os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY"):
        return
    raise DemoError(
        "No LLM key found. Set ANTHROPIC_API_KEY or OPENAI_API_KEY before running this demo."
    )


def is_agent_healthy() -> bool:
    try:
        with httpx.Client(timeout=2.0) as client:
            response = client.get(f"{AGENT_URL}/health")
        return response.status_code == 200
    except Exception:
        return False


def start_or_reuse_agent() -> tuple[subprocess.Popen | None, bool, object | None]:
    if is_agent_healthy():
        info("Reusing existing SRE Agent API process")
        return None, False, None

    if not VENV_UVICORN.exists():
        raise DemoError(f"uvicorn executable not found at {VENV_UVICORN}")

    log_handle = open(LOG_PATH, "w")
    process = subprocess.Popen(
        [
            str(VENV_UVICORN),
            "sre_agent.api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(AGENT_PORT),
        ],
        cwd=str(REPO_ROOT),
        stdout=log_handle,
        stderr=log_handle,
    )

    deadline = time.time() + 40
    while time.time() < deadline:
        if is_agent_healthy():
            ok(f"SRE Agent API started on {AGENT_URL}")
            info(f"Agent logs: {LOG_PATH}")
            return process, True, log_handle
        time.sleep(1)

    tail = ""
    try:
        tail = LOG_PATH.read_text()[-1200:]
    except Exception:
        tail = "<unable to read log tail>"
    raise DemoError(f"Agent failed to start within 40s. Log tail:\n{tail}")


def stop_agent(process: subprocess.Popen | None, started_by_demo: bool, log_handle: object | None) -> None:
    if started_by_demo and process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
    if log_handle is not None:
        try:
            log_handle.close()
        except Exception:
            pass


def localstack_clients() -> tuple[Any, Any]:
    kwargs = boto_localstack_kwargs(LOCALSTACK_ENDPOINT, AWS_REGION)
    return boto3.client("lambda", **kwargs), boto3.client("cloudwatch", **kwargs)


def wait_for_lambda_active(lambda_client: Any, function_name: str, timeout_seconds: int = 90) -> None:
    try:
        waiter = lambda_client.get_waiter("function_active_v2")
        waiter.config.delay = 3
        waiter.config.max_attempts = max(1, timeout_seconds // 3)
        waiter.wait(FunctionName=function_name)
        return
    except Exception:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            try:
                state = lambda_client.get_function_configuration(
                    FunctionName=function_name
                ).get("State", "Active")
                if state == "Active":
                    return
            except Exception:
                pass
            time.sleep(2)
    raise DemoError(f"LocalStack Lambda {function_name} did not reach Active state")


def ensure_demo_lambda(lambda_client: Any) -> str:
    code = (
        "import json\n"
        "def handler(event, context):\n"
        "    if event.get('induce_error'):\n"
        "        raise RuntimeError('Unknown parity drift triggered control-plane failure')\n"
        "    return {'statusCode': 200, 'body': json.dumps({'status': 'ok'})}\n"
    )

    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("index.py", code)
    zip_bytes = zip_buffer.getvalue()

    try:
        lambda_client.delete_function(FunctionName=FUNCTION_NAME)
        info(f"Removed previous LocalStack Lambda: {FUNCTION_NAME}")
        time.sleep(1)
    except Exception:
        pass

    response = lambda_client.create_function(
        FunctionName=FUNCTION_NAME,
        Runtime="python3.11",
        Role=LAMBDA_ROLE_ARN,
        Handler="index.handler",
        Code={"ZipFile": zip_bytes},
        Timeout=15,
        MemorySize=128,
        Description="Demo 20 unknown-incident simulator",
    )
    wait_for_lambda_active(lambda_client, FUNCTION_NAME)
    return response.get("FunctionArn", "")


def trigger_localstack_incident(lambda_client: Any) -> dict[str, Any]:
    request_id = str(uuid4())
    invoked_at = datetime.now(timezone.utc).isoformat()
    response = lambda_client.invoke(
        FunctionName=FUNCTION_NAME,
        Payload=json.dumps({"induce_error": True, "request_id": request_id}).encode("utf-8"),
    )
    payload_raw = response["Payload"].read().decode("utf-8")
    return {
        "request_id": request_id,
        "invoked_at": invoked_at,
        "status_code": response.get("StatusCode", 0),
        "function_error": response.get("FunctionError", "none"),
        "payload": payload_raw,
    }


def read_lambda_error_sum(cloudwatch_client: Any) -> float:
    end_time = datetime.now(timezone.utc)
    start_time = end_time.replace(minute=max(0, end_time.minute - 10))
    response = cloudwatch_client.get_metric_statistics(
        Namespace="AWS/Lambda",
        MetricName="Errors",
        Dimensions=[{"Name": "FunctionName", "Value": FUNCTION_NAME}],
        StartTime=start_time,
        EndTime=end_time,
        Period=60,
        Statistics=["Sum"],
    )
    datapoints = response.get("Datapoints", [])
    if not datapoints:
        return 1.0
    return max(float(point.get("Sum", 0.0)) for point in datapoints)


def build_alert_payload(
    function_arn: str,
    localstack_incident: dict[str, Any],
    error_sum: float,
) -> dict[str, Any]:
    metric_peak = max(1.0, error_sum)
    metric_mid = max(0.5, metric_peak * 0.65)
    metric_start = max(0.2, metric_peak * 0.30)
    now = datetime.now(timezone.utc)
    metric_times = [
        (now.replace(second=0)).isoformat(),
        now.isoformat(),
        datetime.now(timezone.utc).isoformat(),
    ]

    return {
        "alert": {
            "alert_id": str(uuid4()),
            "anomaly_type": "multi_dimensional",
            "service": "quantum-edge-gateway",
            "resource_id": function_arn or FUNCTION_NAME,
            "compute_mechanism": "serverless",
            "metric_name": "aws_lambda_errors",
            "current_value": metric_peak,
            "baseline_value": 0.1,
            "deviation_sigma": 8.6,
            "description": (
                "LocalStack Lambda is failing with an unfamiliar control-plane error pattern. "
                "Agent must remain safe until runbook context is available."
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "correlated_signals": {
                "service": "quantum-edge-gateway",
                "compute_mechanism": "serverless",
                "time_window_start": metric_times[0],
                "time_window_end": metric_times[-1],
                "metrics": [
                    {
                        "name": "aws_lambda_errors",
                        "value": metric_start,
                        "timestamp": metric_times[0],
                        "labels": {"service": "quantum-edge-gateway"},
                    },
                    {
                        "name": "aws_lambda_errors",
                        "value": metric_mid,
                        "timestamp": metric_times[1],
                        "labels": {"service": "quantum-edge-gateway"},
                    },
                    {
                        "name": "aws_lambda_errors",
                        "value": metric_peak,
                        "timestamp": metric_times[2],
                        "labels": {"service": "quantum-edge-gateway"},
                    },
                ],
                "logs": [
                    {
                        "timestamp": localstack_incident["invoked_at"],
                        "message": (
                            "LocalStack invocation failure "
                            f"request_id={localstack_incident['request_id']} "
                            f"function_error={localstack_incident['function_error']}"
                        ),
                        "severity": "ERROR",
                        "labels": {"service": "quantum-edge-gateway"},
                    }
                ],
                "traces": [],
                "events": [
                    {
                        "event_type": "aws.lambda.invocation_error",
                        "source": "aws.lambda",
                        "timestamp": localstack_incident["invoked_at"],
                        "metadata": {
                            "request_id": localstack_incident["request_id"],
                            "status_code": localstack_incident["status_code"],
                            "function_arn": function_arn,
                        },
                        "labels": {"service": "quantum-edge-gateway"},
                    }
                ],
            },
        }
    }


def build_runbook_payload() -> dict:
    return {
        "source": "runbooks/quantum-edge-gateway-regression.md",
        "metadata": {
            "service": "quantum-edge-gateway",
            "type": "runbook",
            "owner": "edge-reliability",
        },
        "content": (
            "# Quantum Edge Gateway Regression\n\n"
            "## Symptom\n"
            "- quasar_flux_error_ratio jumps above 80\n"
            "- control-plane handshake collapse for shard groups\n\n"
            "## Root Cause Pattern\n"
            "- parity drift after control-plane rollout\n"
            "- inconsistent shard configuration propagation\n\n"
            "## Immediate Remediation\n"
            "1. freeze rollout for gateway control-plane\n"
            "2. restore previous shard parity map\n"
            "3. validate handshake success before re-enable\n"
        ),
    }


def diagnose(client: httpx.Client, payload: dict, timeout_seconds: float = 150.0) -> dict:
    response = client.post(f"{AGENT_URL}/api/v1/diagnose", json=payload, timeout=timeout_seconds)
    response.raise_for_status()
    return response.json()


def has_audit_marker(audit_trail: list, marker: str) -> bool:
    return any(marker in str(item) for item in audit_trail)


def main() -> None:
    process = None
    started_by_demo = False
    log_handle = None

    banner("Live Demo 20 - Unknown Incident Safety Net (LocalStack)")
    info("Goal: show safe unknown-incident response before and after runbook ingestion")

    try:
        require_llm_key()
        phase(1, "LocalStack pre-flight and incident simulation setup")
        ensure_localstack_running(
            endpoint=LOCALSTACK_ENDPOINT,
            auth_token=localstack_auth_token(),
            timeout_seconds=90,
            emit_logs=True,
        )
        lambda_client, cloudwatch_client = localstack_clients()
        function_arn = ensure_demo_lambda(lambda_client)
        ok("LocalStack Lambda simulator is active")
        field("Function", FUNCTION_NAME)
        field("Function ARN", function_arn)
        field("LocalStack endpoint", LOCALSTACK_ENDPOINT)

        phase(2, "Start or reuse API process")
        process, started_by_demo, log_handle = start_or_reuse_agent()
        pause("Press ENTER to run baseline diagnosis with no runbook context")

        with httpx.Client(timeout=180.0) as client:
            phase(3, "Baseline unknown incident diagnosis")
            step("Trigger a real LocalStack Lambda failure for baseline input")
            before_incident = trigger_localstack_incident(lambda_client)
            before_error_sum = read_lambda_error_sum(cloudwatch_client)
            field("LocalStack request id", before_incident["request_id"])
            field("Lambda function_error", before_incident["function_error"])
            field("CloudWatch Errors sum", before_error_sum)

            before_payload = build_alert_payload(function_arn, before_incident, before_error_sum)
            before = diagnose(client, before_payload)
            before_citations = len(before.get("citations") or [])
            before_conf = float(before.get("confidence") or 0.0)
            before_requires = bool(before.get("requires_approval"))
            before_audit = before.get("audit_trail") or []
            before_fallback = has_audit_marker(before_audit, "fallback:general_inference_started")
            before_retrieval_miss = has_audit_marker(before_audit, "retrieval:retrieval_miss")

            ok("Baseline diagnosis completed")
            field("Severity", before.get("severity"))
            field("Confidence", f"{before_conf:.2f}")
            field("Citations", before_citations)
            field("Requires approval", before_requires)
            field("Retrieval miss", before_retrieval_miss)
            field("Fallback started", before_fallback)
            field("Root cause (summary)", str(before.get("root_cause", "n/a"))[:140])

            pause("Press ENTER to ingest targeted runbook context")

            phase(4, "Ingest runbook context")
            ingest_response = client.post(
                f"{AGENT_URL}/api/v1/diagnose/ingest",
                json=build_runbook_payload(),
                timeout=120.0,
            )
            ingest_response.raise_for_status()
            ingest_data = ingest_response.json()
            ok("Runbook ingested into RAG store")
            field("Ingest status", ingest_data.get("status"))
            field("Runbook source", ingest_data.get("source"))
            field("Chunks", ingest_data.get("chunks"))

            pause("Press ENTER to re-run diagnosis with fresh evidence context")

            phase(5, "Post-ingestion diagnosis")
            step("Trigger LocalStack incident again after runbook grounding")
            after_incident = trigger_localstack_incident(lambda_client)
            after_error_sum = read_lambda_error_sum(cloudwatch_client)
            field("LocalStack request id", after_incident["request_id"])
            field("Lambda function_error", after_incident["function_error"])
            field("CloudWatch Errors sum", after_error_sum)

            after_payload = build_alert_payload(function_arn, after_incident, after_error_sum)
            after = diagnose(client, after_payload)
            after_citations = len(after.get("citations") or [])
            after_conf = float(after.get("confidence") or 0.0)
            after_requires = bool(after.get("requires_approval"))
            after_audit = after.get("audit_trail") or []
            after_fallback = has_audit_marker(after_audit, "fallback:general_inference_started")
            after_retrieval_miss = has_audit_marker(after_audit, "retrieval:retrieval_miss")

            ok("Post-ingestion diagnosis completed")
            field("Severity", after.get("severity"))
            field("Confidence", f"{after_conf:.2f}")
            field("Citations", after_citations)
            field("Requires approval", after_requires)
            field("Retrieval miss", after_retrieval_miss)
            field("Fallback started", after_fallback)
            field("Root cause (summary)", str(after.get("root_cause", "n/a"))[:140])

            phase(6, "Executive summary")
            ok("Unknown incident flow completed with LocalStack-backed telemetry")
            field("Citations", f"{before_citations} -> {after_citations}")
            field("Confidence", f"{before_conf:.2f} -> {after_conf:.2f}")
            field("Fallback marker", f"{before_fallback} -> {after_fallback}")
            field("Retrieval miss marker", f"{before_retrieval_miss} -> {after_retrieval_miss}")
            info("Business takeaway: the system stays safe first, then becomes more grounded after runbook ingestion")

    except DemoError as exc:
        fail(str(exc))
        raise SystemExit(1)
    except httpx.HTTPError as exc:
        body = exc.response.text if getattr(exc, "response", None) is not None else "n/a"
        fail(f"HTTP error: {exc}")
        info(f"Response body: {body}")
        raise SystemExit(1)
    except Exception as exc:
        fail(f"Unexpected error: {exc}")
        raise SystemExit(1)
    finally:
        stop_agent(process, started_by_demo, log_handle)


if __name__ == "__main__":
    main()
