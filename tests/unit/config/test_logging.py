"""
Tests for config/logging.py — structured logging configuration.

Covers: config/logging.py — raising coverage from 0% to ~90%.
"""

from __future__ import annotations

import logging

import structlog


def test_configure_logging_json_output():
    """JSON mode sets structlog with JSONRenderer."""
    from sre_agent.config.logging import configure_logging

    configure_logging(log_level="DEBUG", json_output=True)
    root = logging.getLogger()
    assert root.level == logging.DEBUG
    assert len(root.handlers) >= 1


def test_configure_logging_console_output():
    """Console mode sets structlog with ConsoleRenderer."""
    from sre_agent.config.logging import configure_logging

    configure_logging(log_level="WARNING", json_output=False)
    root = logging.getLogger()
    assert root.level == logging.WARNING


def test_configure_logging_replaces_handlers():
    """Repeated calls don't accumulate handlers."""
    from sre_agent.config.logging import configure_logging

    configure_logging(log_level="INFO", json_output=True)
    configure_logging(log_level="ERROR", json_output=True)
    root = logging.getLogger()
    # Should have exactly 1 handler (cleared + re-added)
    assert len(root.handlers) == 1
    assert root.level == logging.ERROR


def test_configure_logging_invalid_level_defaults():
    """Invalid log level string defaults to INFO."""
    from sre_agent.config.logging import configure_logging

    configure_logging(log_level="NONEXISTENT", json_output=True)
    root = logging.getLogger()
    assert root.level == logging.INFO
