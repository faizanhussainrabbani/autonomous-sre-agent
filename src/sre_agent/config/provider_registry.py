"""
Re-export shim — ProviderRegistry has moved to domain/detection/provider_registry.py.

This module exists ONLY for backward compatibility. New code should
import from `sre_agent.domain.detection.provider_registry` directly.

See: Engineering Standards §1.1, §4.5
"""

from sre_agent.domain.detection.provider_registry import (  # noqa: F401
    ProviderRegistry,
    ProviderRegistryError,
)
