"""
Structured Logging Configuration — ensures JSON output for production (§2.3 Factor XI).

Call `configure_logging()` at application startup to enable structured JSON
logging via structlog. In development, uses colored console output for readability.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog


def _bind_alert_id(logger: Any, method: str, event_dict: dict) -> dict:
    """Structlog processor — inject the current alert correlation ID (OBS-007).

    Reads ``_current_alert_id`` from the metrics contextvar and adds it to the
    event dict under the ``alert_id`` key.  When no diagnose() is in scope the
    contextvar holds an empty string, so the key is omitted to keep non-pipeline
    log lines clean.
    """
    try:
        from sre_agent.adapters.telemetry.metrics import _current_alert_id  # local import avoids circular dep
        value = _current_alert_id.get("")
        if value:
            event_dict["alert_id"] = value
    except Exception:  # noqa: BLE001
        pass
    return event_dict


def configure_logging(
    log_level: str = "INFO",
    json_output: bool = True,
) -> None:
    """Configure structlog for the application.

    Args:
        log_level: Python log level string (DEBUG, INFO, WARNING, ERROR).
        json_output: If True, emit JSON logs to stdout (production).
                     If False, emit colored console output (development).
    """
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        _bind_alert_id,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if json_output:
        # Production: JSON to stdout, collected by OTel pipeline (§2.3 Factor XI)
        renderer = structlog.processors.JSONRenderer()
    else:
        # Development: colored console for human readability
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
