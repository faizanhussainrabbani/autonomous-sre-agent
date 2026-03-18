#!/usr/bin/env python3
"""
Live Demo 3 — Deployment Regression & Infrastructure Fragility.

Simulates an advanced scenario where a bad deployment triggers a chain of
infrastructure failures that expose pre-existing fragility:

  ┌─────────────────────────────────────────────────────────────────┐
  │  ACT 1 — Bad Canary Deployment (checkout-service v2.3.1)        │
  │    ✦ Error rate surges 15 minutes after deploy                  │
  │    ✦ LLM traces root cause to deployment commit                 │
  │    ✦ Second-opinion validator DISAGREES (confidence drops)      │
  │                                                                 │
  │  ACT 2 — Circuit Breaker Fragility Exposed                      │
  │    ✦ 5 consecutive cloud operator failures trip the breaker     │
  │    ✦ OPEN state rejects all remediation calls                   │
  │    ✦ Breaker recovers to HALF_OPEN after timeout                │
  │                                                                 │
  │  ACT 3 — Certificate Expiry Advisory                            │
  │    ✦ TLS cert for api-gateway expires in 6 hours                │
  │    ✦ Low-urgency advisory flagged for human review              │
  │    ✦ Agent surfaces runbook and recommended renewal action      │
  └─────────────────────────────────────────────────────────────────┘

This demo showcases:
  ✦ Deployment-induced incident diagnosis with metadata
  ✦ Validation disagreement → reduced composite confidence
  ✦ Circuit breaker state machine (CLOSED → OPEN → HALF_OPEN → CLOSED)
  ✦ OBS-009 Prometheus gauge for circuit breaker state
  ✦ Certificate expiry anomaly type (low-urgency advisory path)
  ✦ Confidence calibration transparency

REQUIREMENTS:
  - OPENAI_API_KEY or ANTHROPIC_API_KEY must be set in the environment.
  - chromadb, sentence-transformers, openai / anthropic, tiktoken installed.

Usage:
    export OPENAI_API_KEY="sk-..."
    python scripts/live_demo_deployment_regression.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from uuid import uuid4

# ---------------------------------------------------------------------------
# Terminal Styling
# ---------------------------------------------------------------------------

class C:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def banner(text: str, color: str = C.HEADER) -> None:
    width = 68
    bar = "═" * width
    print(f"\n{color}{C.BOLD}╔{bar}╗{C.RESET}")
    padding = " " * ((width - len(text)) // 2)
    r_pad = " " * (width - len(text) - len(padding))
    print(f"{color}{C.BOLD}║{padding}{text}{r_pad}║{C.RESET}")
    print(f"{color}{C.BOLD}╚{bar}╝{C.RESET}\n")


def section(icon: str, title: str, subtitle: str = "") -> None:
    print(f"\n{C.BLUE}{C.BOLD}{icon}  {title}{C.RESET}")
    if subtitle:
        print(f"   {C.DIM}{subtitle}{C.RESET}")


def field(label: str, value: str, ok: bool = True) -> None:
    icon = "✔" if ok else "⚠"
    color = C.GREEN if ok else C.YELLOW
    print(f"   {color}{icon}  {C.BOLD}{label}:{C.RESET} {value}")


def separator() -> None:
    print(f"   {C.DIM}{'─' * 62}{C.RESET}")


def state_badge(state_name: str) -> str:
    if state_name == "CLOSED":
        return f"{C.GREEN}{C.BOLD}CLOSED (healthy){C.RESET}"
    if state_name == "OPEN":
        return f"{C.RED}{C.BOLD}OPEN (failing — all calls rejected){C.RESET}"
    return f"{C.YELLOW}{C.BOLD}HALF_OPEN (probing — one test call allowed){C.RESET}"


# ---------------------------------------------------------------------------
# API Key validation
# ---------------------------------------------------------------------------

if not os.environ.get("OPENAI_API_KEY") and not os.environ.get("ANTHROPIC_API_KEY"):
    print(f"\n{C.RED}Error: No LLM API Key found in environment.{C.RESET}")
    print("Export your key before running:")
    print("  export OPENAI_API_KEY='sk-...'  OR  export ANTHROPIC_API_KEY='sk-ant-...'")
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
        create_llm,
    )
    from sre_agent.events.in_memory import InMemoryEventBus, InMemoryEventStore
    from sre_agent.adapters.cloud.resilience import (
        CircuitBreaker,
        CircuitOpenError,
        CircuitState,
        TransientError,
        retry_with_backoff,
        RetryConfig,
    )
    from sre_agent.adapters.telemetry.metrics import CIRCUIT_BREAKER_STATE
except ImportError as exc:
    print(f"{C.RED}Import error: {exc}{C.RESET}")
    print("Ensure you are running from the project root with the virtual environment active.")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Knowledge Base Documents
# ---------------------------------------------------------------------------

DEPLOYMENT_RUNBOOKS = [
    (
        """# Runbook: Deployment-Induced Error Rate Surge
