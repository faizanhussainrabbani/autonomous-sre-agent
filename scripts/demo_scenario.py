#!/usr/bin/env python3
"""
Autonomous SRE Agent — Phase 2 Intelligence Layer Interactive Demo

This script simulates an anomaly detection event and runs it through the
Intelligence Layer's RAG diagnostic pipeline. It leverages beautiful console
output to demonstrate the agent's capability to embed alerts, search historical
knowledge bases, reason about root causes using LLMs, validate against secondary
opinions, and deterministically assign severity.

Usage:
    python scripts/demo_scenario.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from unittest.mock import AsyncMock, MagicMock
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
    time.sleep(1.2)  # Artificial delay for dramatic presentation effect

def print_result(title: str, text: str) -> None:
    print(f"  {Colors.OKGREEN}✔ {title}:{Colors.ENDC} {text}")
    time.sleep(0.8)

def print_warning(title: str, text: str) -> None:
    print(f"  {Colors.WARNING}⚠ {title}:{Colors.ENDC} {text}")
    time.sleep(0.8)

try:
    from sre_agent.domain.diagnostics.rag_pipeline import RAGDiagnosticPipeline
    from sre_agent.domain.diagnostics.severity import SeverityClassifier
    from sre_agent.domain.models.canonical import AnomalyAlert, AnomalyType, ComputeMechanism
    from sre_agent.domain.models.diagnosis import ServiceTier
    from sre_agent.ports.diagnostics import DiagnosisRequest
    from sre_agent.ports.llm import Hypothesis, TokenUsage, ValidationResult
    from sre_agent.ports.vector_store import SearchResult
    from sre_agent.events.in_memory import InMemoryEventBus, InMemoryEventStore
    from sre_agent.adapters.llm.throttled_adapter import ThrottledLLMAdapter
except ImportError:
    print(f"{Colors.FAIL}Error: SRE Agent library not found. Please run this script from the project root using `python -m scripts.demo_scenario` or ensure the src path is in PYTHONPATH.{Colors.ENDC}")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Demo Mocks (Ensures 100% reliable demo without needing API keys)
# ---------------------------------------------------------------------------

def _create_mock_llm():
    """Mock LLM to simulate reasoning reliably."""
    inner = MagicMock()
    
    async def _generate(request):
        await asyncio.sleep(2.0)  # Simulate API latency
        return Hypothesis(
            root_cause="Instance memory leak inside 'payment-service' caused by unbounded cache scaling during heavy traffic.",
            confidence=0.92,
            reasoning="The container_memory_rss_bytes metric breached the 1.5GB baseline significantly, reaching 3.8GB. Correlated metrics show gradual memory growth consistent with an unbounded cache over the last 12 hours. Historical post-mortem (doc-0) notes an identical pattern during the Q4 load test.",
            evidence_citations=["runbook/payment-oom.md"],
            suggested_remediation="Safe auto-remediation: 1) Initiate rolling pod restart on payment-service to clear memory. 2) Scale up HPA max replicas to handle traffic shift."
        )

    async def _validate(request):
        await asyncio.sleep(1.0) # Simulate Validation API latency
        return ValidationResult(
            agrees=True,
            confidence=0.90,
            reasoning="The diagnosis is logically sound and directly supported by retrieved historical evidence. Scaling and restarting is a safe and reversible action.",
            contradictions=[],
        )

    inner.generate_hypothesis = _generate
    inner.validate_hypothesis = _validate
    inner.health_check = AsyncMock(return_value=True)
    inner.count_tokens = MagicMock(side_effect=lambda text: len(text) // 4)
    inner.get_token_usage = MagicMock(return_value=TokenUsage(prompt_tokens=400, completion_tokens=150))
    return inner

def _create_mock_pipeline() -> RAGDiagnosticPipeline:
    results = [
        SearchResult(
            doc_id="doc-0",
            content="Post-mortem #442: Payment Service OOM Kills. Root cause was unbounded in-memory cache accumulating stale sessions. Remediation: pod restart clears the state safely.",
            score=0.91,
            source="post-mortem/incident-442.md",
        ),
        SearchResult(
            doc_id="doc-1",
            content="Runbook: payment-service scaling. If memory reaches >90%, initiate safe rolling restart.",
            score=0.88,
            source="runbook/payment-oom.md",
        )
    ]

    mock_vs = MagicMock()
    mock_vs.search = AsyncMock(return_value=results)
    mock_vs.health_check = AsyncMock(return_value=True)

    mock_emb = MagicMock()
    mock_emb.embed_text = AsyncMock(return_value=[0.1] * 384)
    mock_emb.health_check = AsyncMock(return_value=True)

    classifier = SeverityClassifier(
        service_tiers={"payment-service": ServiceTier.TIER_1},
    )

    llm = ThrottledLLMAdapter(_create_mock_llm(), max_concurrent=10)

    return RAGDiagnosticPipeline(
        vector_store=mock_vs,
        embedding=mock_emb,
        llm=llm,
        severity_classifier=classifier,
        event_bus=InMemoryEventBus(),
        event_store=InMemoryEventStore(),
    )


async def run_demo():
    print(f"\n{Colors.HEADER}================================================================{Colors.ENDC}")
    print(f"{Colors.HEADER}         Autonomous SRE Agent — Intelligence Demo               {Colors.ENDC}")
    print(f"{Colors.HEADER}================================================================{Colors.ENDC}\n")

    time.sleep(1)

    # 1. Simulate Anomaly
    print_step("Phase 1: Anomaly Detected", "Observability layer flags an issue in a production system.")
    alert = AnomalyAlert(
        alert_id=uuid4(),
        service="payment-service",
        anomaly_type=AnomalyType.MEMORY_PRESSURE,
        description="OOM kill risk — container memory limit exceeded constraints.",
        metric_name="container_memory_rss_bytes",
        current_value=3.8e9,
        baseline_value=1.5e9,
        deviation_sigma=5.2,
        compute_mechanism=ComputeMechanism.KUBERNETES
    )
    print_result("Service", f"{Colors.BOLD}payment-service (Tier 1){Colors.ENDC}")
    print_result("Metric", f"container_memory_rss_bytes")
    print_result("Deviation", f"+5.2σ (Spiked to 3.8GB)")

    # 2. Boot Pipeline
    print_step("Bootstrapping Intelligence Layer", "Wiring Vector DB, Embedding Models, and LLM Ports (Throttled)...")
    pipeline = _create_mock_pipeline()
    request = DiagnosisRequest(alert=alert, max_evidence_items=3)

    print_step("Phase 2: Executing Diagnostic Pipeline", "Agent is now taking control...")

    # We manually simulate the output of the steps internally for visual effect before the pipeline actually finishes in the background
    
    # Embedding & Retrieval
    print_step("2a. Context Retrieval", "Embedding alert data and querying historical knowledge base (RAG)...")
    time.sleep(1.5)
    print_result("Search", "Found matching Runbook (score: 0.88) and Post-mortem (score: 0.91)")

    # LLM Reasoning
    print_step("2b. LLM Reasoning", "Synthesizing alert telemetry with retrieved organizational knowledge...")
    
    # We await the actual pipeline now (takes ~3s due to API latency mocks)
    result = await pipeline.diagnose(request)

    print_result("Hypothesis Generation", "Complete. Diagnosis built.")

    # Validation
    print_step("2c. Second-Opinion Validation", "Cross-checking the hypothesis against safety constraints and logic...")
    time.sleep(0.5)
    print_result("Validation", f"Passed (Confidence: {result.confidence * 100:.1f}%)")

    # Severity Classification
    print_step("2d. Multi-Dimensional Severity Classification", "Evaluating Blast Radius, Reversibility, and Tier impact...")
    
    # Output the final payload
    print(f"\n{Colors.HEADER}================================================================{Colors.ENDC}")
    print(f"{Colors.HEADER}         DIAGNOSIS RESULT & RECOMMENDED ACTION                  {Colors.ENDC}")
    print(f"{Colors.HEADER}================================================================{Colors.ENDC}\n")

    print(f"{Colors.BOLD}Assigned Severity:{Colors.ENDC}       {Colors.FAIL if result.severity.name in ('SEV1', 'SEV2') else Colors.WARNING}{result.severity.name}{Colors.ENDC}")
    print(f"{Colors.BOLD}Confidence Score:{Colors.ENDC}        {Colors.OKGREEN}{result.confidence * 100:.1f}%{Colors.ENDC}")
    print(f"{Colors.BOLD}Algorithm Assessment:{Colors.ENDC}    {result.root_cause}")
    
    print(f"\n{Colors.BOLD}Diagnostic Reasoning:{Colors.ENDC}")
    print(f"  {result.reasoning}")

    print(f"\n{Colors.BOLD}Evidence Provenance (KB citations):{Colors.ENDC}")
    for idx, ref in enumerate(result.evidence_citations):
        print(f"  [{idx+1}] {Colors.OKCYAN}{ref}{Colors.ENDC}")

    print(f"\n{Colors.BOLD}Recommended Remediation:{Colors.ENDC}")
    print(f"  {Colors.OKGREEN}{result.suggested_remediation}{Colors.ENDC}")

    print("\n")
    if result.requires_human_approval:
        print_warning("Execution Guardrail", "Action halted. Tier 1 Sev 1 incidents require Human-in-the-Loop Override Approval to proceed to auto-remediation (Phase 3).")
    else:
        print_result("Execution Guardrail", "Authorized for Autonomous Phase 3 Remediation execution.")

    print(f"\n{Colors.HEADER}================================================================{Colors.ENDC}\n")

if __name__ == "__main__":
    try:
        asyncio.run(run_demo())
    except KeyboardInterrupt:
        print("\nDemo interrupted. Exiting.")
        sys.exit(0)
