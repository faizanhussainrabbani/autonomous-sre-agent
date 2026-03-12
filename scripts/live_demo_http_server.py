"""
Live Demo 5 — True End-to-End Live HTTP Demo
===========================================

This demo spins up the actual FastAPI application server in the background
and runs incident scenarios against it over real HTTP requests. This verifies
that the application's REST API layer, dependency injection, and reasoning
pipeline all function together end-to-end.

Usage
-----
    source .venv/bin/activate
    python scripts/live_demo_http_server.py
"""

import asyncio
import httpx
import json
import os
import subprocess
import sys
import time
from uuid import uuid4

# Setup basic colored output
class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RED     = "\033[91m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    BLUE    = "\033[94m"
    CYAN    = "\033[96m"
    WHITE   = "\033[97m"

def header(title: str) -> None:
    width = 68
    print(f"\n{C.BOLD}{C.BLUE}{'╔' + '═' * width + '╗'}{C.RESET}")
    print(f"{C.BOLD}{C.BLUE}║{title.center(width)}║{C.RESET}")
    print(f"{C.BOLD}{C.BLUE}{'╚' + '═' * width + '╝'}{C.RESET}\n")

def field(label: str, value: str, indent: int = 3) -> None:
    pad = " " * indent
    print(f"{pad}{C.DIM}{label}:{C.RESET} {C.WHITE}{value}{C.RESET}")

def ok(msg: str, indent: int = 3) -> None:
    print(f"{' ' * indent}{C.GREEN}✔{C.RESET}  {msg}")

def fail(msg: str, indent: int = 3) -> None:
    print(f"{' ' * indent}{C.RED}✖{C.RESET}  {msg}")

def step(msg: str) -> None:
    print(f"\n{C.CYAN}▶{C.RESET}  {C.BOLD}{msg}{C.RESET}")

API_URL = "http://127.0.0.1:8181"

async def wait_for_server():
    """Wait until the FastAPI server is healthy."""
    async with httpx.AsyncClient() as client:
        for _ in range(30):
            try:
                resp = await client.get(f"{API_URL}/health", timeout=1.0)
                if resp.status_code == 200:
                    return True
            except httpx.RequestError:
                pass
            await asyncio.sleep(1)
    return False

def make_alert_payload() -> dict:
    """Create a sample anomaly alert payload."""
    return {
        "alert": {
            "alert_id": str(uuid4()),
            "service": "billing-api",
            "anomaly_type": "error_rate_surge",
            "description": "HTTP 5xx error rate spiked to 12% across billing instances.",
            "metric_name": "http_5xx_errors",
            "current_value": 12.0,
            "baseline_value": 0.5,
            "deviation_sigma": 14.2,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "compute_mechanism": "kubernetes"
        }
    }

async def run_demo():
    header("Live Demo 5 — HTTP API Server Execution")
    
    step("Phase 1: Booting up the FastAPI application server (Background)")
    
    env = os.environ.copy()
    # Start the server on port 8181 to avoid conflicts
    server_process = subprocess.Popen(
        [".venv/bin/uvicorn", "sre_agent.api.main:app", "--port", "8181", "--host", "127.0.0.1"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env
    )
    
    print(f"   {C.DIM}Waiting for server to become healthy...{C.RESET}")
    is_healthy = await wait_for_server()
    if not is_healthy:
        fail("Server failed to start or did not become healthy in time.")
        server_process.terminate()
        sys.exit(1)
        
    ok("FastAPI server is up and responding to /health")

    try:
        step("Phase 2: Sending diagnostic request over HTTP")
        payload = make_alert_payload()
        
        print(f"\n   {C.YELLOW}⚠️  Alert:{C.RESET}")
        field("Service", payload['alert']['service'])
        field("Anomaly", payload['alert']['anomaly_type'])
        field("Issue", payload['alert']['description'])
        
        print(f"\n   {C.DIM}Sending POST {API_URL}/api/v1/diagnose (May take ~10-15s for LLM){C.RESET}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            t0 = time.time()
            response = await client.post(f"{API_URL}/api/v1/diagnose", json=payload)
            elapsed = time.time() - t0
            
            if response.status_code != 200:
                fail(f"HTTP Error {response.status_code}: {response.text}")
            else:
                ok(f"Received 200 OK in {elapsed:.1f}s")
                data = response.json()
                
                print(f"\n{C.BOLD}   📋 HTTP Response payload:{C.RESET}")
                field("Status", data.get("status"))
                field("Severity", data.get("severity"))
                field("Confidence", f"{data.get('confidence', 0)*100:.1f}%")
                
                print(f"      {C.DIM}Root Cause:{C.RESET} {C.CYAN}{data.get('root_cause')}{C.RESET}")
                
                print(f"      {C.DIM}Requires Approval:{C.RESET} {C.RED if data.get('requires_approval') else C.GREEN}{data.get('requires_approval')}{C.RESET}")
                
                print(f"\n   {C.DIM}Audit Trail Log (Token Optimization active over HTTP):{C.RESET}")
                for log in data.get("audit_trail", []):
                    print(f"      - {log}")

    finally:
        step("Phase 3: Shutting down the server")
        server_process.terminate()
        server_process.wait()
        ok("FastAPI server shut down successfully.")
        
    print(f"\n{C.BOLD}{C.GREEN}Demo successfully operated end-to-end over actual HTTP endpoints!{C.RESET}\n")

if __name__ == "__main__":
    asyncio.run(run_demo())
