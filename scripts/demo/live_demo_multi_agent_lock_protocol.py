#!/usr/bin/env python3
"""
Live Demo 13 — Multi-Agent Lock Protocol

Simulates lock acquisition, priority preemption, cooling-off enforcement, and
human override behavior as defined in AGENTS.md.

Environment
-----------
    SKIP_PAUSES          Set to "1" to skip interactive pauses
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from _demo_utils import env_bool

SKIP_PAUSES = env_bool("SKIP_PAUSES", False)


@dataclass
class LockRecord:
    agent_id: str
    resource_type: str
    resource_name: str
    namespace: str
    compute_mechanism: str
    resource_id: str
    provider: str
    priority_level: int
    acquired_at: str
    ttl_seconds: int
    fencing_token: int


class DemoLockManager:
    def __init__(self) -> None:
        self._lock: LockRecord | None = None
        self._cooldown_until: float = 0.0
        self._human_override: bool = False

    def request_lock(self, record: LockRecord) -> tuple[bool, str]:
        now = time.time()

        if self._human_override:
            return False, "denied: human override active"

        if now < self._cooldown_until and (self._lock is None or record.priority_level >= self._lock.priority_level):
            return False, "denied: cooldown active"

        if self._lock is None:
            self._lock = record
            return True, "granted"

        if record.priority_level < self._lock.priority_level:
            previous = self._lock.agent_id
            self._lock = record
            return True, f"granted with preemption (revoked: {previous})"

        return False, f"denied: locked by {self._lock.agent_id}"

    def release_lock(self, actor: str, cooldown_seconds: int = 30) -> str:
        self._lock = None
        self._cooldown_until = time.time() + cooldown_seconds
        return f"released by {actor}; cooldown={cooldown_seconds}s"

    def activate_human_override(self) -> str:
        self._human_override = True
        self._lock = None
        return "human override active; all autonomous lock requests denied"


def pause(prompt: str) -> None:
    if SKIP_PAUSES:
        print("[SKIPPED] Interactive pause disabled")
        return
    input(f"\n{prompt}\n")


def record(agent_id: str, priority: int) -> LockRecord:
    return LockRecord(
        agent_id=agent_id,
        resource_type="deployment",
        resource_name="checkout-service",
        namespace="prod",
        compute_mechanism="KUBERNETES",
        resource_id="deployment/checkout-service",
        provider="kubernetes",
        priority_level=priority,
        acquired_at=datetime.now(timezone.utc).isoformat(),
        ttl_seconds=180,
        fencing_token=int(time.time() * 1000),
    )


def main() -> None:
    manager = DemoLockManager()

    print("\nLive Demo 13 — Multi-Agent Lock Protocol")
    print("=" * 60)
    print("Resource: deployment/checkout-service (prod)")

    sre = record("sre-agent-prod-01", 2)
    secops = record("secops-agent-prod-01", 1)
    finops = record("finops-agent-prod-01", 3)

    print("\nPhase 1: SRE acquires lock")
    granted, reason = manager.request_lock(sre)
    print(json.dumps({"granted": granted, "reason": reason, "record": sre.__dict__}, indent=2))

    pause("Press ENTER to simulate SecOps preemption")
    print("\nPhase 2: SecOps requests same resource with higher priority")
    granted, reason = manager.request_lock(secops)
    print(json.dumps({"granted": granted, "reason": reason, "record": secops.__dict__}, indent=2))

    pause("Press ENTER to simulate cooldown behavior")
    print("\nPhase 3: SecOps releases lock, cooldown enforced")
    print(manager.release_lock(actor="secops-agent-prod-01", cooldown_seconds=15))
    granted, reason = manager.request_lock(finops)
    print(json.dumps({"granted": granted, "reason": reason, "record": finops.__dict__}, indent=2))

    pause("Press ENTER to simulate human override")
    print("\nPhase 4: Human override activates global kill-switch behavior")
    print(manager.activate_human_override())
    granted, reason = manager.request_lock(sre)
    print(json.dumps({"granted": granted, "reason": reason, "record": sre.__dict__}, indent=2))

    print("\n✅ Multi-agent lock protocol simulation complete")


if __name__ == "__main__":
    main()
