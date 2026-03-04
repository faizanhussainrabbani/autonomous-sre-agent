"""
Detection Configuration — Domain-owned configuration types.

These configuration types are owned by the domain layer so that domain
services can depend on them without importing the config/ module,
preserving hexagonal architecture boundaries (§1.1).

The config/ layer (settings.py) imports these types and populates them
from external YAML/env-var sources.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DetectionConfig:
    """Anomaly detection configuration.

    Domain-owned value object — the config module loads raw values
    from YAML/env-vars and constructs this dataclass at startup.

    .. note:: **Two-phase detection pattern:**
        The anomaly detector uses a two-phase pattern for latency spikes
        and memory pressure. The *first* metric above threshold starts a
        timer (no alert). The *second* metric checks if the condition has
        persisted for the configured duration and fires the alert. This
        prevents transient spikes from triggering false alerts. Even with
        ``latency_duration_minutes=0``, two data points are required.
    """
    latency_sigma_threshold: float = 3.0
    latency_duration_minutes: int = 2
    error_rate_surge_percent: float = 200.0
    memory_pressure_percent: float = 85.0
    memory_pressure_duration_minutes: int = 5
    disk_exhaustion_percent: float = 80.0
    disk_projection_hours: int = 24
    cert_expiry_warning_days: int = 14
    cert_expiry_critical_days: int = 3
    deployment_correlation_window_minutes: int = 60
    suppression_window_seconds: int = 30

    # Phase 1.5: Serverless cold-start suppression (AC-1.5.3)
    cold_start_suppression_window_seconds: int = 15

    # Multi-dimensional correlation (AC-3.2.3)
    multi_dim_latency_percent: float = 50.0   # +50% latency shift
    multi_dim_error_percent: float = 80.0     # +80% error rate shift
    multi_dim_window_minutes: int = 5         # Window to observe both shifts