Service: checkout-service
Trigger: Error rate > 3% within 15 minutes of a new deployment.

**Diagnosis Steps**:
  1. Check deployment timeline: `kubectl rollout history deployment/checkout-service`
  2. Compare error rate start time vs. deployment start time.
  3. Inspect the canary pod logs for the new version: `kubectl logs -l version=canary`
  4. Check for serialization regressions or removed API endpoints.

**Remediation**:
  a) If error rate < 10%: Monitor for 5 minutes; if worsening, rollback.
  b) If error rate 10-30%: Immediate rollback: `kubectl rollout undo deployment/checkout-service`
  c) If error rate > 30%: SEV1 — page on-call, rollback, and file incident.

**Prevention**: Gate deployments on canary analysis (1% → 10% → 50% traffic shift).
""",
        "runbooks/deployment-induced-error-surge.md",
        None,
    ),
    (
        """# Post-Mortem: checkout-service v2.2.9 Serialization Bug — 2025-06-15
Service: checkout-service
Root Cause: New Pydantic v2 migration in v2.2.9 changed default field serialization.
Legacy clients sending snake_case fields received 422 Unprocessable Entity.

**Timeline**:
  14:00 UTC — v2.2.9 deployed to canary (1% traffic)
  14:15 UTC — Error rate at 0.4% (within SLO)
  14:30 UTC — Traffic shifted to 10%; error rate jumped to 14%
  14:31 UTC — On-call paged; 14:38 UTC rollback completed

**Remediation**: Rollback to v2.2.8. Serialization fix released as v2.2.10.
**Detection**: Deployment correlation alert fired correctly.
""",
        "post-mortems/checkout-serialization-regression.md",
        None,
    ),
    (
        """# Runbook: TLS Certificate Expiry
Service: api-gateway (and any service with mutual TLS)
Trigger: Certificate expires in < 72 hours.

**Severity**: SEV3 (advisory) if > 24h remaining. SEV1 if expired.

**Renewal Steps (cert-manager)**:
  1. Verify Certificate resource: `kubectl describe certificate api-gateway-tls -n prod`
  2. Force renewal: `kubectl annotate certificate api-gateway-tls cert-manager.io/issuer-kind=ClusterIssuer`
  3. Monitor: `kubectl get certificaterequest -n prod -w`

**Manual Renewal (if cert-manager unavailable)**:
  - Generate new CSR; submit to CA; apply new Secret.
  - No downtime if done correctly before expiry.

**Post-Renewal Validation**: Verify TLS handshake with `openssl s_client -connect api.example.com:443`.
""",
        "runbooks/tls-certificate-expiry.md",
        None,
    ),
    (
        """# Circuit Breaker Incident Pattern
Classification: Infrastructure Fragility

**Pattern**: Cloud operator circuit breakers trip when downstream APIs return 5xx
responses for > 5 consecutive calls. When tripped:
  - Remediation calls are immediately rejected (CircuitOpenError).
  - Breaker remains open for 30s (configurable).
  - After timeout, one probe call is allowed (HALF_OPEN).
  - Success closes the breaker; failure extends the open window.

