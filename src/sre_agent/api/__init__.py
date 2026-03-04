"""
SRE Agent API Entrypoints — FastAPI app + Click CLI.

Architecture: This module is the outermost layer of the Hexagonal Architecture.
It wires adapters to domain services and exposes:
  - REST API: /health, /status, /api/v1/system/halt, /api/v1/system/resume
  - CLI: sre-agent run, sre-agent validate, sre-agent status
"""
from sre_agent.api import app, cli

__all__ = ["app", "cli"]
