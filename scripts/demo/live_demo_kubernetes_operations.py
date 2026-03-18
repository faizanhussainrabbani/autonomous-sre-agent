#!/usr/bin/env python3
"""
Live Demo 12 — Kubernetes Operations (Phase 3 gap coverage)

Demonstrates restart and scale workflows for Kubernetes workloads using
kubectl-compatible operations. By default this runs in simulation mode so it
is safe in CI and on developer machines without cluster access.

Environment
-----------
    K8S_NAMESPACE        Namespace to target (default: prod)
    K8S_DEPLOYMENT       Deployment to scale/restart (default: checkout-service)
    K8S_STATEFULSET      StatefulSet to restart (default: cart-db)
    RUN_KUBECTL          Set to "1" to execute real kubectl commands
    SKIP_PAUSES          Set to "1" to skip interactive pauses
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from dataclasses import dataclass

from _demo_utils import env_bool


@dataclass(frozen=True)
class K8sCommand:
    title: str
    command: str


NAMESPACE = os.getenv("K8S_NAMESPACE", "prod")
DEPLOYMENT = os.getenv("K8S_DEPLOYMENT", "checkout-service")
STATEFULSET = os.getenv("K8S_STATEFULSET", "cart-db")
RUN_KUBECTL = env_bool("RUN_KUBECTL", False)
SKIP_PAUSES = env_bool("SKIP_PAUSES", False)


def pause(prompt: str) -> None:
    if SKIP_PAUSES:
        print("[SKIPPED] Interactive pause disabled")
        return
    input(f"\n{prompt}\n")


def run(command: K8sCommand) -> None:
    print(f"\n▶ {command.title}")
    print(f"   {command.command}")

    if not RUN_KUBECTL:
        print("   [SIMULATION] Command not executed. Set RUN_KUBECTL=1 to run against a cluster.")
        return

    proc = subprocess.run(
        shlex.split(command.command),
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.returncode != 0:
        if proc.stderr.strip():
            print(proc.stderr.strip())
        print(f"   [FAIL] command exited with status {proc.returncode}")
        sys.exit(proc.returncode)


def main() -> None:
    print("\nLive Demo 12 — Kubernetes Operations")
    print("=" * 60)
    print(f"Namespace: {NAMESPACE}")
    print(f"Run mode : {'LIVE kubectl' if RUN_KUBECTL else 'SIMULATION'}")

    commands = [
        K8sCommand(
            title="Scale deployment as remediation action",
            command=f"kubectl -n {NAMESPACE} scale deployment/{DEPLOYMENT} --replicas=4",
        ),
        K8sCommand(
            title="Rollout restart deployment",
            command=f"kubectl -n {NAMESPACE} rollout restart deployment/{DEPLOYMENT}",
        ),
        K8sCommand(
            title="Rollout restart statefulset",
            command=f"kubectl -n {NAMESPACE} rollout restart statefulset/{STATEFULSET}",
        ),
    ]

    pause("Press ENTER to apply Kubernetes remediation sequence")
    for item in commands:
        run(item)

    print("\n✅ Kubernetes operations demo completed")


if __name__ == "__main__":
    main()