**Implication for SRE Agent**: If the cloud operator is degraded, the agent
cannot apply remediation until the circuit recovers. The operator must be paged.

**Recovery Actions**:
  1. Check cloud provider status page.
  2. Verify IAM credentials have not expired.
  3. Wait for HALF_OPEN probe; if successful, operations resume automatically.
""",
        "runbooks/circuit-breaker-fragility.md",
        None,
    ),
]


# ---------------------------------------------------------------------------
# Act 1: Deployment-Induced Incident
# ---------------------------------------------------------------------------

async def run_act1_deployment_regression(pipeline, llm) -> dict:
    banner("ACT 1 — Bad Canary Deployment Detected", color=C.HEADER)
    print(f"  {C.DIM}checkout-service v2.3.1 was deployed 14 minutes ago.{C.RESET}")
    print(f"  {C.DIM}Pydantic v3 migration broke legacy API clients — 503 errors surging.{C.RESET}\n")

    alert = AnomalyAlert(
        service="checkout-service",
        anomaly_type=AnomalyType.DEPLOYMENT_INDUCED,
        description=(
            "HTTP 503 error rate surged to 22% — 14 minutes after deployment of "
            "checkout-service v2.3.1. Pydantic v3 field serialization changed "
            "default encoding for UUID fields, breaking 400+ legacy API clients."
        ),
        metric_name="http_5xx_error_rate",
        current_value=22.0,
        baseline_value=0.4,
        deviation_sigma=10.8,
        compute_mechanism=ComputeMechanism.KUBERNETES,
        is_deployment_induced=True,
        deployment_details={
            "commit_sha": "f7e3d1c",
            "version": "v2.3.1",
            "deployer": "ci-bot",
            "deploy_timestamp": "2026-07-15T14:00:00Z",
            "canary_traffic_pct": 10,
        },
    )

    section("🚨", "Deployment Alert",
            f"service={alert.service}  metric={alert.metric_name}  "
            f"value={alert.current_value}  sigma={alert.deviation_sigma}σ")
    print(f"   {C.YELLOW}Deployment detected: commit {alert.deployment_details['commit_sha']} "
          f"(v{alert.deployment_details['version']}){C.RESET}\n")

    event_bus = InMemoryEventBus()
    event_store = InMemoryEventStore()
    pipeline._event_bus = event_bus
    pipeline._event_store = event_store

    diag_start = time.time()
    result = await pipeline.diagnose(DiagnosisRequest(alert=alert, max_evidence_items=4))
    diag_elapsed = time.time() - diag_start

    sev_color = C.RED if result.severity.name in ("SEV1", "SEV2") else C.YELLOW
    field("Severity", f"{sev_color}{C.BOLD}{result.severity.name}{C.RESET}")
    field("Confidence", f"{result.confidence * 100:.1f}%")
    field("Diagnosis Time", f"{diag_elapsed:.2f}s")
    field(
        "Execution Guardrail",
        f"{C.RED}⛔ Human Approval Required{C.RESET}" if result.requires_human_approval
        else f"{C.GREEN}✅ Autonomous{C.RESET}",
    )
    separator()
    print(f"\n   {C.BOLD}Root Cause (Live LLM):{C.RESET}")
    for line in (result.root_cause or "Not determined.").splitlines():
        print(f"     {C.CYAN}{line.strip()}{C.RESET}")

    if result.evidence_citations:
        print(f"\n   {C.BOLD}Evidence Citations:{C.RESET}")
        for i, ref in enumerate(result.evidence_citations):
            print(f"     [{i + 1}] {C.DIM}{ref}{C.RESET}")

    if result.suggested_remediation:
        print(f"\n   {C.BOLD}Recommended Action:{C.RESET}")
        for line in result.suggested_remediation.splitlines():
            print(f"     {C.GREEN}{line.strip()}{C.RESET}")

    print(f"\n   {C.BOLD}Confidence Breakdown Context:{C.RESET}")
    print(f"   {C.DIM}  Composite: {result.confidence * 100:.1f}% "
          f"(LLM + Validator weights applied){C.RESET}")
    print(f"   {C.DIM}  Note: If the validator disagreed, confidence would drop by ~7.5pp.{C.RESET}")

    return {"result": result, "alert": alert, "event_store": event_store}


# ---------------------------------------------------------------------------
# Act 2: Circuit Breaker Fragility
# ---------------------------------------------------------------------------

async def run_act2_circuit_breaker() -> None:
    banner("ACT 2 — Cloud Operator Circuit Breaker Fragility", color=C.YELLOW)
    print(f"  {C.DIM}The cloud operator returns 5xx errors — circuit breaker trips.{C.RESET}")
    print(f"  {C.DIM}All remediation calls are rejected until the breaker recovers.{C.RESET}\n")

    cb = CircuitBreaker(
        failure_threshold=5,
        recovery_timeout_seconds=3.0,  # Reduced for demo speed
        name="k8s-operator",
    )

    section("🔌", "Circuit Breaker Initial State")
    state_val = CIRCUIT_BREAKER_STATE.labels(
        provider="cloud", resource_type="k8s-operator"
    )._value.get()
    print(f"   State: {state_badge(cb.state.name)}  (Prometheus gauge={state_val:.0f})")

    # Simulate 5 consecutive operator failures
    section("💥", "Simulating 5 Consecutive Cloud Operator Failures",
            "Each failure increments the failure counter...")

    failure_call_count = 0

    async def _failing_operator_call():
        nonlocal failure_call_count
        failure_call_count += 1
        raise TransientError(f"AWS API 503 — Service Unavailable (attempt {failure_call_count})")

    for i in range(5):
        try:
            await retry_with_backoff(
                _failing_operator_call,
                config=RetryConfig(max_retries=0),  # No retries for demo clarity
                circuit_breaker=cb,
            )
        except (TransientError, CircuitOpenError) as exc:
            icon = "🔴" if cb.state == CircuitState.OPEN else "⚠️ "
            state_val = CIRCUIT_BREAKER_STATE.labels(
                provider="cloud", resource_type="k8s-operator"
            )._value.get()
            print(f"   {icon}  Failure {i + 1}: {exc}  →  state={cb.state.name}  gauge={state_val:.0f}")

    print()
    field("Circuit Breaker State After 5 Failures", state_badge(cb.state.name), ok=False)

    # Show that a new call is immediately rejected
    section("🚫", "Attempting Remediation Call — Breaker is OPEN",
            "All calls must be immediately rejected...")
    try:
        await retry_with_backoff(
            _failing_operator_call,
            config=RetryConfig(max_retries=0),
            circuit_breaker=cb,
        )
    except CircuitOpenError as exc:
        print(f"   {C.RED}✖  Remediation blocked: {exc}{C.RESET}")
        field("Outcome", "Call rejected immediately — no latency wasted on a failing API", ok=False)

    # Wait for recovery
    section("⏱", "Waiting for Recovery Timeout (3s demo / 30s production)...")
    for remaining in range(3, 0, -1):
        print(f"   {C.DIM}  ...{remaining}s remaining{C.RESET}", end="\r")
        await asyncio.sleep(1.0)
    print(f"   {C.DIM}  Recovery window elapsed.{C.RESET}        ")

    # Access .state to trigger HALF_OPEN transition
    _ = cb.state
    state_val = CIRCUIT_BREAKER_STATE.labels(
        provider="cloud", resource_type="k8s-operator"
    )._value.get()
    field("Circuit Breaker State After Timeout", state_badge(cb.state.name), ok=False)
    print(f"   {C.DIM}  Prometheus gauge updated to {state_val:.0f} (1 = HALF_OPEN){C.RESET}")

    # Successful probe call closes the breaker
    section("✅", "Sending Probe Call — Cloud Operator Recovered",
            "One successful call closes the breaker...")

    async def _healthy_operator_call():
        return {"status": "ok", "action": "scale_out", "replicas": 5}

    probe_result = await retry_with_backoff(
        _healthy_operator_call,
        config=RetryConfig(max_retries=0),
        circuit_breaker=cb,
    )
    state_val = CIRCUIT_BREAKER_STATE.labels(
        provider="cloud", resource_type="k8s-operator"
    )._value.get()
    field("Probe Result", str(probe_result))
    field("Circuit Breaker State After Recovery", state_badge(cb.state.name))
    print(f"   {C.DIM}  Prometheus gauge reset to {state_val:.0f} (0 = CLOSED){C.RESET}")
    print(f"\n   {C.GREEN}✔  Autonomous remediation is now unblocked — circuit is CLOSED.{C.RESET}")


# ---------------------------------------------------------------------------
# Act 3: Certificate Expiry Advisory
# ---------------------------------------------------------------------------

async def run_act3_certificate_expiry(pipeline, llm) -> dict:
    banner("ACT 3 — TLS Certificate Expiry Advisory", color=C.CYAN)
    print(f"  {C.DIM}api-gateway TLS certificate expires in 5.8 hours.{C.RESET}")
    print(f"  {C.DIM}Low-urgency advisory — no production impact yet.{C.RESET}\n")

    alert = AnomalyAlert(
        service="api-gateway",
        anomaly_type=AnomalyType.CERTIFICATE_EXPIRY,
        description=(
            "TLS certificate for api-gateway (CN=api.example.com) expires in 5.8 hours. "
            "cert-manager renewal job failed due to Let's Encrypt rate limit. "
            "Manual renewal required before 22:00 UTC."
        ),
        metric_name="tls_certificate_expiry_seconds",
        current_value=20_880.0,   # 5.8 hours in seconds
        baseline_value=7_776_000.0,  # 90 days in seconds
        deviation_sigma=14.2,
        compute_mechanism=ComputeMechanism.KUBERNETES,
    )

    section("🔐", "Certificate Expiry Alert",
            f"service={alert.service}  expiry={alert.current_value / 3600:.1f}h remaining  "
            f"sigma={alert.deviation_sigma}σ")

    event_store = InMemoryEventStore()
    pipeline._event_bus = InMemoryEventBus()
    pipeline._event_store = event_store

    diag_start = time.time()
    result = await pipeline.diagnose(DiagnosisRequest(alert=alert, max_evidence_items=3))
    diag_elapsed = time.time() - diag_start

    sev_color = C.YELLOW if result.severity.name in ("SEV3", "SEV4") else C.RED
    field("Severity", f"{sev_color}{C.BOLD}{result.severity.name}{C.RESET}")
    field("Confidence", f"{result.confidence * 100:.1f}%")
    field("Diagnosis Time", f"{diag_elapsed:.2f}s")
    separator()

    print(f"\n   {C.BOLD}Root Cause (Live LLM):{C.RESET}")
    for line in (result.root_cause or "Not determined.").splitlines():
        print(f"     {C.CYAN}{line.strip()}{C.RESET}")

    if result.suggested_remediation:
        print(f"\n   {C.BOLD}Recommended Renewal Steps:{C.RESET}")
        for line in result.suggested_remediation.splitlines():
            print(f"     {C.GREEN}{line.strip()}{C.RESET}")

    if result.evidence_citations:
        print(f"\n   {C.BOLD}Evidence Citations:{C.RESET}")
        for i, ref in enumerate(result.evidence_citations):
            print(f"     [{i + 1}] {C.DIM}{ref}{C.RESET}")

    approval_text = (
        f"{C.RED}Human Approval Required{C.RESET}"
        if result.requires_human_approval
        else f"{C.GREEN}Advisory Only — Agent Logs for Audit{C.RESET}"
    )
    field("Execution Guardrail", approval_text)

    events = await event_store.get_events(str(alert.alert_id))
    print(f"\n   {C.DIM}Events emitted: {', '.join(e.event_type for e in events)}{C.RESET}")

    return {"result": result, "alert": alert}


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

async def run_demo() -> None:
    banner("Live Demo 3 — Deployment Regression & Infrastructure Fragility")

    # --- Phase 0: Bootstrap ---
    section("⚙", "Phase 0: Bootstrapping Intelligence Adapters",
            "Connecting ChromaDB, Sentence-Transformers, and LLM API...")
    boot_start = time.time()
    vs = create_vector_store(collection_name="deployment_demo_kb")
    emb = create_embedding()
    llm = create_llm()
    boot_elapsed = time.time() - boot_start
    field("Adapters Ready", f"Loaded in {boot_elapsed:.2f}s")

    # --- Phase 1: Knowledge Base ingestion ---
    section("📚", "Phase 1: Knowledge Base Ingestion",
            "Embedding deployment runbooks and post-mortems...")
    ingest = create_ingestion_pipeline(vector_store=vs, embedding=emb)
    ingest_start = time.time()
    await ingest.ingest_batch(DEPLOYMENT_RUNBOOKS)
    ingest_elapsed = time.time() - ingest_start
    field("Documents Ingested", f"{len(DEPLOYMENT_RUNBOOKS)} runbooks vectorized in {ingest_elapsed:.2f}s")

    # --- Create shared pipeline ---
    pipeline = create_diagnostic_pipeline(
        vector_store=vs,
        embedding=emb,
        llm=llm,
        service_tiers={
            "checkout-service": ServiceTier.TIER_2,
            "api-gateway": ServiceTier.TIER_1,
        },
        context_budget=4000,
    )

    # --- Act 1: Deployment regression ---
    act1_data = await run_act1_deployment_regression(pipeline, llm)

    # --- Act 2: Circuit breaker ---
    await run_act2_circuit_breaker()

    # --- Act 3: Certificate expiry ---
    act3_data = await run_act3_certificate_expiry(pipeline, llm)

    # --- Final evaluation ---
    banner("DEPLOYMENT REGRESSION — EVALUATION SUMMARY", color=C.GREEN)

    act1_result = act1_data["result"]
    act3_result = act3_data["result"]

    print(f"  {C.BOLD}ACT 1 — Deployment-Induced Error Surge:{C.RESET}")
    print(f"    Severity: {act1_result.severity.name}  "
          f"Confidence: {act1_result.confidence * 100:.1f}%  "
          f"Approval: {'Required' if act1_result.requires_human_approval else 'Autonomous'}")

    print(f"\n  {C.BOLD}ACT 2 — Circuit Breaker:{C.RESET}")
    print(f"    Trip threshold: 5 failures  Recovery: 3s (demo) / 30s (prod)")
    print(f"    State progression: CLOSED → OPEN → HALF_OPEN → CLOSED ✓")

    print(f"\n  {C.BOLD}ACT 3 — Certificate Expiry Advisory:{C.RESET}")
    print(f"    Severity: {act3_result.severity.name}  "
          f"Confidence: {act3_result.confidence * 100:.1f}%  "
          f"Approval: {'Required' if act3_result.requires_human_approval else 'Autonomous'}")

    usage = llm.get_token_usage()
    print(f"\n  {C.DIM}Total LLM Token Usage: {usage.prompt_tokens} prompt / "
          f"{usage.completion_tokens} completion / {usage.total_tokens} total{C.RESET}")

    print(f"\n  {C.BOLD}Key Observations for Improvement:{C.RESET}")
    print(f"  {C.YELLOW}  1. If validation disagreement reduces confidence below threshold,")
    print(f"       the deployment diagnosis may still be classified correctly but the")
    print(f"       low confidence score should trigger an explanatory warning.{C.RESET}")
    print(f"  {C.YELLOW}  2. The circuit breaker recovery demo shows remediation is blocked")
    print(f"       for the full recovery_timeout window — consider a shorter default (15s).{C.RESET}")
    print(f"  {C.YELLOW}  3. Certificate expiry severity depends on remaining time — the agent")
    print(f"       should dynamically adjust severity based on hours_remaining.{C.RESET}")

    print(f"\n  {C.GREEN}Demo complete.{C.RESET}\n")


if __name__ == "__main__":
    try:
        asyncio.run(run_demo())
    except KeyboardInterrupt:
        print("\nDemo interrupted by user. Exiting.")
        sys.exit(0)
