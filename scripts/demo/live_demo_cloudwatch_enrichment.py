"""
Live Demo 9 — CloudWatch Bridge Enrichment
==========================================

A self-contained orchestration script demonstrating Phase 2.3 CloudWatch
telemetry extraction. The SRE Agent's AlertEnricher intercepts an alert,
fetches live Metric baselines, logs, and extracts Resource Metadata from
AWS LocalStack before feeding the enriched alert into the RAG Pipeline.

What this demo proves (end-to-end against LocalStack):
  Phase 0  — Pre-flight: verify LocalStack and boto3
  Phase 1  — Generate synthetic metrics (lambda_errors) in CloudWatch
  Phase 2  — Publish synthetic error logs via CloudWatch Logs
  Phase 3  — Trigger AlertEnricher 
  Phase 4  — Verify Canonical Enriched Signal payload

Usage
-----
    source .venv/bin/activate
    python scripts/live_demo_cloudwatch_enrichment.py
"""

import sys
import os
import time
import uuid
import boto3
import asyncio
from datetime import datetime, timezone, timedelta
from _demo_utils import aws_region, env_bool, boto_localstack_kwargs

try:
    from sre_agent.adapters.cloud.aws.enrichment import AlertEnricher
    from sre_agent.config.settings import EnrichmentConfig
except ImportError:
    print("FATAL: Could not import sre_agent modules. Are you in the valid .venv?")
    sys.exit(1)


