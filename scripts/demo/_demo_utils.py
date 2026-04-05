"""Shared utility helpers for live demo scripts."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import IO, Any, Callable
from urllib import request


class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    WHITE = "\033[97m"


LOCALSTACK_PRO_IMAGE = "localstack/localstack-pro:latest"
LOCALSTACK_REQUIRED_SERVICES = "autoscaling,cloudwatch,ec2,ecs,events,iam,lambda,logs,s3,secretsmanager,sns,sts"
_LOCALSTACK_REQUIRED_SERVICE_SET = {
    "autoscaling",
    "cloudwatch",
    "ec2",
    "ecs",
    "events",
    "iam",
    "lambda",
    "logs",
    "s3",
    "secretsmanager",
    "sns",
    "sts",
}


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def aws_region(default: str = "us-east-1") -> str:
    return os.getenv("AWS_DEFAULT_REGION", default)


def boto_localstack_kwargs(endpoint: str, region: str | None = None) -> dict[str, Any]:
    return {
        "endpoint_url": endpoint,
        "region_name": region or aws_region(),
        "aws_access_key_id": "test",
        "aws_secret_access_key": "test",
    }


def pause_if_interactive(skip_pauses: bool, prompt: str = "Press ENTER to continue...") -> None:
    if skip_pauses:
        print()
        return
    input(f"\n{prompt}\n")


def banner(title: str, width: int = 76) -> None:
    print(f"\n{C.BOLD}{C.BLUE}╔{'═' * width}╗{C.RESET}")
    print(f"{C.BOLD}{C.BLUE}║{title.center(width)}║{C.RESET}")
    print(f"{C.BOLD}{C.BLUE}╚{'═' * width}╝{C.RESET}\n")


def phase(number: int, title: str, width: int = 76) -> None:
    label = f"  PHASE {number}: {title}  "
    print(f"\n{C.BOLD}{C.MAGENTA}╔{'═' * width}╗{C.RESET}")
    print(f"{C.BOLD}{C.MAGENTA}║{label.center(width)}║{C.RESET}")
    print(f"{C.BOLD}{C.MAGENTA}╚{'═' * width}╝{C.RESET}\n")


def step(message: str) -> None:
    print(f"\n   {C.YELLOW}> {C.BOLD}{message}{C.RESET}")


def ok(message: str) -> None:
    print(f"   {C.GREEN}[OK]{C.RESET} {message}")


def info(message: str) -> None:
    print(f"   {C.CYAN}[INFO]{C.RESET} {message}")


def fail(message: str) -> None:
    print(f"   {C.RED}[FAIL]{C.RESET} {C.RED}{message}{C.RESET}")


def field(label: str, value: Any) -> None:
    print(f"   {C.DIM}{label}:{C.RESET} {C.WHITE}{value}{C.RESET}")


def localstack_endpoint(default: str = "http://localhost:4566") -> str:
    return os.getenv("LOCALSTACK_ENDPOINT", default)


def localstack_auth_token() -> str | None:
    """Return LOCALSTACK_AUTH_TOKEN from environment variable, or None."""
    token = (os.getenv("LOCALSTACK_AUTH_TOKEN") or "").strip()
    return token or None


def _localstack_health_payload(endpoint: str) -> dict[str, Any] | None:
    try:
        with request.urlopen(f"{endpoint}/_localstack/health", timeout=3) as response:
            return json.loads(response.read())
    except Exception:
        return None


def _localstack_pro_ready(endpoint: str) -> tuple[bool, str]:
    payload = _localstack_health_payload(endpoint)
    if not payload:
        return False, "health endpoint is unreachable"

    edition = str(payload.get("edition", "")).lower()
    if edition != "pro":
        observed = edition or "unknown"
        return False, f"edition is '{observed}' (expected 'pro')"

    services = payload.get("services") or {}
    missing = [
        svc
        for svc in sorted(_LOCALSTACK_REQUIRED_SERVICE_SET)
        if str(services.get(svc, "")).lower() not in {"available", "running"}
    ]
    if missing:
        return False, f"required services not ready: {', '.join(missing)}"

    return True, "ready"


def is_localstack_healthy(endpoint: str) -> bool:
    payload = _localstack_health_payload(endpoint)
    if not payload:
        return False
    return payload.get("status") in {"running", "ok"} or bool(payload.get("services"))


def ensure_localstack_running(
    endpoint: str,
    auth_token: str | None = None,
    timeout_seconds: int = 90,
    emit_logs: bool = True,
    auto_start: bool = True,
) -> None:
    ready, reason = _localstack_pro_ready(endpoint)
    if ready:
        if emit_logs:
            ok(f"LocalStack Pro reachable at {endpoint}")
        return

    if not auto_start:
        raise RuntimeError(
            f"LocalStack Pro is not ready at {endpoint}: {reason}. "
            "Endpoint-only mode is enabled; start LocalStack Pro via Docker and retry."
        )

    token = (auth_token or localstack_auth_token() or "").strip()
    if not token:
        raise RuntimeError(
            "LOCALSTACK_AUTH_TOKEN is missing. Set it in .env or export it in your shell."
        )

    repo_root = Path(__file__).resolve().parents[2]
    compose_file = repo_root / "docker-compose.deps.yml"
    if not compose_file.exists():
        raise RuntimeError(f"Docker compose file not found: {compose_file}")

    env = os.environ.copy()
    env["LOCALSTACK_AUTH_TOKEN"] = token
    env["SERVICES"] = LOCALSTACK_REQUIRED_SERVICES
    env["DEFAULT_REGION"] = "us-east-1"
    env["LAMBDA_RUNTIME_ENVIRONMENT_TIMEOUT"] = "120"
    env["EAGER_SERVICE_LOADING"] = "1"

    if emit_logs:
        step("LocalStack Pro is not ready, starting Docker Compose service 'localstack'")

    result = subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "up", "-d", "localstack"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "docker compose up for LocalStack failed "
            f"(exit {result.returncode}): {result.stderr.strip() or result.stdout.strip()}"
        )

    if emit_logs:
        info(
            f"Waiting for LocalStack Pro health at {endpoint} "
            f"(timeout {timeout_seconds}s)"
        )

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        ready, _ = _localstack_pro_ready(endpoint)
        if ready:
            if emit_logs:
                ok(f"LocalStack Pro is healthy at {endpoint}")
            return
        time.sleep(2)

    payload = _localstack_health_payload(endpoint)
    observed_edition = "unreachable"
    if payload:
        observed_edition = str(payload.get("edition", "unknown") or "unknown")

    raise RuntimeError(
        "LocalStack Pro did not become ready within "
        f"{timeout_seconds}s (observed edition: {observed_edition}). "
        "If startup logs show license activation failed, verify LOCALSTACK_AUTH_TOKEN."
    )


# ---------------------------------------------------------------------------
# SIGINT / SIGTERM cleanup registration
# ---------------------------------------------------------------------------

def register_cleanup_handler(cleanup_fn: Callable[[], None]) -> None:
    """Register SIGINT and SIGTERM handlers that run *cleanup_fn* before exit.

    Args:
        cleanup_fn: Zero-argument callable invoked on interrupt.  Should
            be safe to call more than once and should not raise.
    """

    def _handler(_sig: int, _frame: Any) -> None:
        print(f"\n{C.YELLOW}Interrupted — running cleanup...{C.RESET}")
        cleanup_fn()
        sys.exit(130)

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)


# ---------------------------------------------------------------------------
# SRE Agent process lifecycle
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VENV_UVICORN = _REPO_ROOT / ".venv" / "bin" / "uvicorn"


def _is_agent_healthy(url: str) -> bool:
    """Probe the agent health endpoint without pulling in httpx."""
    try:
        with request.urlopen(f"{url}/health", timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def start_or_reuse_agent(
    port: int = 8181,
    log_path: str = "/tmp/sre_agent_demo.log",
    startup_timeout: int = 40,
    health_path: str = "/health",
) -> tuple[subprocess.Popen | None, bool, IO[Any] | None]:
    """Start a uvicorn SRE Agent server or reuse one already running.

    Args:
        port: TCP port for the agent.
        log_path: File path for agent stdout/stderr.
        startup_timeout: Seconds to wait for the health endpoint.
        health_path: URL path for the health probe.

    Returns:
        A 3-tuple ``(process, started_by_demo, log_handle)``.
        If an agent was already healthy, returns ``(None, False, None)``.
    """
    url = f"http://127.0.0.1:{port}"
    if _is_agent_healthy(url):
        info(f"Reusing existing SRE Agent on port {port}")
        return None, False, None

    if not _VENV_UVICORN.exists():
        raise RuntimeError(f"uvicorn not found at {_VENV_UVICORN}")

    log_handle: IO[Any] = open(log_path, "w")  # noqa: SIM115
    process = subprocess.Popen(
        [
            str(_VENV_UVICORN),
            "sre_agent.api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(_REPO_ROOT),
        stdout=log_handle,
        stderr=log_handle,
    )

    deadline = time.time() + startup_timeout
    while time.time() < deadline:
        if _is_agent_healthy(url):
            ok(f"SRE Agent started on {url}")
            info(f"Agent logs: {log_path}")
            return process, True, log_handle
        time.sleep(1)

    tail = ""
    try:
        tail = Path(log_path).read_text()[-1200:]
    except Exception:
        tail = "<unable to read log tail>"
    raise RuntimeError(
        f"Agent failed to start within {startup_timeout}s. Log tail:\n{tail}"
    )


def stop_agent(
    process: subprocess.Popen | None,
    started_by_demo: bool,
    log_handle: IO[Any] | None,
    shutdown_timeout: int = 5,
) -> None:
    """Terminate the agent process if it was started by this demo.

    Args:
        process: The Popen handle (may be None if reused).
        started_by_demo: Only terminate if True.
        log_handle: Open log file to close.
        shutdown_timeout: Seconds to wait before sending SIGKILL.
    """
    if started_by_demo and process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=shutdown_timeout)
        except subprocess.TimeoutExpired:
            process.kill()
    if log_handle is not None:
        try:
            log_handle.close()
        except Exception:
            pass
