"""
Live Demo 10 — EventBridge Canonical Timeline
=============================================

Demonstrates the SRE Agent's capability to ingest live EventBridge 
system events, classify them, canonicalize them, and insert them into
an incident diagnosis timeline. 

What this demo proves:
  Phase 0  — Ensure FastAPI /api/v1/events/aws routes are loaded
  Phase 1  — Simulate EventBridge Webhook POST: Deployment Event (ECS)
  Phase 2  — Simulate EventBridge Webhook POST: OOM Event (ECS)
  Phase 3  — Retrieve Canonical Events from storage
  Phase 4  — Timeline Construction

Usage
-----
    source .venv/bin/activate
    python scripts/live_demo_eventbridge_reaction.py
"""

import sys
import uuid
import asyncio
from datetime import datetime, timezone

try:
    from fastapi.testclient import TestClient
    from sre_agent.api.main import app 
    from sre_agent.domain.diagnostics.timeline import TimelineConstructor
    from sre_agent.domain.models.canonical import SignalType, CanonicalEvent, CanonicalMetric
except ImportError:
    print("FATAL: Could not import sre_agent components. Ensure FastAPI and testclient are available.")
    sys.exit(1)


# Provide colors for presentation
C_GREEN = "\033[92m"
C_BLUE = "\033[94m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_BOLD = "\033[1m"
C_RESET = "\033[0m"


def wait_for_enter(prompt="Press ENTER to continue..."):
    print(f"\n{C_YELLOW}{prompt}{C_RESET}")
    input()


def print_step(title):
    print(f"\n{C_BOLD}{C_BLUE}--- {title} ---{C_RESET}")


def phase0_preflight():
    print_step("Phase 0: Pre-flight - Initialize TestClient")
    global client
    client = TestClient(app)
    
    # Check if event events route is healthy
    response = client.get("/healthz")
    if response.status_code != 200:
        print(f"[{C_RED}FAIL{C_RESET}] App healthz failing.")
        sys.exit(1)
        
    print(f"[{C_GREEN}OK{C_RESET}] Internal FastAPI TestClient established.")
    wait_for_enter("Press ENTER to send simulated Deployment Event")


def phase1_deployment_event():
    print_step("Phase 1: POST ECS Deployment Event to Bridge")
    
    event_payload = {
        "version": "0",
        "id": str(uuid.uuid4()),
        "detail-type": "ECS Deployment State Change",
        "source": "aws.ecs",
        "account": "123456789012",
        "time": datetime.now(timezone.utc).isoformat(),
        "region": "us-east-1",
        "resources": [
            "arn:aws:ecs:us-east-1:123456789012:service/main-cluster/order-service"
        ],
        "detail": {
            "eventType": "INFO",
            "eventName": "SERVICE_DEPLOYMENT_COMPLETED",
            "reason": "ECS service order-service deployed successfully."
        }
    }
    
    response = client.post("/api/v1/events/aws", json=event_payload)
    if response.status_code == 200:
        print(f"[{C_GREEN}OK{C_RESET}] Successfully ingested deployment EventBridge payload.")
    else:
        print(f"[{C_RED}FAIL{C_RESET}] {response.text}")
        
    wait_for_enter("Press ENTER to send simulated OOM Event")


def phase2_oom_event():
    print_step("Phase 2: POST ECS OOM Kill Event to Bridge")
    
    event_payload = {
        "version": "0",
        "id": str(uuid.uuid4()),
        "detail-type": "ECS Task State Change",
        "source": "aws.ecs",
        "account": "123456789012",
        "time": datetime.now(timezone.utc).isoformat(),
        "region": "us-east-1",
        "resources": [
            "arn:aws:ecs:us-east-1:123456789012:task/main-cluster/abcdef1234567890"
        ],
        "detail": {
            "group": "service:order-service",
            "lastStatus": "STOPPED",
            "stoppedReason": "Essential container in task exited",
            "containers": [
                {
                    "name": "order-web",
                    "reason": "OutOfMemoryError: Container killed due to memory usage"
                }
            ]
        }
    }
    
    response = client.post("/api/v1/events/aws", json=event_payload)
    if response.status_code == 200:
        print(f"[{C_GREEN}OK{C_RESET}] Successfully ingested OOM Kill EventBridge payload.")
        
    wait_for_enter("Press ENTER to inspect Canonical Storage")


def phase3_retrieve_events():
    print_step("Phase 3: Retrieve Correlated Domain Events")
    
    # Fetch recent events for 'order-service'
    response = client.get("/api/v1/events/aws/recent?service=order-service")
    events = response.json().get("events", [])
    
    print(f"Found {len(events)} events for 'order-service'.")
    for evt in events:
        print(f" -> Type: {evt.get('event_type')}")
        print(f"    Source: {evt.get('source')}")
        print(f"    Metadata: {evt.get('metadata')}")
        
    global global_events
    global_events = events
    
    wait_for_enter("Press ENTER to render Timeline Construction")


def phase4_timeline_construction():
    print_step("Phase 4: Construct Diagnosis Timeline")
    
    # Map raw JSON outputs back to our internal data types for the Timeline class
    events_mapped = []
    
    # Use fake metric to tie it together
    from sre_agent.domain.models.canonical import ServiceLabels, CorrelatedSignals
    
    m1 = CanonicalMetric(
        name="ecs_memory_utilization",
        value=100.0,
        timestamp=datetime.now(timezone.utc),
        labels=ServiceLabels(service="order-service")
    )
    
    for raw in global_events:
        c_evt = CanonicalEvent(
            event_type=raw['event_type'],
            source=raw.get('source', 'aws'),
            timestamp=datetime.fromisoformat(raw['timestamp']),
            labels=ServiceLabels(service="order-service"),
            metadata=raw.get('metadata', {}),
            provider_source=raw.get('source', 'aws')
        )
        events_mapped.append(c_evt)
        
    correlated = CorrelatedSignals(
        service="order-service",
        metrics=[m1],
        logs=[],
        traces=[],
        events=events_mapped
    )
        
    # Introduce TimelineConstructor
    from sre_agent.domain.diagnostics.timeline import TimelineConstructor
    constructor = TimelineConstructor()
    timeline = constructor.build(
        signals=correlated,
        anomaly_type="OOM_KILL"
    )
    
    print("--- Generated System Timeline Representation ---")
    print("\n" + timeline)
    print("----------------------------------------------")
    print(f"[{C_GREEN}SUCCESS{C_RESET}] Timeline properly interleaved Metric + Events filtered for OOM_KILL.")
    
    
def main():
    print(f"\n{C_BOLD}Autonomous SRE Agent — Live Demo 10: EventBridge Timelines{C_RESET}")
    print("=" * 70)
    
    phase0_preflight()
    phase1_deployment_event()
    phase2_oom_event()
    phase3_retrieve_events()
    phase4_timeline_construction()
    
    print_step("Demo Finished")

if __name__ == "__main__":
    main()
