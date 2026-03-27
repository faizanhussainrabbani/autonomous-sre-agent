"""Ports — abstract interfaces for external system interactions."""

from sre_agent.ports.telemetry import (
    DependencyGraphQuery,
    LogQuery,
    MetricsQuery,
    TelemetryProvider,
    TraceQuery,
)
from sre_agent.ports.events import EventBus, EventStore
from sre_agent.ports.vector_store import VectorStorePort
from sre_agent.ports.embedding import EmbeddingPort
from sre_agent.ports.llm import LLMReasoningPort
from sre_agent.ports.diagnostics import DiagnosticPort
from sre_agent.ports.remediation import RemediationPort
from sre_agent.ports.lock_manager import DistributedLockManagerPort, LockRequest, LockResult

__all__ = [
    "DependencyGraphQuery",
    "DiagnosticPort",
    "DistributedLockManagerPort",
    "EmbeddingPort",
    "EventBus",
    "EventStore",
    "LLMReasoningPort",
    "LogQuery",
    "MetricsQuery",
    "LockRequest",
    "LockResult",
    "RemediationPort",
    "TelemetryProvider",
    "TraceQuery",
    "VectorStorePort",
]
