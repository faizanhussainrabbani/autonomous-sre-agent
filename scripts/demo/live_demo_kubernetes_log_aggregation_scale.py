#!/usr/bin/env python3
"""
Live Demo 24 (Strict Live) - Kubernetes Pod Log Aggregation and Scale Remediation
===================================================================================

This script is strict-live for production demos:

1. Requires RUN_KUBECTL=1 and a reachable Kubernetes cluster
2. Requires a reachable SRE Agent API (or START_AGENT=1)
3. Deploys from an existing repo manifest instead of ad-hoc nginx deployments
4. Targets one real deployment/service from that manifest (TARGET_SERVICE)
5. Fails fast if cluster/app paths are unavailable

Environment
-----------
    K8S_NAMESPACE      Namespace for demo workloads (default: sre-demo)
    K8S_CLUSTER        Cluster display name (default: sre-local)
    RUN_KUBECTL        MUST be "1" for strict-live execution
    SKIP_PAUSES        Set to "1" for non-interactive runs
    AGENT_PORT         SRE Agent port (default: 8181)
    START_AGENT        Set to "1" to auto-start SRE Agent server
    MANIFEST_PATH      Existing workload manifest path
                       (default: infra/k8s/sample-services.yaml)
    TARGET_SERVICE     Deployment/service to target from manifest (default: svc-a)
    SCALE_TARGET       Target replica count after remediation (default: 3)
    FAULT_MEMORY_LIMIT Fault-injection memory limit (default: 32Mi)

Notes
-----
The script keeps remediation steps explicit and observable. It does not fall
back to synthetic diagnosis or synthetic telemetry.
"""

from __future__ import annotations

import json
import os
import shlex
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib import request as urlrequest

