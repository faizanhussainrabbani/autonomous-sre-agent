#!/usr/bin/env python3
"""Live Demo 23 - AI Says No Before It Acts.

Executive narrative:
1. A risky remediation plan is denied by safety guardrails.
2. A safer plan is allowed and executed against LocalStack.
3. The output proves risk-first automation and controlled execution.

Usage:
    SKIP_PAUSES=1 python3 scripts/demo/live_demo_23_ai_says_no_before_it_acts.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import zipfile
from io import BytesIO
from typing import Any

import boto3
import structlog

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

from sre_agent.adapters.coordination.in_memory_lock_manager import InMemoryDistributedLockManager
from sre_agent.adapters.cloud.aws.lambda_operator import LambdaOperator
from sre_agent.domain.detection.cloud_operator_registry import CloudOperatorRegistry
from sre_agent.domain.models.canonical import AnomalyAlert, AnomalyType, ComputeMechanism, Severity
from sre_agent.domain.models.diagnosis import Diagnosis
from sre_agent.domain.remediation.engine import RemediationEngine
from sre_agent.domain.remediation.models import ApprovalState
from sre_agent.domain.remediation.planner import RemediationPlanner
from sre_agent.domain.safety.blast_radius import BlastRadiusCalculator
from sre_agent.domain.safety.cooldown import CooldownEnforcer
from sre_agent.domain.safety.guardrails import GuardrailOrchestrator
from sre_agent.domain.safety.kill_switch import KillSwitch


SKIP_PAUSES = env_bool("SKIP_PAUSES", False)
LOCALSTACK_ENDPOINT = localstack_endpoint()
AWS_REGION = aws_region("us-east-1")
ACCOUNT_ID = "000000000000"
FUNCTION_NAME = "checkout-service"
LAMBDA_ROLE_ARN = f"arn:aws:iam::{ACCOUNT_ID}:role/lambda-role"

# Keep output narration simple for executive demos by silencing framework info logs.
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING),
)


def pause(prompt: str) -> None:
    pause_if_interactive(SKIP_PAUSES, prompt)


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
    raise RuntimeError(f"LocalStack Lambda {function_name} did not reach Active state")


def ensure_demo_lambda(lambda_client: Any) -> str:
    code = (
        "import json\n"
        "def handler(event, context):\n"
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
        Description="Demo 23 guardrail remediation target",
    )
    wait_for_lambda_active(lambda_client, FUNCTION_NAME)
    return response.get("FunctionArn", "")


def set_initial_concurrency(lambda_client: Any, function_name: str, initial_value: int = 2) -> None:
    lambda_client.put_function_concurrency(
        FunctionName=function_name,
        ReservedConcurrentExecutions=initial_value,
    )


def read_reserved_concurrency(lambda_client: Any, function_name: str) -> int | None:
    response = lambda_client.get_function_concurrency(FunctionName=function_name)
    return response.get("ReservedConcurrentExecutions")


def make_alert(blast_radius_ratio: float, function_arn: str) -> AnomalyAlert:
    return AnomalyAlert(
        service="checkout-service",
        namespace="",
        resource_id=function_arn or FUNCTION_NAME,
        compute_mechanism=ComputeMechanism.SERVERLESS,
        anomaly_type=AnomalyType.INVOCATION_ERROR_SURGE,
        description="Lambda invocation error surge on checkout-service",
        blast_radius_ratio=blast_radius_ratio,
    )


def make_diagnosis(alert: AnomalyAlert) -> Diagnosis:
    return Diagnosis(
        alert_id=alert.alert_id,
        service=alert.service,
        root_cause="Invocation errors spiked after dependency latency surge",
        confidence=0.93,
        severity=Severity.SEV3,
        reasoning="Known serverless error pattern with controlled concurrency reduction.",
    )


def build_engine(lambda_client: Any) -> RemediationEngine:
    registry = CloudOperatorRegistry()
    registry.register(LambdaOperator(lambda_client=lambda_client))

    kill_switch = KillSwitch()
    cooldown = CooldownEnforcer()
    guardrails = GuardrailOrchestrator(
        kill_switch=kill_switch,
        blast_radius=BlastRadiusCalculator(),
        cooldown=cooldown,
    )

    return RemediationEngine(
        cloud_operator_registry=registry,
        guardrails=guardrails,
        kill_switch=kill_switch,
        cooldown=cooldown,
        lock_manager=InMemoryDistributedLockManager(),
    )


async def run_demo() -> None:
    banner("Live Demo 23 - AI Says No Before It Acts (LocalStack)")
    info("Goal: prove guardrails deny risky automation before executing safer actions")

    phase(1, "LocalStack pre-flight and remediation target setup")
    ensure_localstack_running(
        endpoint=LOCALSTACK_ENDPOINT,
        auth_token=localstack_auth_token(),
        timeout_seconds=90,
        emit_logs=True,
    )
    lambda_client = localstack_lambda_client()
    function_arn = ensure_demo_lambda(lambda_client)
    set_initial_concurrency(lambda_client, FUNCTION_NAME, initial_value=2)
    before_concurrency = read_reserved_concurrency(lambda_client, FUNCTION_NAME)
    ok("LocalStack remediation target is ready")
    field("Function", FUNCTION_NAME)
    field("Function ARN", function_arn)
    field("Initial reserved concurrency", before_concurrency)

    planner = RemediationPlanner()
    engine = build_engine(lambda_client)

    pause("Press ENTER to run high-risk denial path")

    phase(2, "High-risk plan should be denied")
    denied_alert = make_alert(blast_radius_ratio=0.95, function_arn=function_arn)
    denied_plan = await planner.create_plan(
        diagnosis=make_diagnosis(denied_alert),
        alert=denied_alert,
        current_replicas=2,
    )
    denied_plan.approval_state = ApprovalState.APPROVED
    denied_result = await engine.execute(denied_plan)

    ok("Guardrail evaluation completed for high-risk request")
    field("Success", denied_result.success)
    field("Verification", denied_result.verification_status.value)
    field("Decision", denied_result.error_message)

    if denied_result.success:
        raise RuntimeError("Expected denial path to fail, but execution succeeded")

    pause("Press ENTER to run safe execution path")

    phase(3, "Safer plan should execute")
    safe_alert = make_alert(blast_radius_ratio=0.05, function_arn=function_arn)
    safe_plan = await planner.create_plan(
        diagnosis=make_diagnosis(safe_alert),
        alert=safe_alert,
        current_replicas=2,
    )
    safe_plan.approval_state = ApprovalState.APPROVED
    safe_result = await engine.execute(safe_plan)

    action = safe_plan.actions[0]
    after_concurrency = read_reserved_concurrency(lambda_client, FUNCTION_NAME)
    ok("Safe remediation path executed")
    field("Success", safe_result.success)
    field("Verification", safe_result.verification_status.value)
    field("Strategy", safe_plan.strategy.value)
    field("Desired concurrency", action.desired_count)
    field("Lock fencing token", action.lock_fencing_token)
    field("Reserved concurrency (before -> after)", f"{before_concurrency} -> {after_concurrency}")

    if not safe_result.success:
        raise RuntimeError(f"Expected successful execution path, got error: {safe_result.error_message}")

    phase(4, "Executive summary")
    ok("Risk-first automation demonstrated with LocalStack execution")
    info("1. Guardrails denied the risky request")
    info("2. Safe action executed with lock-backed control")
    info("3. Runtime effect was visible in LocalStack concurrency")


if __name__ == "__main__":
    try:
        asyncio.run(run_demo())
    except Exception as exc:  # noqa: BLE001
        fail(str(exc))
        raise SystemExit(1)
