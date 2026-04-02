"""Shared utility helpers for live demo scripts."""

from __future__ import annotations

import json
import os
import subprocess
import time
from typing import Any
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
    return os.getenv("LOCALSTACK_AUTH_TOKEN") or os.getenv("LOCALSTACK_API_KEY")


def is_localstack_healthy(endpoint: str) -> bool:
    try:
        with request.urlopen(f"{endpoint}/_localstack/health", timeout=3) as response:
            payload = json.loads(response.read())
        return payload.get("status") in {"running", "ok"} or bool(payload.get("services"))
    except Exception:
        return False


def ensure_localstack_running(
    endpoint: str,
    auth_token: str | None = None,
    timeout_seconds: int = 90,
    emit_logs: bool = True,
) -> None:
    if is_localstack_healthy(endpoint):
        if emit_logs:
            ok(f"LocalStack reachable at {endpoint}")
        return

    env = os.environ.copy()
    if auth_token:
        env["LOCALSTACK_AUTH_TOKEN"] = auth_token
    env["LOCALSTACK_LAMBDA_SYNCHRONOUS_CREATE"] = "1"

    if emit_logs:
        step("LocalStack not running, attempting automatic startup")

    try:
        result = subprocess.run(
            ["localstack", "start", "-d"],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "LocalStack CLI not found. Install with: pip install localstack"
        ) from exc

    if result.returncode not in {0, 1}:
        raise RuntimeError(
            "localstack start failed "
            f"(exit {result.returncode}): {result.stderr.strip() or result.stdout.strip()}"
        )

    if emit_logs:
        info(f"Waiting for LocalStack health at {endpoint} (timeout {timeout_seconds}s)")

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if is_localstack_healthy(endpoint):
            if emit_logs:
                ok(f"LocalStack is healthy at {endpoint}")
            return
        time.sleep(2)

    raise RuntimeError(
        f"LocalStack did not become healthy within {timeout_seconds}s. "
        "Check with: localstack status services"
    )
