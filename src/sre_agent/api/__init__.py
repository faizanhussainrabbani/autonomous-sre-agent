"""
SRE Agent API Entrypoints — FastAPI app + Click CLI.

Architecture: This module is the outermost layer of the Hexagonal Architecture.
It wires adapters to domain services and exposes:
  - REST API: /health, /status, /api/v1/system/halt, /api/v1/system/resume
  - CLI: sre-agent run, sre-agent validate, sre-agent status
"""
from sre_agent.api.main import app  # noqa: F401
from sre_agent.api.cli import cli  # noqa: F401

__all__ = ["app", "cli"]
