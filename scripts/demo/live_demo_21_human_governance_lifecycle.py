#!/usr/bin/env python3
"""Live Demo 21 - Human Governance Lifecycle.

Executive narrative:
1. A LocalStack incident is classified by the agent.
2. A human operator applies a severity override.
3. The override is verified, then revoked.
4. The system confirms governance state transitions end to end.

Usage:
    SKIP_PAUSES=1 python3 scripts/demo/live_demo_21_human_governance_lifecycle.py
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
LOG_PATH = Path("/tmp/sre_agent_demo21.log")
LOCALSTACK_ENDPOINT = localstack_endpoint()
AWS_REGION = aws_region("us-east-1")
ACCOUNT_ID = "000000000000"
FUNCTION_NAME = "billing-gateway"
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
        "        raise RuntimeError('Downstream provider timeout burst')\n"
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
        Description="Demo 21 governance incident simulator",
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


def build_diagnose_payload(
    function_arn: str,
    localstack_incident: dict[str, Any],
    error_sum: float,
) -> dict:
    metric_value = max(1.0, error_sum)
    return {
        "alert": {
            "alert_id": str(uuid4()),
            "anomaly_type": "error_rate_surge",
            "service": "billing-gateway",
            "resource_id": function_arn or FUNCTION_NAME,
            "compute_mechanism": "serverless",
            "metric_name": "aws_lambda_errors",
            "current_value": metric_value,
            "baseline_value": 0.2,
            "deviation_sigma": 6.8,
            "description": (
                "Billing gateway incident from LocalStack Lambda failures. "
                "Human governance controls are now demonstrated."
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "correlated_signals": {
                "service": "billing-gateway",
                "compute_mechanism": "serverless",
                "time_window_start": localstack_incident["invoked_at"],
                "time_window_end": localstack_incident["invoked_at"],
                "metrics": [
                    {
                        "name": "aws_lambda_errors",
                        "value": metric_value,
                        "timestamp": localstack_incident["invoked_at"],
                        "labels": {"service": "billing-gateway"},
                    }
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
                        "labels": {"service": "billing-gateway"},
                    }
                ],
                "traces": [],
                "events": [],
            },
        }
    }


def build_runbook_payload() -> dict:
    return {
        "source": "runbooks/billing-gateway-error-rate.md",
        "metadata": {"service": "billing-gateway", "type": "runbook"},
        "content": (
            "# Billing Gateway Error Surge\n\n"
            "## Pattern\n"
            "- provider timeout burst\n"
            "- retry storm and 5xx increase\n\n"
            "## Governance\n"
            "- if blast radius extends to checkout, escalate human approval path\n"
            "- use severity override when business impact assessment changes\n"
        ),
    }


def diagnose(client: httpx.Client, payload: dict[str, Any]) -> dict:
    response = client.post(
        f"{AGENT_URL}/api/v1/diagnose",
        json=payload,
        timeout=150.0,
    )
    response.raise_for_status()
    return response.json()


def main() -> None:
    process = None
    started_by_demo = False
    log_handle = None

    banner("Live Demo 21 - Human Governance Lifecycle (LocalStack)")
    info("Goal: prove apply, verify, and revoke governance controls end to end")

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

        with httpx.Client(timeout=120.0) as client:
            phase(3, "Ingest governance-aware runbook context")
            ingest = client.post(
                f"{AGENT_URL}/api/v1/diagnose/ingest",
                json=build_runbook_payload(),
                timeout=120.0,
            )
            ingest.raise_for_status()
            ingest_data = ingest.json()
            ok("Governance runbook ingested")
            field("Ingest status", ingest_data.get("status"))
            field("Runbook source", ingest_data.get("source"))
            field("Chunks", ingest_data.get("chunks"))

            pause("Press ENTER to run diagnosis and create incident context")

            phase(4, "Run diagnosis to produce incident id")
            step("Trigger LocalStack Lambda failure as incident source")
            incident = trigger_localstack_incident(lambda_client)
            error_sum = read_lambda_error_sum(cloudwatch_client)
            field("LocalStack request id", incident["request_id"])
            field("Lambda function_error", incident["function_error"])
            field("CloudWatch Errors sum", error_sum)
            diagnosis_payload = build_diagnose_payload(function_arn, incident, error_sum)
            diagnosis = diagnose(client, diagnosis_payload)
            alert_id = diagnosis.get("alert_id")
            if not alert_id:
                raise DemoError("Diagnosis response did not return alert_id")

            original_severity = diagnosis.get("severity") or "SEV2"
            ok("Incident context created")
            field("Alert id", alert_id)
            field("Severity", original_severity)
            field("Confidence", diagnosis.get("confidence"))

            pause("Press ENTER to apply human severity override")

            phase(5, "Apply severity override")
            override_payload = {
                "original_severity": original_severity,
                "override_severity": "SEV1",
                "operator": "executive.oncall@example.com",
                "reason": "Executive risk review elevated impact to critical status.",
            }
            apply_resp = client.post(
                f"{AGENT_URL}/api/v1/incidents/{alert_id}/severity-override",
                json=override_payload,
                timeout=30.0,
            )
            apply_resp.raise_for_status()
            apply_data = apply_resp.json()
            ok("Override applied")
            field("Override severity", apply_data.get("override_severity"))
            field("Pipeline halted", apply_data.get("halts_pipeline"))

            pause("Press ENTER to verify override read path")

            phase(6, "Read active override")
            get_resp = client.get(
                f"{AGENT_URL}/api/v1/incidents/{alert_id}/severity-override",
                timeout=30.0,
            )
            get_resp.raise_for_status()
            get_data = get_resp.json()
            ok("Override read-back verified")
            field("Original severity", get_data.get("original_severity"))
            field("Override severity", get_data.get("override_severity"))
            field("Operator", get_data.get("operator"))

            pause("Press ENTER to revoke override")

            phase(7, "Revoke override")
            delete_resp = client.delete(
                f"{AGENT_URL}/api/v1/incidents/{alert_id}/severity-override",
                timeout=30.0,
            )
            if delete_resp.status_code != 204:
                raise DemoError(
                    f"Expected 204 from override delete, got {delete_resp.status_code}: {delete_resp.text}"
                )
            ok("Override revoked (204)")

            phase(8, "Confirm override no longer exists")
            missing_resp = client.get(
                f"{AGENT_URL}/api/v1/incidents/{alert_id}/severity-override",
                timeout=30.0,
            )
            if missing_resp.status_code != 404:
                raise DemoError(
                    "Expected 404 after override revoke "
                    f"but got {missing_resp.status_code}: {missing_resp.text}"
                )
            ok("Post-delete check returned 404 as expected")
            info("Business takeaway: human override controls are explicit, auditable, and reversible")

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
