#!/usr/bin/env python3
"""
Autonomous SRE Agent — LIVE E2E Intelligence Layer Demo

This script runs a true End-to-End simulation of the Phase 2 Intelligence Layer.
It uses REAL models instead of mocks:
 - ChromaDB (In-memory Vector DB)
 - Sentence-Transformers (Local embedding generation)
 - OpenAI or Anthropic (Live LLM API calls)

REQUIREMENTS:
 - You must have `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` exposed in your environment.
 - `chromadb`, `sentence-transformers`, `openai`, `anthropic`, and `tiktoken` must be installed.

Usage:
    export OPENAI_API_KEY="sk-..."
    python scripts/live_e2e_demo.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from uuid import uuid4

# Setup standard formatting
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_step(title: str, text: str = "") -> None:
    print(f"\n{Colors.OKBLUE}{Colors.BOLD}▶ {title}{Colors.ENDC}")
    if text:
        print(f"  {text}")

def print_result(title: str, text: str) -> None:
    print(f"  {Colors.OKGREEN}✔ {title}:{Colors.ENDC} {text}")

def print_warning(title: str, text: str) -> None:
    print(f"  {Colors.WARNING}⚠ {title}:{Colors.ENDC} {text}")

# Ensure we have API keys
if not os.environ.get("OPENAI_API_KEY") and not os.environ.get("ANTHROPIC_API_KEY"):
    print(f"\n{Colors.FAIL}Error: No LLM API Key found!{Colors.ENDC}")
    print("Please expose your key in the terminal before running the live demo:")
    print("  export OPENAI_API_KEY='sk-...'")
    print("  OR")
    print("  export ANTHROPIC_API_KEY='sk-ant-...'")
    sys.exit(1)

try:
    from sre_agent.domain.models.canonical import AnomalyAlert, AnomalyType, ComputeMechanism
    from sre_agent.domain.models.diagnosis import ServiceTier
    from sre_agent.ports.diagnostics import DiagnosisRequest
    from sre_agent.adapters.intelligence_bootstrap import (
        create_diagnostic_pipeline,
        create_ingestion_pipeline,
        create_vector_store,
        create_embedding,
        create_llm
    )
    from sre_agent.events.in_memory import InMemoryEventBus, InMemoryEventStore
except ImportError as e:
    print(f"{Colors.FAIL}Error importing modules: {e}{Colors.ENDC}")
    print("Please make sure you are in the virtual environment and have installed the 'intelligence' dependencies.")
    sys.exit(1)


async def run_demo():
    print(f"\n{Colors.HEADER}================================================================{Colors.ENDC}")
    print(f"{Colors.HEADER}    Autonomous SRE Agent — LIVE E2E Intelligence Layer Demo     {Colors.ENDC}")
    print(f"{Colors.HEADER}================================================================{Colors.ENDC}\n")

    # 1. Boot Pipelines
    print_step("Phase 0: Bootstrapping Live Adapters", "Initializing ChromaDB, Sentence-Transformers, and LLM APIs...")
    start_time = time.time()
    
    # We use explicit memory instances to avoid disk-locking collisions across runs
    vs = create_vector_store(collection_name="demo_kb")
    emb = create_embedding()
    llm = create_llm()
    
    ingestion = create_ingestion_pipeline(vector_store=vs, embedding=emb)
    pipeline = create_diagnostic_pipeline(
        vector_store=vs,
        embedding=emb,
        llm=llm,
        service_tiers={"nginx-gateway": ServiceTier.TIER_1},
        context_budget=4000
    )
    
    # Wire the event buses
    pipeline._event_bus = InMemoryEventBus()
    pipeline._event_store = InMemoryEventStore()

    boot_time = time.time() - start_time
    print_result("Adapters Connected", f"Loaded in {boot_time:.2f}s")

    # 2. Ingest Sample Runbooks (Live RAG)
    print_step("Phase 1: Knowledge Base Ingestion", "Embedding and storing actual incident post-mortems...")
    documents = [
        (
            """# Post-Mortem: Nginx 502 Bad Gateway Spikes
            Date: 2026-01-15
            Service: nginx-gateway
            
            **Symptom**: We saw a massive spike in 502 Bad Gateway errors on the nginx-gateway service, correlating with high CPU usage on the upstream backend-api service.
            
            **Root Cause**: The upstream API servers were becoming overwhelmed and crashing due to a connection pool exhaustion bug, causing Nginx to drop connections.
            
            **Remediation Action**: We had to immediately scale up the backend-api replicas from 5 to 20 to handle the thundering herd, and gently restart the nginx-gateway pods to clear stale worker connections.
            """,
            "post-mortems/incident-nginx-502.md",
            None
        ),
        (
            """# Runbook: DB Connection Latency
            Service: postgres-primary
            
            When DB connections exceed 500ms, it is usually a missing index issue or a transaction lock timeout. Check pg_stat_activity. Do NOT restart the primary DB automatically.
            """,
            "runbooks/database-latency.md",
            None
        )
    ]
    await ingestion.ingest_batch(documents)
    print_result("Ingestion Complete", f"Successfully vectorized and stored {len(documents)} documents.")

    # 3. Simulate Anomaly
    print_step("Phase 2: Anomaly Detected", "Observability layer flags an issue in a production system.")
    alert = AnomalyAlert(
        alert_id=uuid4(),
        service="nginx-gateway",
        anomaly_type=AnomalyType.ERROR_RATE_SURGE,
        description="Massive spike in 502 Bad Gateway HTTP codes.",
        metric_name="http_5xx_error_rate",
        current_value=150.0,  # 150 errors / sec
        baseline_value=2.0,
        deviation_sigma=12.5,
        compute_mechanism=ComputeMechanism.KUBERNETES
    )
    print_result("Service", f"{Colors.BOLD}{alert.service} (Tier 1){Colors.ENDC}")
    print_result("Metric", f"{alert.metric_name}")
    print_result("Deviation", f"+{alert.deviation_sigma}σ (Spiked to {alert.current_value} eps)")

    # 4. Run Diagnosic Pipeline LIVE
    print_step("Phase 3: Live RAG Diagnostic Execution", "Querying Vector DB and invoking LLM API live... (This may take 5-10 seconds depending on API latency)")
    request = DiagnosisRequest(alert=alert, max_evidence_items=3)
    
    diag_start = time.time()
    result = await pipeline.diagnose(request)
    diag_time = time.time() - diag_start

    print_result("Live Pipeline Complete", f"Finished in {diag_time:.2f}s")

    # Output the final payload
    print(f"\n{Colors.HEADER}================================================================{Colors.ENDC}")
    print(f"{Colors.HEADER}         DIAGNOSIS RESULT & RECOMMENDED ACTION                  {Colors.ENDC}")
    print(f"{Colors.HEADER}================================================================{Colors.ENDC}\n")

    print(f"{Colors.BOLD}Assigned Severity:{Colors.ENDC}       {Colors.FAIL if result.severity.name in ('SEV1', 'SEV2') else Colors.WARNING}{result.severity.name}{Colors.ENDC}")
    print(f"{Colors.BOLD}Confidence Score:{Colors.ENDC}        {Colors.OKGREEN}{result.confidence * 100:.1f}%{Colors.ENDC}")
    
    # --- Root Cause ---
    root_cause = result.root_cause or "(not determined)"
    print(f"\n{Colors.BOLD}Live LLM Root Cause Assessment:{Colors.ENDC}")
    print(f"  {Colors.OKCYAN}{root_cause}{Colors.ENDC}")

    # --- Reasoning (adapter normalises list → numbered string) ---
    reasoning = result.reasoning or "(no reasoning provided)"
    print(f"\n{Colors.BOLD}Live LLM Diagnostic Reasoning:{Colors.ENDC}")
    for line in reasoning.splitlines():
        print(f"  {line}")

    # --- Evidence citations ---
    print(f"\n{Colors.BOLD}Vector DB Evidence Provenance (KB citations):{Colors.ENDC}")
    if result.evidence_citations:
        for idx, ref in enumerate(result.evidence_citations):
            print(f"  [{idx+1}] {Colors.OKCYAN}{ref}{Colors.ENDC}")
    else:
        print(f"  {Colors.WARNING}(no citations returned){Colors.ENDC}")

    # --- Remediation ---
    remediation = result.suggested_remediation or "(none provided — raise severity manually)"
    print(f"\n{Colors.BOLD}Live LLM Recommended Remediation:{Colors.ENDC}")
    for line in remediation.splitlines():
        print(f"  {Colors.OKGREEN}{line}{Colors.ENDC}")

    print("\n")
    if result.requires_human_approval:
        print_warning("Execution Guardrail", "Action halted. Incident requires Human-in-the-Loop Override Approval to proceed to auto-remediation.")
    else:
        print_result("Execution Guardrail", "Authorized for Autonomous Phase 3 Remediation execution.")

    # Show the tokens used
    usage = llm.get_token_usage()
    print(f"\n{Colors.OKBLUE}Token Usage: {usage.prompt_tokens} prompt / {usage.completion_tokens} completion / {usage.total_tokens} total{Colors.ENDC}")
    print(f"{Colors.HEADER}================================================================{Colors.ENDC}\n")

if __name__ == "__main__":
    try:
        asyncio.run(run_demo())
    except KeyboardInterrupt:
        print("\nDemo interrupted. Exiting.")
        sys.exit(0)