from _demo_utils import (
    C,
    banner,
    env_bool,
    fail,
    field,
    info,
    ok,
    pause_if_interactive,
    phase,
    step,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
NAMESPACE = os.getenv("K8S_NAMESPACE", "sre-demo")
CLUSTER_NAME = os.getenv("K8S_CLUSTER", "sre-local")
RUN_KUBECTL = env_bool("RUN_KUBECTL", False)
SKIP_PAUSES = env_bool("SKIP_PAUSES", False)
AGENT_PORT = int(os.getenv("AGENT_PORT", "8181"))
AGENT_URL = f"http://127.0.0.1:{AGENT_PORT}"
START_AGENT = env_bool("START_AGENT", False)
TARGET_SERVICE = os.getenv("TARGET_SERVICE", "svc-a")
SCALE_TARGET = int(os.getenv("SCALE_TARGET", "3"))
FAULT_MEMORY_LIMIT = os.getenv("FAULT_MEMORY_LIMIT", "32Mi")

manifest_default = PROJECT_ROOT / "infra" / "k8s" / "sample-services.yaml"
MANIFEST_PATH = Path(os.getenv("MANIFEST_PATH", str(manifest_default))).expanduser()
if not MANIFEST_PATH.is_absolute():
    MANIFEST_PATH = (PROJECT_ROOT / MANIFEST_PATH).resolve()

VENV_UVICORN = PROJECT_ROOT / ".venv" / "bin" / "uvicorn"

# Process handles and in-memory state for cross-phase data.
_agent_proc: subprocess.Popen | None = None
_store: dict[str, Any] = {}


def pause(prompt: str = "Press ENTER to continue...") -> None:
    pause_if_interactive(SKIP_PAUSES, prompt)


@dataclass(frozen=True)
class K8sCommand:
    title: str
    command: str


def kubectl(args: str, *, namespaced: bool = True) -> str:
    if namespaced:
        return f"kubectl -n {NAMESPACE} {args}"
    return f"kubectl {args}"


def run_kubectl(cmd: K8sCommand, *, allow_fail: bool = False) -> str:
    """Execute kubectl command and return stdout."""
    print(f"\n   {C.YELLOW}>{C.RESET} {C.BOLD}{cmd.title}{C.RESET}")
    print(f"     {C.DIM}{cmd.command}{C.RESET}")

    proc = subprocess.run(
        shlex.split(cmd.command),
        text=True,
        capture_output=True,
        check=False,
    )

    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()

    if stdout:
        for line in stdout.split("\n")[:20]:
            print(f"     {line}")

    if proc.returncode != 0:
        if stderr:
            for line in stderr.split("\n")[:8]:
                print(f"     {C.RED}{line}{C.RESET}")

        if allow_fail:
            info(f"Command exited with status {proc.returncode} (non-fatal)")
            return ""

        fail(f"Command exited with status {proc.returncode}")
        sys.exit(proc.returncode)

    return stdout


def run_kubectl_json(cmd: K8sCommand, *, allow_fail: bool = False) -> dict[str, Any]:
    """Run kubectl command that must return JSON."""
    raw = run_kubectl(cmd, allow_fail=allow_fail)
    if not raw:
        if allow_fail:
            return {}
        fail("Expected JSON output, received empty output")
        sys.exit(1)

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        fail(f"Failed to parse JSON output: {exc}")
        sys.exit(1)


def _agent_health() -> tuple[bool, dict[str, Any]]:
    """Return SRE Agent health and payload when reachable."""
    try:
        with urlrequest.urlopen(f"{AGENT_URL}/health", timeout=3) as response:
            payload = json.loads(response.read())
        status_value = str(payload.get("status", "")).lower()
        return status_value in {"ok", "healthy"}, payload
    except Exception:
        return False, {}


def _parse_cpu_millicores(value: str) -> float:
    value = value.strip()
    if value.endswith("m"):
        return float(value[:-1])
    return float(value) * 1000.0


def _parse_memory_mib(value: str) -> float:
    value = value.strip()
    if value.endswith("Ki"):
        return float(value[:-2]) / 1024.0
    if value.endswith("Mi"):
        return float(value[:-2])
    if value.endswith("Gi"):
        return float(value[:-2]) * 1024.0
    if value.endswith("Ti"):
        return float(value[:-2]) * 1024.0 * 1024.0
    if value.endswith("M"):
        return float(value[:-1])
    if value.endswith("G"):
        return float(value[:-1]) * 1000.0
    return float(value)


def _collect_top_metrics(service: str) -> list[dict[str, Any]]:
    """Collect live pod CPU and memory metrics from kubectl top."""
    output = ""
    lines: list[str] = []
    deadline = time.time() + 120

    while time.time() < deadline:
        output = run_kubectl(K8sCommand(
            title=f"Live metrics for app={service}",
            command=kubectl(f"top pods -l app={service} --no-headers"),
        ), allow_fail=True)

        lines = [line.strip() for line in output.split("\n") if line.strip()]
        if lines:
            break

        info(f"Metrics not available yet for app={service}; retrying in 5s")
        time.sleep(5)
    else:
        fail(
            f"No metrics returned for app={service} within 120s. "
            "Ensure metrics-server is installed and healthy."
        )
        sys.exit(1)

    now = datetime.now(timezone.utc).isoformat()
    metrics: list[dict[str, Any]] = []
    for line in lines:
        columns = line.split()
        if len(columns) < 3:
            continue

        pod_name = columns[0]
        cpu_raw = columns[1]
        mem_raw = columns[2]

        metrics.append({
            "name": "cpu_usage_millicores",
            "value": _parse_cpu_millicores(cpu_raw),
            "timestamp": now,
            "labels": {
                "service": service,
                "namespace": NAMESPACE,
                "pod": pod_name,
            },
        })
        metrics.append({
            "name": "memory_usage_mib",
            "value": _parse_memory_mib(mem_raw),
            "timestamp": now,
            "labels": {
                "service": service,
                "namespace": NAMESPACE,
                "pod": pod_name,
            },
        })

    if not metrics:
        fail(f"Unable to parse metrics from kubectl top output for app={service}")
        sys.exit(1)

    return metrics


def _collect_restart_metrics(service: str) -> list[dict[str, Any]]:
    """Collect live restart-count metrics from pod status."""
    pods_json = run_kubectl_json(K8sCommand(
        title=f"Live pod restart counts for app={service}",
        command=kubectl(f"get pods -l app={service} -o json"),
    ))

    items = pods_json.get("items", [])
    now = datetime.now(timezone.utc).isoformat()
    metrics: list[dict[str, Any]] = []
    for item in items:
        pod_name = item.get("metadata", {}).get("name", "unknown-pod")
        statuses = item.get("status", {}).get("containerStatuses", [])
        restart_count = sum(int(s.get("restartCount", 0)) for s in statuses)
        metrics.append({
            "name": "restart_count",
            "value": float(restart_count),
            "timestamp": now,
            "labels": {
                "service": service,
                "namespace": NAMESPACE,
                "pod": pod_name,
            },
        })

    return metrics


def _collect_live_logs(service: str) -> list[dict[str, Any]]:
    """Collect real pod logs from kubectl; fail when unavailable."""
    pods_json = run_kubectl_json(K8sCommand(
        title=f"Pods available for log collection (app={service})",
        command=kubectl(f"get pods -l app={service} -o json"),
    ))

    running_pods = [
        item.get("metadata", {}).get("name", "")
        for item in pods_json.get("items", [])
        if item.get("status", {}).get("phase") == "Running"
    ]

    if not running_pods:
        fail(f"No running pods available for app={service}; cannot collect strict-live logs.")
        sys.exit(1)

    lines: list[str] = []
    for pod_name in running_pods[:5]:
        output = run_kubectl(K8sCommand(
            title=f"Live logs from pod {pod_name}",
            command=kubectl(f"logs pod/{pod_name} --tail=200 --timestamps"),
        ), allow_fail=True)
        pod_lines = [line.strip() for line in output.split("\n") if line.strip()]
        if pod_lines:
            lines.extend(pod_lines)

    if not lines:
        fail(f"No logs returned for app={service}. Cannot continue strict-live demo.")
        sys.exit(1)

    entries: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()

    for line in lines[:60]:
        severity = "INFO"
        lowered = line.lower()
        if "error" in lowered or "oom" in lowered or "crash" in lowered:
            severity = "ERROR"
        elif "warn" in lowered or "timeout" in lowered:
            severity = "WARNING"

        timestamp = now
        message = line
        parts = line.split(" ", 1)
        if len(parts) == 2 and "t" in parts[0].lower():
            timestamp = parts[0]
            message = parts[1]

        entries.append({
            "timestamp": timestamp,
            "message": message,
            "severity": severity,
            "labels": {
                "service": service,
                "namespace": NAMESPACE,
            },
        })

    return entries


def _deployment_snapshot(service: str) -> dict[str, Any]:
    deployment = run_kubectl_json(K8sCommand(
        title=f"Deployment snapshot for {service}",
        command=kubectl(f"get deployment/{service} -o json"),
    ))

    container = (
        deployment.get("spec", {})
        .get("template", {})
        .get("spec", {})
        .get("containers", [{}])[0]
    )
    resources = container.get("resources", {}) or {}
    limits = resources.get("limits", {}) or {}
    requests = resources.get("requests", {}) or {}

    return {
        "replicas": int(deployment.get("spec", {}).get("replicas", 0) or 0),
        "ready_replicas": int(deployment.get("status", {}).get("readyReplicas", 0) or 0),
        "limits": {
            "cpu": limits.get("cpu"),
            "memory": limits.get("memory"),
        },
        "requests": {
            "cpu": requests.get("cpu"),
            "memory": requests.get("memory"),
        },
    }


def _pod_health_summary(service: str) -> dict[str, Any]:
    pods = run_kubectl_json(K8sCommand(
        title=f"Pod status summary for app={service}",
        command=kubectl(f"get pods -l app={service} -o json"),
    ))

    summary: list[dict[str, Any]] = []
    restart_total = 0
    reasons: list[str] = []

    for item in pods.get("items", []):
        name = item.get("metadata", {}).get("name", "unknown-pod")
        status = item.get("status", {})
        phase_value = status.get("phase", "Unknown")
        statuses = status.get("containerStatuses", [])
        restart_count = sum(int(s.get("restartCount", 0)) for s in statuses)
        ready = all(bool(s.get("ready", False)) for s in statuses) if statuses else False

        waiting_reasons = [
            s.get("state", {}).get("waiting", {}).get("reason")
            for s in statuses
            if s.get("state", {}).get("waiting", {}).get("reason")
        ]
        terminated_reasons = [
            s.get("lastState", {}).get("terminated", {}).get("reason")
            for s in statuses
            if s.get("lastState", {}).get("terminated", {}).get("reason")
        ]

        restart_total += restart_count
        reasons.extend(waiting_reasons)
        reasons.extend(terminated_reasons)

        summary.append({
            "name": name,
            "phase": phase_value,
            "ready": ready,
            "restart_count": restart_count,
            "reasons": waiting_reasons + terminated_reasons,
        })

    return {
        "pods": summary,
        "restart_total": restart_total,
        "reasons": [r for r in reasons if r],
    }


def _wait_for_fault_signal(
    service: str,
    *,
    baseline_pods: set[str] | None = None,
    timeout_seconds: int = 90,
) -> dict[str, Any]:
    """Wait for crash-loop/restart or rollout replacement signals after fault injection."""
    baseline = baseline_pods or set()
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        health = _pod_health_summary(service)
        current_pods = {pod.get("name", "") for pod in health.get("pods", []) if pod.get("name")}
        replaced_pods = sorted(pod for pod in current_pods if pod not in baseline)
        unready_pods = [
            pod.get("name", "")
            for pod in health.get("pods", [])
            if not pod.get("ready", False)
        ]
        crash_like = {
            reason for reason in health.get("reasons", [])
            if reason in {"CrashLoopBackOff", "OOMKilled", "Error"}
        }
        if health.get("restart_total", 0) > 0 or crash_like:
            health["signal"] = "restart_or_crash"
            return health
        if replaced_pods:
            health["signal"] = "rollout_replacement"
            health["replaced_pods"] = replaced_pods
            health["unready_pods"] = [pod for pod in unready_pods if pod]
            return health
        if unready_pods:
            health["signal"] = "rollout_unready"
            health["unready_pods"] = [pod for pod in unready_pods if pod]
            return health
        time.sleep(5)

    fail(
        f"Fault signal not observed for app={service} within {timeout_seconds}s "
        "(no restarts/crash or rollout signals)."
    )
    sys.exit(1)


def _fault_request_memory(limit_memory: str) -> str:
    """Choose a request memory value that is always <= fault memory limit."""
    try:
        limit_mib = _parse_memory_mib(limit_memory)
    except ValueError:
        return "16Mi"

    if limit_mib <= 2.0:
        return "1Mi"

    request_mib = min(16.0, max(1.0, limit_mib / 2.0))
    if request_mib >= limit_mib:
        request_mib = max(1.0, limit_mib - 1.0)

    return f"{int(request_mib)}Mi"


def _average(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / float(len(values))


def phase0_preflight() -> None:
    phase(0, "Pre-flight Checks (Strict Live)")

    step("Enforce strict-live execution")
    if not RUN_KUBECTL:
        fail("RUN_KUBECTL=1 is required for this strict-live demo")
        fail("Refusing to run with simulation or dry-run behavior")
        sys.exit(1)
    ok("Strict-live mode confirmed")

    step("Validate manifest and target service inputs")
    if not MANIFEST_PATH.exists():
        fail(f"Manifest path not found: {MANIFEST_PATH}")
        sys.exit(1)

    manifest_text = MANIFEST_PATH.read_text(encoding="utf-8")
    if f"name: {TARGET_SERVICE}" not in manifest_text:
        fail(
            f"Target service '{TARGET_SERVICE}' not found in {MANIFEST_PATH}. "
            "Set TARGET_SERVICE to an existing deployment/service name."
        )
        sys.exit(1)
    ok("Manifest path and target service are valid")

    step("Verify kubectl client and cluster connectivity")
    run_kubectl(K8sCommand(
        title="kubectl client version",
        command=kubectl("version --client=true", namespaced=False),
    ))
    run_kubectl(K8sCommand(
        title="kubectl cluster-info",
        command=kubectl("cluster-info", namespaced=False),
    ))
    ok("kubectl connected to cluster")

    step("Verify SRE Agent app path")
    if START_AGENT:
        info("START_AGENT=1 set. Agent process will be launched in Phase 3.")
    else:
        healthy, payload = _agent_health()
        if not healthy:
            fail(f"SRE Agent not reachable at {AGENT_URL}")
            fail("Start the agent manually or set START_AGENT=1")
            sys.exit(1)
        ok(f"SRE Agent reachable: {payload}")

    field("Namespace", NAMESPACE)
    field("Cluster", CLUSTER_NAME)
    field("Manifest", MANIFEST_PATH)
    field("Target service", TARGET_SERVICE)
    field("Scale target", SCALE_TARGET)
    field("Agent URL", AGENT_URL)

    pause("Pre-flight complete. Press ENTER to deploy manifest workloads...")


def phase1_deploy_manifest_workload() -> None:
    phase(1, "Deploy Existing Manifest and Target Real Service")

    step(f"Ensure namespace '{NAMESPACE}' exists")
    ns_present = run_kubectl(K8sCommand(
        title="Check namespace",
        command=kubectl(f"get namespace {NAMESPACE}", namespaced=False),
    ), allow_fail=True)

    if not ns_present:
        run_kubectl(K8sCommand(
            title=f"Create namespace {NAMESPACE}",
            command=kubectl(f"create namespace {NAMESPACE}", namespaced=False),
        ))
    ok(f"Namespace ready: {NAMESPACE}")

    step("Apply existing manifest in target namespace")
    manifest_arg = shlex.quote(str(MANIFEST_PATH))
    run_kubectl(K8sCommand(
        title="Apply workload manifest",
        command=kubectl(f"apply -f {manifest_arg}"),
    ))

    step(f"Verify target deployment/service for '{TARGET_SERVICE}'")
    run_kubectl(K8sCommand(
        title="Get target deployment",
        command=kubectl(f"get deployment/{TARGET_SERVICE} -o wide"),
    ))
    run_kubectl(K8sCommand(
        title="Get target service",
        command=kubectl(f"get service/{TARGET_SERVICE} -o wide"),
    ))

    run_kubectl(K8sCommand(
        title="Wait for target rollout",
        command=kubectl(f"rollout status deployment/{TARGET_SERVICE} --timeout=180s"),
    ))

    snapshot = _deployment_snapshot(TARGET_SERVICE)
    initial_replicas = int(snapshot.get("replicas", 0) or 0)
    if initial_replicas <= 0:
        fail("Target deployment has zero replicas after rollout")
        sys.exit(1)
    if SCALE_TARGET <= initial_replicas:
        fail(
            f"SCALE_TARGET={SCALE_TARGET} must be greater than initial replicas={initial_replicas}"
        )
        sys.exit(1)

    _store["initial_replicas"] = initial_replicas
    _store["original_resources"] = {
        "limits": snapshot.get("limits", {}),
        "requests": snapshot.get("requests", {}),
    }

    field("Initial replicas", initial_replicas)
    field("Original limits", snapshot.get("limits", {}))
    field("Original requests", snapshot.get("requests", {}))

    pause("Manifest workload deployed. Press ENTER to capture baseline telemetry...")


def phase2_baseline_metrics() -> None:
    phase(2, "Capture Baseline Metrics from Live Pods")

    step(f"Pod inventory for app={TARGET_SERVICE}")
    run_kubectl(K8sCommand(
        title="List target pods",
        command=kubectl(f"get pods -l app={TARGET_SERVICE} -o wide"),
    ))

    baseline_metrics = _collect_top_metrics(TARGET_SERVICE)
    baseline_metrics.extend(_collect_restart_metrics(TARGET_SERVICE))
    _store["baseline_metrics"] = baseline_metrics

    ok(f"Captured {len(baseline_metrics)} baseline metric points")
    for metric in baseline_metrics[:6]:
        label = metric.get("labels", {}).get("pod", TARGET_SERVICE)
        field(f"  {label} / {metric['name']}", metric["value"])

    pause("Baseline captured. Press ENTER to ensure SRE Agent is running...")


def phase3_start_agent() -> None:
    global _agent_proc
    phase(3, "Ensure SRE Agent FastAPI Server Availability")

    if START_AGENT:
        step(f"Launch uvicorn on port {AGENT_PORT}")
        if not VENV_UVICORN.exists():
            fail(f"uvicorn executable not found at {VENV_UVICORN}")
            sys.exit(1)

        agent_log = open("/tmp/sre_agent_demo24.log", "w", encoding="utf-8")
        _agent_proc = subprocess.Popen(
            [
                str(VENV_UVICORN),
                "sre_agent.api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(AGENT_PORT),
            ],
            stdout=agent_log,
            stderr=agent_log,
            cwd=str(PROJECT_ROOT),
        )
        info(f"Agent PID: {_agent_proc.pid}")
        info("Agent logs: /tmp/sre_agent_demo24.log")

    step("Verify /health endpoint")
    deadline = time.time() + 45
    while time.time() < deadline:
        healthy, payload = _agent_health()
        if healthy:
            ok(f"SRE Agent healthy: {payload}")
            break
        time.sleep(1)
    else:
        fail(f"SRE Agent not healthy at {AGENT_URL}/health")
        if START_AGENT and Path("/tmp/sre_agent_demo24.log").exists():
            tail = Path("/tmp/sre_agent_demo24.log").read_text(encoding="utf-8")[-1200:]
            info("Last agent log lines:")
            print(tail)
        sys.exit(1)

    pause("Agent path verified. Press ENTER to seed diagnostic runbooks...")


def phase4_seed_knowledge_base() -> None:
    phase(4, "Seed Knowledge Base with Kubernetes Runbooks")

    runbooks = [
        {
            "source": "runbooks/k8s-pod-oomkilled.md",
            "metadata": {
                "tier": "1",
                "platform": "kubernetes",
                "service": TARGET_SERVICE,
            },
            "content": (
                "# Kubernetes Pod OOMKilled - Memory Pressure Remediation\n\n"
                "## Symptoms\n"
                "- Pod OOMKilled (exit code 137)\n"
                "- Restart count spikes\n"
                "- CrashLoopBackOff observed\n\n"
                "## Remediation\n"
                "1. Scale deployment horizontally to distribute memory pressure\n"
                "2. Restore safe resource requests/limits\n"
                "3. Validate pod readiness and restart stabilization\n"
            ),
        },
        {
            "source": "runbooks/k8s-horizontal-scaling.md",
            "metadata": {
                "tier": "2",
                "platform": "kubernetes",
                "service": TARGET_SERVICE,
            },
            "content": (
                "# Kubernetes Horizontal Scaling Playbook\n\n"
                "## Trigger\n"
                "Scale when memory/CPU saturation causes service instability.\n\n"
                "## Procedure\n"
                "1. Check current replicas and pod health\n"
                "2. Scale deployment to target replicas\n"
                "3. Wait for rollout and validate Ready pods\n"
            ),
        },
    ]

    for runbook in runbooks:
        step(f"Ingest runbook: {runbook['source']}")
        request = urlrequest.Request(
            f"{AGENT_URL}/api/v1/diagnose/ingest",
            data=json.dumps(runbook).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        start = time.time()
        with urlrequest.urlopen(request, timeout=120) as response:
            payload = json.loads(response.read())
        if payload.get("status") != "success":
            fail(f"Runbook ingestion failed for {runbook['source']}: {payload}")
            sys.exit(1)
        elapsed = time.time() - start
        ok(f"Ingested in {elapsed:.1f}s: {runbook['source']}")

    pause("Runbooks ingested. Press ENTER to inject live fault...")


def phase5_inject_fault() -> None:
    phase(5, f"Inject Memory Fault on {TARGET_SERVICE}")

    baseline_health = _pod_health_summary(TARGET_SERVICE)
    baseline_pods = {
        pod.get("name", "")
        for pod in baseline_health.get("pods", [])
        if pod.get("name")
    }

    resources = _store.get("original_resources", {})
    limits = resources.get("limits", {})
    requests = resources.get("requests", {})
    cpu_limit = limits.get("cpu") or "100m"
    cpu_request = requests.get("cpu") or "100m"
    fault_request_memory = _fault_request_memory(FAULT_MEMORY_LIMIT)

    step("Apply restrictive memory limits to force instability")
    run_kubectl(K8sCommand(
        title="Patch target deployment resources",
        command=kubectl(
            f"set resources deployment/{TARGET_SERVICE} "
            f"--limits=cpu={cpu_limit},memory={FAULT_MEMORY_LIMIT} "
            f"--requests=cpu={cpu_request},memory={fault_request_memory}"
        ),
    ))

    step("Wait for fault indicators (restarts/crash or rollout replacement)")
    health = _wait_for_fault_signal(
        TARGET_SERVICE,
        baseline_pods=baseline_pods,
        timeout_seconds=90,
    )
    _store["fault_health"] = health

    field("Fault signal", health.get("signal", "unknown"))
    field("Observed restart total", health.get("restart_total", 0))
    field("Observed reasons", ", ".join(sorted(set(health.get("reasons", [])))) or "none")
    replaced_pods = health.get("replaced_pods") or []
    if replaced_pods:
        field("Replaced pods", ", ".join(replaced_pods))
    unready_pods = health.get("unready_pods") or []
    if unready_pods:
        field("Unready pods", ", ".join(unready_pods))
    for pod in health.get("pods", [])[:6]:
        field(
            f"  {pod['name']}",
            f"phase={pod['phase']} ready={pod['ready']} restarts={pod['restart_count']} reasons={pod['reasons']}",
        )

    pause("Fault observed. Press ENTER to collect logs and metrics...")


def phase6_collect_logs_and_metrics() -> None:
    phase(6, "Collect Live Pod Logs and Correlated Metrics")

    logs = _collect_live_logs(TARGET_SERVICE)
    metrics = _collect_top_metrics(TARGET_SERVICE)
    metrics.extend(_collect_restart_metrics(TARGET_SERVICE))

    describe_output = run_kubectl(K8sCommand(
        title=f"Describe pods for app={TARGET_SERVICE}",
        command=kubectl(f"describe pods -l app={TARGET_SERVICE}"),
    ))
    event_lines = [
        line.strip()
        for line in describe_output.split("\n")
        if "warning" in line.lower() or "oom" in line.lower() or "backoff" in line.lower()
    ]

    now = datetime.now(timezone.utc)
    _store["correlated_signals"] = {
        "service": TARGET_SERVICE,
        "namespace": NAMESPACE,
        "time_window_start": (now - timedelta(minutes=5)).isoformat(),
        "time_window_end": now.isoformat(),
        "compute_mechanism": "kubernetes",
        "metrics": metrics,
        "logs": logs,
        "traces": [],
        "events": event_lines[:20],
    }

    ok("Correlated signals assembled from live cluster data")
    field("Metric points", len(metrics))
    field("Log entries", len(logs))
    field("Event excerpts", len(event_lines[:20]))

    for entry in logs[:5]:
        sev = entry.get("severity", "INFO")
        color = C.RED if sev == "ERROR" else C.YELLOW if sev == "WARNING" else C.GREEN
        print(f"     {color}[{sev}]{C.RESET} {entry['message'][:120]}")

    pause("Live telemetry captured. Press ENTER to trigger diagnosis...")


def phase7_diagnose() -> None:
    phase(7, "Trigger RAG Diagnosis via SRE Agent")

    alert_id = str(uuid.uuid4())
    _store["alert_id"] = alert_id

    baseline_values = [
        float(m["value"])
        for m in _store.get("baseline_metrics", [])
        if m.get("name") == "memory_usage_mib"
    ]
    current_values = [
        float(m["value"])
        for m in _store.get("correlated_signals", {}).get("metrics", [])
        if m.get("name") == "memory_usage_mib"
    ]

    baseline_memory = _average(baseline_values)
    current_memory = max(current_values) if current_values else baseline_memory
    sigma_denominator = max(1.0, baseline_memory * 0.10)
    deviation_sigma = max(0.0, round((current_memory - baseline_memory) / sigma_denominator, 2))

    payload = {
        "alert": {
            "alert_id": alert_id,
            "anomaly_type": "memory_pressure",
            "service": TARGET_SERVICE,
            "namespace": NAMESPACE,
            "compute_mechanism": "kubernetes",
            "metric_name": "memory_usage_mib",
            "current_value": round(current_memory, 2),
            "baseline_value": round(baseline_memory, 2),
            "deviation_sigma": deviation_sigma,
            "description": (
                f"Live Kubernetes deployment '{TARGET_SERVICE}' in namespace '{NAMESPACE}' "
                "shows restart growth and pod instability following memory-limit fault injection."
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "correlated_signals": _store.get("correlated_signals", {}),
        }
    }

    field("Alert ID", alert_id)
    field("Current memory (MiB)", round(current_memory, 2))
    field("Baseline memory (MiB)", round(baseline_memory, 2))
    field("Deviation sigma", deviation_sigma)

    step("POST /api/v1/diagnose")
    request = urlrequest.Request(
        f"{AGENT_URL}/api/v1/diagnose",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    start = time.time()
    with urlrequest.urlopen(request, timeout=120) as response:
        diagnosis = json.loads(response.read())
    elapsed = time.time() - start

    if diagnosis.get("status") != "success":
        fail(f"Diagnosis API returned unexpected payload: {diagnosis}")
        sys.exit(1)

    _store["diagnosis"] = diagnosis
    _store["diagnosis_live"] = True
    ok(f"Live diagnosis received in {elapsed:.1f}s")

    pause("Diagnosis complete. Press ENTER to review diagnosis...")


def phase8_show_diagnosis() -> None:
    phase(8, f"Diagnosis Result for {TARGET_SERVICE}")

    diagnosis = _store["diagnosis"]
    width = 74

    print(f"\n   {C.BOLD}{C.GREEN}{'-' * width}{C.RESET}")
    print(f"   {C.BOLD}{C.GREEN}SRE AGENT DIAGNOSIS (LIVE){C.RESET}")
    print(f"   {C.BOLD}{C.GREEN}{'-' * width}{C.RESET}\n")

    field("Alert ID", diagnosis.get("alert_id", "n/a"))
    field("Status", diagnosis.get("status", "n/a"))
    field("Severity", diagnosis.get("severity", "n/a"))
    confidence = float(diagnosis.get("confidence", 0.0) or 0.0)
    field("Confidence", f"{confidence * 100:.1f}%")
    field("Requires Approval", diagnosis.get("requires_approval", "n/a"))

    root_cause = diagnosis.get("root_cause") or "n/a"
    print(f"\n   {C.CYAN}Root Cause:{C.RESET}")
    for sentence in str(root_cause).split(". "):
        sentence = sentence.strip()
        if sentence:
            print(f"      {sentence}.")

    remediation = diagnosis.get("remediation") or "n/a"
    print(f"\n   {C.CYAN}Suggested Remediation:{C.RESET}")
    for sentence in str(remediation).split(". "):
        sentence = sentence.strip()
        if sentence:
            print(f"      - {sentence}.")

    citations = diagnosis.get("citations") or []
    if citations:
        print(f"\n   {C.CYAN}Evidence Citations:{C.RESET}")
        for citation in citations:
            field("  source", citation.get("source", "n/a"))
            field("  relevance", f"{float(citation.get('relevance_score', 0.0)):.3f}")

    audit = diagnosis.get("audit_trail") or []
    if audit:
        print(f"\n   {C.CYAN}Audit Trail:{C.RESET}")
        for entry in audit:
            stage = entry.get("stage", "") if isinstance(entry, dict) else ""
            action = entry.get("action", "") if isinstance(entry, dict) else ""
            details = entry.get("details", {}) if isinstance(entry, dict) else {}
            print(f"      {C.DIM}{stage}/{action}:{C.RESET} {details}")

    pause("Diagnosis reviewed. Press ENTER to generate remediation plan...")


def phase9_remediation_plan() -> None:
    phase(9, "Remediation Plan (Live)")

    diagnosis = _store["diagnosis"]
    confidence = float(diagnosis.get("confidence", 0.0) or 0.0)
    initial_replicas = int(_store.get("initial_replicas", 1))

    step("Generate scale-up plan")
    field("Action", f"Scale deployment/{TARGET_SERVICE}")
    field("Current replicas", initial_replicas)
    field("Target replicas", SCALE_TARGET)
    field("Namespace", NAMESPACE)
    field("Command", kubectl(f"scale deployment/{TARGET_SERVICE} --replicas={SCALE_TARGET}"))

    if confidence >= 0.85:
        approval_level = "AUTONOMOUS"
    elif confidence >= 0.70:
        approval_level = "PROPOSE"
    else:
        approval_level = "BLOCK"

    severity = str(diagnosis.get("severity", "SEV4"))
    requires_human = bool(diagnosis.get("requires_approval", False))

    field("Approval level", approval_level)
    field("Confidence", f"{confidence * 100:.1f}%")
    field("Severity", severity)
    field("Requires human approval", requires_human)

    step("Run live safety checks")
    run_kubectl(K8sCommand(
        title="Cluster nodes",
        command=kubectl("get nodes", namespaced=False),
    ))
    run_kubectl(K8sCommand(
        title="Existing HPA objects in namespace",
        command=kubectl("get hpa"),
    ), allow_fail=True)
    run_kubectl(K8sCommand(
        title="PodDisruptionBudgets in namespace",
        command=kubectl("get pdb"),
    ), allow_fail=True)

    if approval_level == "BLOCK":
        fail("Diagnosis confidence too low for automated remediation (BLOCK)")
        sys.exit(1)

    _store["approval_level"] = approval_level
    pause("Remediation plan ready. Press ENTER to execute scale-up...")


def phase10_execute_remediation() -> None:
    phase(10, f"Execute Scale Remediation for {TARGET_SERVICE}")

    resources = _store.get("original_resources", {})
    limits = resources.get("limits", {})
    requests = resources.get("requests", {})

    cpu_limit = limits.get("cpu") or "100m"
    mem_limit = limits.get("memory") or "64Mi"
    cpu_request = requests.get("cpu") or "100m"
    mem_request = requests.get("memory") or "32Mi"

    step("Restore original resource limits")
    run_kubectl(K8sCommand(
        title="Restore deployment resources",
        command=kubectl(
            f"set resources deployment/{TARGET_SERVICE} "
            f"--limits=cpu={cpu_limit},memory={mem_limit} "
            f"--requests=cpu={cpu_request},memory={mem_request}"
        ),
    ))

    step(f"Scale deployment/{TARGET_SERVICE} to {SCALE_TARGET}")
    run_kubectl(K8sCommand(
        title="Scale deployment",
        command=kubectl(f"scale deployment/{TARGET_SERVICE} --replicas={SCALE_TARGET}"),
    ))
    run_kubectl(K8sCommand(
        title="Wait for rollout",
        command=kubectl(f"rollout status deployment/{TARGET_SERVICE} --timeout=180s"),
    ))

    _store["remediation_action"] = {
        "action": "scale",
        "resource_type": "deployment",
        "resource_name": TARGET_SERVICE,
        "namespace": NAMESPACE,
        "previous_replicas": _store.get("initial_replicas"),
        "target_replicas": SCALE_TARGET,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "approval_level": _store.get("approval_level", "AUTONOMOUS"),
    }

    ok("Remediation action executed")
    field("Action ID", str(uuid.uuid4())[:8])
    field("Executed at", _store["remediation_action"]["executed_at"])
    field("Approval", _store["remediation_action"]["approval_level"])

    pause("Remediation executed. Press ENTER to validate outcome...")


def phase11_validate() -> None:
    phase(11, "Validate Live Remediation Outcome")

    deployment = _deployment_snapshot(TARGET_SERVICE)
    pod_health = _pod_health_summary(TARGET_SERVICE)

    desired = int(deployment.get("replicas", 0) or 0)
    ready = int(deployment.get("ready_replicas", 0) or 0)
    pods = pod_health.get("pods", [])
    ready_pods = [p for p in pods if p.get("ready", False)]
    unready_pods = [p for p in pods if not p.get("ready", False)]

    step("Validation checks")
    field("Desired replicas", desired)
    field("Ready replicas", ready)
    field("Pods discovered", len(pods))
    field("Ready pods", len(ready_pods))
    field("Total restart count", pod_health.get("restart_total", 0))

    if desired != SCALE_TARGET:
        fail(f"Validation failed: desired replicas is {desired}, expected {SCALE_TARGET}")
        sys.exit(1)
    if ready < SCALE_TARGET:
        fail(f"Validation failed: ready replicas is {ready}, expected at least {SCALE_TARGET}")
        sys.exit(1)
    if len(ready_pods) < SCALE_TARGET:
        fail("Validation failed: not enough ready pods after remediation")
        for pod in unready_pods:
            field("  Unready pod", f"{pod['name']} reasons={pod['reasons']}")
        sys.exit(1)

    print(f"\n   {C.BOLD}{C.GREEN}{'-' * 60}{C.RESET}")
    print(f"   {C.BOLD}{C.GREEN}LIVE VALIDATION SUMMARY{C.RESET}")
    print(f"   {C.BOLD}{C.GREEN}{'-' * 60}{C.RESET}\n")

    field("Service", TARGET_SERVICE)
    field("Namespace", NAMESPACE)
    field("Scaled replicas", f"{_store.get('initial_replicas')} -> {SCALE_TARGET}")
    field("Ready pods", f"{len(ready_pods)}/{len(pods)}")
    field("Validation result", "PASS")
    ok("Remediation validated successfully on live cluster")

    pause("Validation complete. Press ENTER to clean up resources...")


def phase12_cleanup() -> None:
    phase(12, "Cleanup Demo Resources")

    step(f"Delete namespace {NAMESPACE}")
    run_kubectl(K8sCommand(
        title="Delete namespace",
        command=kubectl(f"delete namespace {NAMESPACE} --ignore-not-found", namespaced=False),
    ), allow_fail=True)
    ok(f"Namespace cleanup requested: {NAMESPACE}")

    if _agent_proc and _agent_proc.poll() is None:
        step("Terminate demo-started SRE Agent process")
        _agent_proc.terminate()
        try:
            _agent_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _agent_proc.kill()
        ok(f"Agent process {_agent_proc.pid} terminated")

    if START_AGENT:
        info("Agent logs: /tmp/sre_agent_demo24.log")


def _signal_handler(_: int, __: Any) -> None:
    print(f"\n\n   {C.YELLOW}Interrupted - running cleanup...{C.RESET}")
    phase12_cleanup()
    sys.exit(130)


def main() -> None:
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    banner("Live Demo 24 (Strict Live) - Kubernetes Log Aggregation and Scale")

    phase0_preflight()
    phase1_deploy_manifest_workload()
    phase2_baseline_metrics()
    phase3_start_agent()
    phase4_seed_knowledge_base()
    phase5_inject_fault()
    phase6_collect_logs_and_metrics()
    phase7_diagnose()
    phase8_show_diagnosis()
    phase9_remediation_plan()
    phase10_execute_remediation()
    phase11_validate()
    phase12_cleanup()

    print(f"\n{C.BOLD}{C.GREEN}[OK] Demo 24 complete (strict-live path verified){C.RESET}")
    print(f"{C.DIM}detect -> diagnose -> remediate -> validate (all live paths){C.RESET}\n")


if __name__ == "__main__":
    main()
