"""
Re-export shim — ProviderHealthMonitor has moved to domain/detection/provider_health.py.

This module exists ONLY for backward compatibility. New code should
import from `sre_agent.domain.detection.provider_health` directly.

See: Engineering Standards §1.1, §4.5
"""

from sre_agent.domain.detection.provider_health import (  # noqa: F401
    CircuitState,
    ProviderHealthMonitor,
)
