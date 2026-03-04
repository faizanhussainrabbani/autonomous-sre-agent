"""
Unit test conftest — fixtures specific to isolated domain tests.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from sre_agent.domain.detection.baseline import BaselineService
from sre_agent.domain.detection.anomaly_detector import AnomalyDetector
from sre_agent.domain.detection.alert_correlation import AlertCorrelationEngine
from sre_agent.events.in_memory import InMemoryEventBus
from sre_agent.config.settings import DetectionConfig


@pytest.fixture
def baseline_service() -> BaselineService:
    """Pre-configured BaselineService for unit tests."""
    return BaselineService()


@pytest.fixture
def anomaly_detector(detection_config: DetectionConfig) -> AnomalyDetector:
    """Pre-configured AnomalyDetector with default detection config."""
    return AnomalyDetector(config=detection_config)


@pytest.fixture
def correlation_engine(
    event_bus: InMemoryEventBus,
    simple_service_graph,
) -> AlertCorrelationEngine:
    """AlertCorrelationEngine with a simple A→B→C service graph."""
    return AlertCorrelationEngine(
        event_bus=event_bus,
        service_graph=simple_service_graph,
    )


@pytest.fixture
def mock_telemetry_provider() -> MagicMock:
    """Mock TelemetryProvider for domain tests that need a provider stub."""
    mock = MagicMock()
    mock.query_metrics = AsyncMock(return_value=[])
    mock.query_traces = AsyncMock(return_value=[])
    mock.query_logs = AsyncMock(return_value=[])
    mock.health_check = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def mock_cloud_operator() -> MagicMock:
    """Mock CloudOperatorPort for remediation tests."""
    mock = MagicMock()
    mock.restart_service = AsyncMock(return_value=True)
    mock.scale_service = AsyncMock(return_value=True)
    mock.stop_service = AsyncMock(return_value=True)
    return mock
