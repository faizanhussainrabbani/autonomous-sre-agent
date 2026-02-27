"""
Domain Detection Context — Anomaly detection, baselines, correlation.

Public API for the Detection bounded context (§1.2).
"""

from sre_agent.domain.detection.anomaly_detector import (
    AnomalyDetector,
    DetectionResult,
)
from sre_agent.domain.detection.alert_correlation import (
    AlertCorrelationEngine,
    CorrelatedIncident,
)
from sre_agent.domain.detection.baseline import (
    BaselineService,
    BaselineWindow,
)
from sre_agent.domain.detection.pipeline_monitor import (
    PipelineHealthMonitor,
)
from sre_agent.domain.detection.signal_correlator import (
    SignalCorrelator,
)
from sre_agent.domain.detection.dependency_graph import (
    DependencyGraphService,
)
from sre_agent.domain.detection.provider_health import (
    ProviderHealthMonitor,
    CircuitState,
)
from sre_agent.domain.detection.provider_registry import (
    ProviderRegistry,
    ProviderRegistryError,
)
from sre_agent.domain.detection.late_data_handler import (
    LateDataHandler,
)

__all__ = [
    "AnomalyDetector",
    "DetectionResult",
    "AlertCorrelationEngine",
    "CorrelatedIncident",
    "BaselineService",
    "BaselineWindow",
    "PipelineHealthMonitor",
    "SignalCorrelator",
    "DependencyGraphService",
    "ProviderHealthMonitor",
    "CircuitState",
    "ProviderRegistry",
    "ProviderRegistryError",
    "LateDataHandler",
]
