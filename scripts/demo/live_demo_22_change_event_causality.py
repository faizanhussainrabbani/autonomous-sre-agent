#!/usr/bin/env python3
"""Live Demo 22 - Change Event Causality.

Executive narrative:
1. LocalStack-backed infrastructure change signals are converted into EventBridge-style payloads.
2. The same events are retrieved and correlated into diagnosis context.
3. The incident diagnosis is shown with explicit change-impact storyline.

Usage:
    SKIP_PAUSES=1 python3 scripts/demo/live_demo_22_change_event_causality.py
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
    register_cleanup_handler,
    start_or_reuse_agent,
    step,
    stop_agent,
)


AGENT_PORT = int(os.getenv("AGENT_PORT", "8181"))
AGENT_URL = f"http://127.0.0.1:{AGENT_PORT}"
SKIP_PAUSES = env_bool("SKIP_PAUSES", False)
REPO_ROOT = Path(__file__).parent.parent.parent
VENV_UVICORN = REPO_ROOT / ".venv" / "bin" / "uvicorn"
LOG_PATH = Path("/tmp/sre_agent_demo22.log")
LOCALSTACK_ENDPOINT = localstack_endpoint()
AWS_REGION = aws_region("us-east-1")
ACCOUNT_ID = "000000000000"
FUNCTION_NAME = "order-service"
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




def localstack_lambda_client() -> Any:
    kwargs = boto_localstack_kwargs(LOCALSTACK_ENDPOINT, AWS_REGION)
    return boto3.client("lambda", **kwargs)


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
        "        raise RuntimeError('Container startup regression after deployment')\n"
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
        Description="Demo 22 causality event simulator",
    )
    wait_for_lambda_active(lambda_client, FUNCTION_NAME)
    return response.get("FunctionArn", "")


def capture_localstack_change(lambda_client: Any) -> dict[str, Any]:
    request_id = str(uuid4())
    invoked_at = datetime.now(timezone.utc).isoformat()

    lambda_client.update_function_configuration(
        FunctionName=FUNCTION_NAME,
        Description=f"Updated for demo causality at {invoked_at}",
    )
    response = lambda_client.invoke(
        FunctionName=FUNCTION_NAME,
        Payload=json.dumps({"induce_error": True, "request_id": request_id}).encode("utf-8"),
    )
    payload_raw = response["Payload"].read().decode("utf-8")
    function_error = response.get("FunctionError", "none")

    return {
        "request_id": request_id,
        "invoked_at": invoked_at,
        "function_error": function_error,
        "status_code": response.get("StatusCode", 0),
        "payload": payload_raw,
    }


def build_event_payloads(function_arn: str, incident: dict[str, Any]) -> tuple[dict, dict]:
    now = datetime.now(timezone.utc).isoformat()
    deployment_event: dict[str, Any] = {
        "version": "0",
        "id": str(uuid4()),
        "detail-type": "Lambda Function Updated",
        "source": "aws.lambda",
        "account": ACCOUNT_ID,
        "time": now,
        "region": AWS_REGION,
        "resources": [function_arn],
        "detail": {
            "functionName": FUNCTION_NAME,
            "eventType": "configuration_update",
            "reason": "Function configuration updated before incident spike",
        },
    }

    incident_event: dict[str, Any] = {
        "version": "0",
        "id": str(uuid4()),
        "detail-type": "AWS API Call via CloudTrail",
        "source": "aws.lambda",
        "account": ACCOUNT_ID,
        "time": incident["invoked_at"],
        "region": AWS_REGION,
        "resources": [function_arn],
        "detail": {
            "eventName": "Invoke",
            "eventSource": "lambda.amazonaws.com",
            "functionName": FUNCTION_NAME,
            "requestID": incident["request_id"],
            "errorCode": incident["function_error"],
            "requestParameters": {"functionName": FUNCTION_NAME},
        },
    }

    return deployment_event, incident_event


def build_correlated_payload(events: list[dict], incident: dict[str, Any]) -> dict:
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    event_signals = []
    for event in events:
        event_signals.append(
            {
                "event_type": event.get("event_type", "unknown_event"),
                "source": event.get("source", "aws"),
                "timestamp": event.get("timestamp", now_iso),
                "metadata": event.get("metadata", {}),
                "labels": {"service": "order-service"},
            }
        )

    return {
        "alert": {
            "alert_id": str(uuid4()),
            "anomaly_type": "deployment_induced",
            "service": FUNCTION_NAME,
            "compute_mechanism": "serverless",
            "metric_name": "aws_lambda_errors",
            "current_value": 22.0,
            "baseline_value": 0.8,
            "deviation_sigma": 7.1,
            "description": (
                "order-service errors started shortly after a LocalStack change event "
                "and a failed invocation event."
            ),
            "timestamp": now_iso,
            "correlated_signals": {
                "service": FUNCTION_NAME,
                "compute_mechanism": "serverless",
                "time_window_start": now_iso,
                "time_window_end": now_iso,
                "metrics": [
                    {
                        "name": "aws_lambda_errors",
                        "value": 22.0,
                        "timestamp": now_iso,
                        "labels": {"service": FUNCTION_NAME},
                    }
                ],
                "logs": [
                    {
                        "timestamp": incident["invoked_at"],
                        "message": (
                            "ERROR LocalStack invocation failed after configuration update "
                            f"request_id={incident['request_id']}"
                        ),
                        "severity": "ERROR",
                        "labels": {"service": FUNCTION_NAME},
                    }
                ],
                "events": event_signals,
                "traces": [],
            },
        }
    }


def main() -> None:
    process = None
    started_by_demo = False
    log_handle = None

    banner("Live Demo 22 - Change Event Causality (LocalStack)")
    info("Goal: prove LocalStack change events can be correlated into incident reasoning")

    try:
        require_llm_key()

        phase(1, "LocalStack pre-flight and resource setup")
        ensure_localstack_running(
            endpoint=LOCALSTACK_ENDPOINT,
            auth_token=localstack_auth_token(),
            timeout_seconds=90,
            emit_logs=True,
        )
        lambda_client = localstack_lambda_client()
        function_arn = ensure_demo_lambda(lambda_client)
        incident = capture_localstack_change(lambda_client)
        ok("LocalStack change activity captured")
        field("Function", FUNCTION_NAME)
        field("Function ARN", function_arn)
        field("Request id", incident["request_id"])
        field("Function error", incident["function_error"])

        phase(2, "Start or reuse API process")
        process, started_by_demo, log_handle = start_or_reuse_agent(
            port=AGENT_PORT, log_path=str(LOG_PATH),
        )
        register_cleanup_handler(lambda: stop_agent(process, started_by_demo, log_handle))

        deployment_event, incident_event = build_event_payloads(function_arn, incident)

        with httpx.Client(timeout=120.0) as client:
            phase(3, "Post infrastructure change events")
            for idx, payload in enumerate((deployment_event, incident_event), start=1):
                response = client.post(f"{AGENT_URL}/api/v1/events/aws", json=payload, timeout=30.0)
                response.raise_for_status()
                data = response.json()
                ok(f"Event {idx} accepted")
                field("Status", data.get("status"))
                field("Event type", data.get("event_type"))
                field("Source", data.get("source"))

            pause("Press ENTER to retrieve recent service events")

            phase(4, "Retrieve recent events for order-service")
            recent = client.get(
                f"{AGENT_URL}/api/v1/events/aws/recent",
                params={"service": FUNCTION_NAME, "limit": 10},
                timeout=30.0,
            )
            recent.raise_for_status()
            recent_data = recent.json()
            events = recent_data.get("events", [])
            ok("Recent service events fetched")
            field("Service", FUNCTION_NAME)
            field("Event count", recent_data.get("count"))
            for evt in events[-2:]:
                field("Event", f"{evt.get('event_type')} at {evt.get('timestamp')}")

            if not events:
                raise DemoError("No events were returned for order-service")

            pause("Press ENTER to run diagnosis with correlated event context")

            phase(5, "Diagnose incident with event correlation")
            diagnose_payload = build_correlated_payload(events, incident)
            diagnosis_resp = client.post(
                f"{AGENT_URL}/api/v1/diagnose",
                json=diagnose_payload,
                timeout=150.0,
            )
            diagnosis_resp.raise_for_status()
            diagnosis = diagnosis_resp.json()

            ok("Diagnosis generated with event-causality context")
            field("Severity", diagnosis.get("severity"))
            field("Confidence", diagnosis.get("confidence"))
            field("Citations", len(diagnosis.get("citations") or []))
            field("Root cause (summary)", str(diagnosis.get("root_cause", "n/a"))[:200])

            phase(6, "Executive causality brief")
            ok("Change-to-impact causality flow demonstrated")
            info("1. LocalStack change event captured")
            info("2. LocalStack failure event captured")
            info("3. Events correlated through API retrieval")
            info("4. Diagnosis produced with timeline-aware reasoning")

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
