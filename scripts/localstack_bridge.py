"""
LocalStack SNS → SRE Agent Incident Bridge
==========================================

A lightweight webhook server that catches AWS SNS notifications from
LocalStack CloudWatch Alarms and translates them into the canonical
AnomalyAlert format expected by the SRE Agent's ``/api/v1/diagnose``
endpoint.

Architecture
------------

    LocalStack CloudWatch Alarm
            │
            ▼
    LocalStack SNS (HTTP delivery)
            │
            ▼
    ┌──────────────────────┐
    │  This Bridge (8080)  │  ← Translates AWS Alarm JSON → AnomalyAlert
    └──────────────────────┘
            │
            ▼
    SRE Agent FastAPI (8181)  → RAG + LLM Diagnosis

Usage
-----
    # Terminal — start the bridge:
    source .venv/bin/activate
    python scripts/localstack_bridge.py

    # Then subscribe LocalStack SNS to this webhook:
    awslocal sns subscribe \\
        --topic-arn arn:aws:sns:us-east-1:000000000000:sre-agent-alerts \\
        --protocol http \\
        --notification-endpoint http://host.docker.internal:8080/sns/webhook
"""

from __future__ import annotations

import json
import os
import time
from typing import Any
from uuid import uuid4

import httpx
import uvicorn
from fastapi import FastAPI, Request

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 8080
AGENT_URL = "http://127.0.0.1:8181"

# Enrichment toggle — set BRIDGE_ENRICHMENT=1 to enable CloudWatch enrichment
ENRICHMENT_ENABLED = os.environ.get("BRIDGE_ENRICHMENT", "0") == "1"
LOCALSTACK_ENDPOINT = os.environ.get(
    "LOCALSTACK_ENDPOINT", "http://localhost:4566"
)

# Mapping: CloudWatch alarm name prefix → service + anomaly context
ALARM_SERVICE_MAP: dict[str, dict[str, Any]] = {
    "PaymentProcessor": {
        "service": "payment-processor",
        "anomaly_type": "invocation_error_surge",
        "compute_mechanism": "serverless",
        "metric_name": "Errors",
        "description_template": (
            "CloudWatch alarm '{alarm}' transitioned to ALARM. "
            "Lambda function invocation errors exceeded threshold."
        ),
    },
}

DEFAULT_SERVICE_CONTEXT: dict[str, Any] = {
    "service": "unknown-service",
    "anomaly_type": "error_rate_surge",
    "compute_mechanism": "serverless",
    "metric_name": "Errors",
    "description_template": "CloudWatch alarm '{alarm}' transitioned to ALARM.",
}

# ---------------------------------------------------------------------------
# Colour helpers (for terminal readability)
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

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="LocalStack SNS → SRE Agent Bridge")

# ---------------------------------------------------------------------------
# Enrichment setup (optional — enabled via BRIDGE_ENRICHMENT=1)
# ---------------------------------------------------------------------------
_enricher = None


def _get_enricher():
    """Lazy-initialise the AlertEnricher when enrichment is enabled."""
    global _enricher
    if _enricher is not None:
        return _enricher

    if not ENRICHMENT_ENABLED:
        return None

    try:
        import boto3
        from sre_agent.adapters.cloud.aws.enrichment import AlertEnricher
        from sre_agent.adapters.cloud.aws.resource_metadata import (
            AWSResourceMetadataFetcher,
        )

        kwargs: dict[str, Any] = {}
        if LOCALSTACK_ENDPOINT:
            kwargs["endpoint_url"] = LOCALSTACK_ENDPOINT

        cw_client = boto3.client("cloudwatch", region_name="us-east-1", **kwargs)
        logs_client = boto3.client("logs", region_name="us-east-1", **kwargs)
        lambda_client = boto3.client("lambda", region_name="us-east-1", **kwargs)

        metadata = AWSResourceMetadataFetcher(lambda_client=lambda_client)
        _enricher = AlertEnricher(
            cloudwatch_client=cw_client,
            logs_client=logs_client,
            metadata_fetcher=metadata,
        )
        print(f"   {C.GREEN}✔  Enrichment enabled (CloudWatch + Logs + Metadata){C.RESET}")
        return _enricher
    except Exception as exc:
        print(f"   {C.YELLOW}⚠  Enrichment init failed: {exc}{C.RESET}")
        return None