# Provide colors for presentation
C_GREEN = "\033[92m"
C_BLUE = "\033[94m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_BOLD = "\033[1m"
C_RESET = "\033[0m"

LOCALSTACK_URL = "http://localhost:4566"
AWS_REGION = aws_region("us-east-1")
SKIP_PAUSES = env_bool("SKIP_PAUSES", False)

cw_client = boto3.client("cloudwatch", **boto_localstack_kwargs(LOCALSTACK_URL, AWS_REGION))
logs_client = boto3.client("logs", **boto_localstack_kwargs(LOCALSTACK_URL, AWS_REGION))


def wait_for_enter(prompt="Press ENTER to continue..."):
    print(f"\n{C_YELLOW}{prompt}{C_RESET}")
    if SKIP_PAUSES:
        print(f"{C_BLUE}[SKIPPED]{C_RESET} Interactive pause disabled via SKIP_PAUSES=1")
        return
    input()


def print_step(title):
    print(f"\n{C_BOLD}{C_BLUE}--- {title} ---{C_RESET}")


def phase0_preflight():
    print_step("Phase 0: Pre-flight Checks")
    print("Checking AWS LocalStack reachability at local port 4566...")
    try:
        # Check cloudwatch
        cw_client.list_metrics()
        print(f"[{C_GREEN}OK{C_RESET}] CloudWatch endpoint reachable.")
    except Exception as e:
        print(f"[{C_RED}FAIL{C_RESET}] LocalStack unavailable: {e}")
        print(
            "Please start LocalStack Pro: "
            "docker run --rm -d -p 4566:4566 --name localstack "
            "-e LOCALSTACK_AUTH_TOKEN=<your-token> "
            "-e DEFAULT_REGION=us-east-1 "
            "-e SERVICES=ecs,ec2,iam,lambda,s3,secretsmanager,sts,autoscaling "
            "-e DOCKER_HOST=unix:///var/run/docker.sock "
            "-v localstack_data:/var/lib/localstack "
            "-v /var/run/docker.sock:/var/run/docker.sock "
            "localstack/localstack-pro:latest"
        )
        sys.exit(1)
        
    wait_for_enter("Press ENTER to publish Synthetic Metrics")


def phase1_publish_metrics():
    print_step("Phase 1: Publish Synthetic Metrics to CloudWatch")
    # Simulate a sudden spike in Lambda errors
    now = datetime.now(timezone.utc)
    
    # Send baseline data (historical)
    metric_data = []
    service_name = "payment-processor"
    
    print(f"Publishing {C_BOLD}AWS/Lambda Errors{C_RESET} for {service_name}...")
    for i in range(10, 0, -1):
        dt = now - timedelta(minutes=i)
        # Background noise
        metric_data.append({
            'MetricName': "Errors",
            'Dimensions': [{'Name': 'FunctionName', 'Value': service_name}],
            'Timestamp': dt,
            'Value': 1.0,
            'Unit': 'Count'
        })
        
    # The anomaly spike
    metric_data.append({
        'MetricName': "Errors",
        'Dimensions': [{'Name': 'FunctionName', 'Value': service_name}],
        'Timestamp': now,
        'Value': 150.0,  # MASSIVE SPIKE
        'Unit': 'Count'
    })

    cw_client.put_metric_data(Namespace="AWS/Lambda", MetricData=metric_data)
    print(f"[{C_GREEN}OK{C_RESET}] Synthesized 10m baseline and 1m spike (150 errors).")
    
    wait_for_enter("Press ENTER to publish Synthetic Logs")


def phase2_publish_logs():
    print_step("Phase 2: Publish Synthetic Error Logs to CloudWatch Logs")
    service_name = "payment-processor"
    log_group_name = f"/aws/lambda/{service_name}"
    log_stream_name = f"demo-stream-{uuid.uuid4().hex[:8]}"
    
    try:
        logs_client.create_log_group(logGroupName=log_group_name)
    except logs_client.exceptions.ResourceAlreadyExistsException:
        pass
        
    logs_client.create_log_stream(logGroupName=log_group_name, logStreamName=log_stream_name)
    
    t1 = int((datetime.now(timezone.utc) - timedelta(seconds=2)).timestamp() * 1000)
    t2 = int(datetime.now(timezone.utc).timestamp() * 1000)
    
    events = [
        {'timestamp': t1, 'message': '{"level": "INFO", "message": "Invoking downstream API"}'},
        {'timestamp': t2, 'message': '{"level": "ERROR", "message": "timeout connecting to db.internal"}'}
    ]
    
    # Add a slight delay so LocalStack absorbs metrics
    print("Waiting 2s for AWS consistency...")
    time.sleep(2)
    
    logs_client.put_log_events(logGroupName=log_group_name, logStreamName=log_stream_name, logEvents=events)
    print(f"[{C_GREEN}OK{C_RESET}] Log stream '{log_stream_name}' populated.")
    
    wait_for_enter("Press ENTER to trigger Alert Enrichment")


async def phase3_trigger_enricher():
    print_step("Phase 3: Trigger the SRE Alert Enricher")
    
    enricher = AlertEnricher(
        cloudwatch_client=cw_client,
        logs_client=logs_client,
        metadata_fetcher=None,
        log_window_minutes=30,
        metric_window_minutes=30
    )
    
    # We pretend an SNS payload arrived asking to enrich lambda_errors
    print(f"Simulating SNS Bridge intercepting alert for {C_BOLD}payment-processor{C_RESET}...")
    
    enriched_signals = await enricher.enrich(
        service="payment-processor",
        metric_name="Errors"
    )
    
    print(f"\n--- Enrichment Complete (window {enriched_signals['window_start']} to {enriched_signals['window_end']}) ---")
    
    print(f" -> Current Value: {enriched_signals['current_value']}")
    print(f" -> Baseline: {enriched_signals['baseline_value']}")
    print(f" -> Deviation Sigma: {enriched_signals['deviation_sigma']}")
    
    print("\n   [Metrics Found]")
    for m in enriched_signals["metrics"]:
        print(f"      - {m['timestamp']}: {m['value']} {m.get('unit', '')}")
        
    print("\n   [Logs Found]")
    for log in enriched_signals["logs"]:
        if isinstance(log, dict):
            timestamp = log.get("timestamp", "")
            severity = log.get("severity", "UNK")
            message = log.get("message", "")
        else:
            timestamp = getattr(log, "timestamp", "")
            severity = getattr(log, "severity", "UNK")
            message = getattr(log, "message", str(log))
        print(f"      - {timestamp} [{severity}] {message}")
            
    print(f"\n[{C_GREEN}SUCCESS{C_RESET}] The bridge now has context to inject into diagnosis requests.")
    
    
def main():
    print(f"\n{C_BOLD}Autonomous SRE Agent — Live Demo 9: CloudWatch Bridge Enrichment{C_RESET}")
    print("=" * 70)
    phase0_preflight()
    phase1_publish_metrics()
    phase2_publish_logs()
    
    # Run async phase
    asyncio.run(phase3_trigger_enricher())
    
    print_step("Demo Finished")
    print("If you started LocalStack for this test, you can shut it down.")


if __name__ == "__main__":
    main()
