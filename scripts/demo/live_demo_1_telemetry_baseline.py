#!/usr/bin/env python3
"""
Demo 1: Telemetry Baseline (Phase 1)
Proves that the system can fetch foundational raw metrics from CloudWatch (via LocalStack)
and parse them into CanonicalMetric structs used by all upstream anomaly detection layers.

Architecture Validated: Adapters (CloudWatchMetricsAdapter) -> Domain (CanonicalMetric)
"""

import sys
import time
import asyncio
from datetime import datetime, timedelta, timezone

import structlog
import boto3
from _demo_utils import aws_region, boto_localstack_kwargs

from sre_agent.adapters.telemetry.cloudwatch.metrics_adapter import CloudWatchMetricsAdapter
from sre_agent.domain.models.canonical import CanonicalMetric

logger = structlog.get_logger()

# Setup LocalStack connectivity matching existing scripts
AWS_REGION = aws_region("us-east-1")
ENDPOINT_URL = "http://localhost:4566"
NAMESPACE = "ECS/ContainerInsights"

def push_test_metrics(cw_client):
    """Push 5 minutes of historical CPU Utilization datums."""
    logger.info("Pushing baseline mock metrics to LocalStack CloudWatch", namespace=NAMESPACE)
    now = datetime.now(timezone.utc)
    
    for i in range(5, 0, -1):
        dt = now - timedelta(minutes=i)
        # Synthetic sine wave-like load: 30, 45, 55, 60, 40
        values = [30.0, 45.0, 55.0, 60.0, 40.0]
        val = values[5 - i]
        
        cw_client.put_metric_data(
            Namespace=NAMESPACE,
            MetricData=[
                {
                    'MetricName': 'CpuUtilized',
                    'Dimensions': [{'Name': 'ServiceName', 'Value': 'baseline-service'}],
                    'Timestamp': dt,
                    'Value': val,
                    'Unit': 'Percent'
                }
            ]
        )
    logger.info("Pushed 5 metric datums for CpuUtilized.")

async def main():
    logger.info("Starting Demo 1: Phase 1 Telemetry Baseline")
    
    # 1. Initialize boto3 client pointing to LocalStack
    cw_client = boto3.client("cloudwatch", **boto_localstack_kwargs(ENDPOINT_URL, AWS_REGION))
    
    # 2. Push some synthetic metrics
    push_test_metrics(cw_client)
    
    # LocalStack needs a split second sometimes to index metrics
    time.sleep(1)

    # 3. Initialize the Adapter
    adapter = CloudWatchMetricsAdapter(cloudwatch_client=cw_client)
    
    # 4. Fetch the metrics into Canonical representations
    logger.info("Fetching metrics via SRE Agent CloudWatchMetricsAdapter")
    
    try:
        results = await adapter.query(
            service="baseline-service",
            metric="ecs_cpu_utilization",
            start_time=datetime.now(timezone.utc) - timedelta(minutes=10),
            end_time=datetime.now(timezone.utc)
        )
        logger.info("Successfully retrieved metrics", count=len(results))
        for res in results:
            if isinstance(res, CanonicalMetric):
                logger.debug("Canonical Metric parsed", 
                             timestamp=res.timestamp, 
                             name=res.name,
                             value=res.value,
                             unit=res.unit)
        
        if len(results) > 0:
            logger.info("✅ AC 1.1-1.3 Passed: Baseline Telemetry properly converted to Domain Canonical objects.")
        else:
            logger.error("❌ AC Failed: No metrics returned. Note that LocalStack CW can sometimes be slow to flush.")
            sys.exit(1)
            
    except Exception as e:
        logger.error("Simulation failed unexpectedly", error=str(e))
        sys.exit(1)

if __name__ == "__main__":
    structlog.configure(
        processors=[structlog.dev.ConsoleRenderer(colors=True)]
    )
    asyncio.run(main())
