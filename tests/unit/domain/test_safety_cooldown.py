"""Unit tests for domain/safety/cooldown.py.

Covers uncovered branches: lines 67-73, 100-120, 131.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from sre_agent.domain.models.canonical import ComputeMechanism
from sre_agent.domain.safety.cooldown import CooldownEnforcer, _split_resource

# ---------------------------------------------------------------------------
# _split_resource helper (line 131)
# ---------------------------------------------------------------------------


def test_split_resource_with_slash() -> None:
    resource_type, resource_name = _split_resource("deployment/checkout-service")
    assert resource_type == "deployment"
    assert resource_name == "checkout-service"


def test_split_resource_without_slash() -> None:
    resource_type, resource_name = _split_resource("checkout-service")
    assert resource_type == "resource"
    assert resource_name == "checkout-service"


# ---------------------------------------------------------------------------
# is_in_cooldown — covered lines 67-73
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cooldown_not_active_when_no_entry() -> None:
    enforcer = CooldownEnforcer()
    in_cd, remaining = await enforcer.is_in_cooldown(
        resource_id="deployment/svc",
        compute_mechanism=ComputeMechanism.KUBERNETES,
        provider="kubernetes",
        namespace="prod",
    )
    assert in_cd is False
    assert remaining == 0


@pytest.mark.asyncio
async def test_cooldown_active_within_window() -> None:
    enforcer = CooldownEnforcer()
    await enforcer.record_action(
        resource_id="deployment/svc",
        compute_mechanism=ComputeMechanism.KUBERNETES,
        provider="kubernetes",
        namespace="prod",
        ttl_seconds=900,
    )
    in_cd, remaining = await enforcer.is_in_cooldown(
        resource_id="deployment/svc",
        compute_mechanism=ComputeMechanism.KUBERNETES,
        provider="kubernetes",
        namespace="prod",
    )
    assert in_cd is True
    assert remaining > 0


@pytest.mark.asyncio
async def test_cooldown_bypassed_for_priority_1() -> None:
    """Priority-1 (SecOps) agent can bypass cooldown."""
    enforcer = CooldownEnforcer()
    await enforcer.record_action(
        resource_id="deployment/svc",
        compute_mechanism=ComputeMechanism.KUBERNETES,
        provider="kubernetes",
        namespace="prod",
        ttl_seconds=900,
    )
    in_cd, remaining = await enforcer.is_in_cooldown(
        resource_id="deployment/svc",
        compute_mechanism=ComputeMechanism.KUBERNETES,
        provider="kubernetes",
        namespace="prod",
        requester_priority=1,
    )
    assert in_cd is False
    assert remaining == 0


@pytest.mark.asyncio
async def test_cooldown_expired_clears_entry() -> None:
    """Expired cooldown entries are cleaned up and return False."""
    enforcer = CooldownEnforcer()
    # Manually insert an already-expired entry
    key = enforcer.build_key(
        resource_id="deployment/svc",
        compute_mechanism=ComputeMechanism.KUBERNETES,
        provider="kubernetes",
        namespace="prod",
    )
    enforcer._cooldowns[key] = time.time() - 1  # expired 1 second ago

    in_cd, remaining = await enforcer.is_in_cooldown(
        resource_id="deployment/svc",
        compute_mechanism=ComputeMechanism.KUBERNETES,
        provider="kubernetes",
        namespace="prod",
    )
    assert in_cd is False
    assert remaining == 0
    # Entry should be cleaned up
    assert key not in enforcer._cooldowns


# ---------------------------------------------------------------------------
# build_key — non-Kubernetes path
# ---------------------------------------------------------------------------


def test_build_key_non_kubernetes() -> None:
    key = CooldownEnforcer.build_key(
        resource_id="arn:aws:lambda:us-east-1:123:function:handler",
        compute_mechanism=ComputeMechanism.SERVERLESS,
        provider="aws",
        namespace="",
    )
    assert key == "cooldown:aws:SERVERLESS:arn:aws:lambda:us-east-1:123:function:handler"


def test_build_key_kubernetes() -> None:
    key = CooldownEnforcer.build_key(
        resource_id="deployment/checkout-service",
        compute_mechanism=ComputeMechanism.KUBERNETES,
        provider="kubernetes",
        namespace="prod",
    )
    assert key == "cooldown:prod:deployment:checkout-service"


# ---------------------------------------------------------------------------
# _audit_cooldown — lines 100-120 (with and without audit port)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_cooldown_no_audit_port() -> None:
    """record_action with no audit port completes without error."""
    enforcer = CooldownEnforcer(audit=None)
    key = await enforcer.record_action(
        resource_id="deployment/svc",
        compute_mechanism=ComputeMechanism.KUBERNETES,
        provider="kubernetes",
        namespace="prod",
        ttl_seconds=60,
    )
    assert key.startswith("cooldown:")


@pytest.mark.asyncio
async def test_audit_cooldown_with_audit_port() -> None:
    """record_action calls audit port when provided."""
    audit = MagicMock()
    audit.record_cooldown_event = AsyncMock()
    enforcer = CooldownEnforcer(audit=audit)

    await enforcer.record_action(
        resource_id="deployment/svc",
        compute_mechanism=ComputeMechanism.KUBERNETES,
        provider="kubernetes",
        namespace="prod",
        ttl_seconds=60,
        actor_id="sre-agent-prod",
    )

    audit.record_cooldown_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_audit_cooldown_swallows_exception() -> None:
    """Audit write failure does not propagate to caller."""
    audit = MagicMock()
    audit.record_cooldown_event = AsyncMock(side_effect=RuntimeError("DB down"))
    enforcer = CooldownEnforcer(audit=audit)

    # Should not raise
    await enforcer.record_action(
        resource_id="deployment/svc",
        compute_mechanism=ComputeMechanism.KUBERNETES,
        provider="kubernetes",
        namespace="prod",
        ttl_seconds=60,
    )