def _resolve_service_context(alarm_name: str) -> dict[str, Any]:
    """Match an alarm name to its service context using prefix lookup."""
    for prefix, ctx in ALARM_SERVICE_MAP.items():
        if alarm_name.startswith(prefix):
            return ctx
    return DEFAULT_SERVICE_CONTEXT


def _build_agent_payload(alarm_data: dict[str, Any]) -> dict[str, Any]:
    """Translate a CloudWatch Alarm state-change into a canonical AnomalyAlert.

    When enrichment is disabled (default), uses hardcoded fallback values.
    """
    alarm_name = alarm_data.get("AlarmName", "unknown-alarm")
    ctx = _resolve_service_context(alarm_name)

    state_change_time = alarm_data.get(
        "StateChangeTime", time.strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    # Extract trigger info from alarm data
    trigger = alarm_data.get("Trigger", {})
    threshold = float(trigger.get("Threshold", 1.0))

    return {
        "alert": {
            "alert_id": str(uuid4()),
            "anomaly_type": ctx["anomaly_type"],
            "service": ctx["service"],
            "compute_mechanism": ctx["compute_mechanism"],
            "metric_name": ctx["metric_name"],
            "current_value": threshold,
            "baseline_value": 0.0,
            "deviation_sigma": 10.0,
            "description": ctx["description_template"].format(alarm=alarm_name),
            "timestamp": state_change_time,
            "correlated_signals": {
                "service": ctx["service"],
                "window_start": state_change_time,
                "window_end": state_change_time,
                "metrics": [
                    {
                        "name": ctx["metric_name"],
                        "value": threshold,
                        "timestamp": state_change_time,
                        "labels": {"service": ctx["service"]},
                    }
                ],
            },
        }
    }


async def _build_enriched_payload(
    alarm_data: dict[str, Any],
    enricher: Any,
) -> dict[str, Any]:
    """Build an enriched payload using live CloudWatch data.

    Falls back to _build_agent_payload if enrichment fails.
    """
    alarm_name = alarm_data.get("AlarmName", "unknown-alarm")
    ctx = _resolve_service_context(alarm_name)
    trigger = alarm_data.get("Trigger", {})
    namespace = trigger.get("Namespace", "AWS/Lambda")
    metric_name_cw = trigger.get("MetricName", ctx["metric_name"])
    dimensions_raw = trigger.get("Dimensions", [])

    # Convert CloudWatch dimension format to list of dicts
    dimensions = [
        {"Name": d.get("name", d.get("Name", "")),
         "Value": d.get("value", d.get("Value", ""))}
        for d in dimensions_raw
    ] if dimensions_raw else [{"Name": "FunctionName", "Value": ctx["service"]}]

    state_change_time = alarm_data.get(
        "StateChangeTime", time.strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    try:
        enrichment = await enricher.enrich(
            alarm_data=alarm_data,
            service=ctx["service"],
            metric_name=metric_name_cw,
            namespace=namespace,
            dimensions=dimensions,
        )

        print(
            f"   {C.GREEN}✔  Enrichment complete: "
            f"{len(enrichment.get('metrics', []))} metrics, "
            f"{len(enrichment.get('logs', []))} logs, "
            f"σ={enrichment.get('deviation_sigma', '?')}{C.RESET}"
        )

        return {
            "alert": {
                "alert_id": str(uuid4()),
                "anomaly_type": ctx["anomaly_type"],
                "service": ctx["service"],
                "compute_mechanism": ctx["compute_mechanism"],
                "metric_name": ctx["metric_name"],
                "current_value": enrichment.get("current_value", 1.0),
                "baseline_value": enrichment.get("baseline_value", 0.0),
                "deviation_sigma": enrichment.get("deviation_sigma", 10.0),
                "description": ctx["description_template"].format(alarm=alarm_name),
                "timestamp": state_change_time,
                "correlated_signals": {
                    "service": ctx["service"],
                    "window_start": enrichment.get("window_start", state_change_time),
                    "window_end": enrichment.get("window_end", state_change_time),
                    "metrics": enrichment.get("metrics", []),
                    "logs": enrichment.get("logs", []),
                },
            }
        }
    except Exception as exc:
        print(f"   {C.YELLOW}⚠  Enrichment failed, using fallback: {exc}{C.RESET}")
        return _build_agent_payload(alarm_data)


@app.post("/sns/webhook")
async def handle_sns(request: Request) -> dict[str, str]:
    """Receive an SNS HTTP notification, translate it, and forward to the Agent.

    SNS sends two message types:

    * SubscriptionConfirmation: auto-confirmed via the SubscribeURL.
    * Notification: contains the CloudWatch Alarm state-change JSON.
    """
    body = await request.body()
    msg: dict[str, Any] = json.loads(body)

    # ------------------------------------------------------------------
    # Handle SNS subscription confirmation (required by SNS protocol)
    # ------------------------------------------------------------------
    if msg.get("Type") == "SubscriptionConfirmation":
        subscribe_url = msg.get("SubscribeURL", "")
        print(
            f"{C.CYAN}📬 SNS SubscriptionConfirmation received.{C.RESET}\n"
            f"   {C.DIM}Confirming via: {subscribe_url}{C.RESET}"
        )
        async with httpx.AsyncClient() as client:
            await client.get(subscribe_url, timeout=10.0)
        print(f"   {C.GREEN}✔  Subscription confirmed.{C.RESET}")
        return {"status": "subscription_confirmed"}

    # ------------------------------------------------------------------
    # Handle actual alarm notifications
    # ------------------------------------------------------------------
    if msg.get("Type") != "Notification":
        print(f"{C.YELLOW}⚠  Ignoring unknown SNS Type: {msg.get('Type')}{C.RESET}")
        return {"status": "ignored"}

    alarm_data: dict[str, Any] = json.loads(msg.get("Message", "{}"))
    new_state = alarm_data.get("NewStateValue", "")

    if new_state != "ALARM":
        print(
            f"{C.DIM}ℹ  Alarm state changed to '{new_state}' (not ALARM). "
            f"Skipping.{C.RESET}"
        )
        return {"status": "skipped_non_alarm"}

    alarm_name = alarm_data.get("AlarmName", "unknown")
    print(
        f"\n{C.RED}{C.BOLD}🚨 CloudWatch Alarm Triggered: "
        f"{alarm_name}{C.RESET}"
    )
    print(
        f"   {C.DIM}NewStateReason: "
        f"{alarm_data.get('NewStateReason', 'n/a')}{C.RESET}"
    )

    # Build the canonical AnomalyAlert payload
    enricher = _get_enricher()
    if enricher is not None:
        agent_payload = await _build_enriched_payload(alarm_data, enricher)
    else:
        agent_payload = _build_agent_payload(alarm_data)
    print(
        f"   {C.CYAN}→ Forwarding to SRE Agent at "
        f"{AGENT_URL}/api/v1/diagnose ...{C.RESET}"
    )

    # Forward to the running SRE Agent
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{AGENT_URL}/api/v1/diagnose",
                json=agent_payload,
                timeout=60.0,
            )
            data = resp.json()
            print(f"\n{C.GREEN}{C.BOLD}🤖 Agent Diagnosis Output:{C.RESET}")
            print(json.dumps(data, indent=2))
        except httpx.RequestError as exc:
            print(
                f"{C.RED}✖  Failed to reach the SRE Agent: {exc}{C.RESET}\n"
                f"   {C.DIM}Ensure the Agent FastAPI server is running on "
                f"port 8181.{C.RESET}"
            )
            return {"status": "agent_unreachable", "error": str(exc)}

    return {"status": "ok"}


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe for the bridge."""
    return {"status": "healthy", "component": "localstack-bridge"}


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(
        f"\n{C.BOLD}{C.BLUE}LocalStack SNS → SRE Agent Bridge{C.RESET}\n"
        f"{C.DIM}Listening on http://{BRIDGE_HOST}:{BRIDGE_PORT}/sns/webhook{C.RESET}\n"
        f"{C.DIM}Forwarding alerts to {AGENT_URL}/api/v1/diagnose{C.RESET}\n"
    )
    uvicorn.run(app, host=BRIDGE_HOST, port=BRIDGE_PORT)
