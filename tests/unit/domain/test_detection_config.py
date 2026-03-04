"""
Unit tests for DetectionConfig — Task 13.5, AC-3.5.1, AC-3.5.2.

Validates default thresholds, per-service overrides, and sensitivity levels.
"""

from __future__ import annotations

import pytest

from sre_agent.domain.models.detection_config import DetectionConfig


@pytest.mark.unit
class TestDetectionConfigDefaults:
    """Verify DetectionConfig sensible defaults match engineering standards."""

    def test_default_latency_sigma_threshold(self) -> None:
        """Default sigma threshold is 3.0 per §3 anomaly detection."""
        config = DetectionConfig()
        assert config.latency_sigma_threshold == 3.0

    def test_default_latency_duration_minutes(self) -> None:
        """Default sustained duration is 2 minutes."""
        config = DetectionConfig()
        assert config.latency_duration_minutes == 2

    def test_default_error_rate_surge_percent(self) -> None:
        """Default error rate surge is 200% of baseline."""
        config = DetectionConfig()
        assert config.error_rate_surge_percent == 200.0

    def test_default_memory_pressure_percent(self) -> None:
        """Default memory pressure threshold is 85%."""
        config = DetectionConfig()
        assert config.memory_pressure_percent == 85.0

    def test_default_disk_exhaustion_percent(self) -> None:
        """Default disk exhaustion threshold is 80%."""
        config = DetectionConfig()
        assert config.disk_exhaustion_percent == 80.0

    def test_default_cert_expiry_warning_days(self) -> None:
        """Default cert expiry warning is 14 days."""
        config = DetectionConfig()
        assert config.cert_expiry_warning_days == 14

    def test_default_cert_expiry_critical_days(self) -> None:
        """Default cert expiry critical is 3 days."""
        config = DetectionConfig()
        assert config.cert_expiry_critical_days == 3


@pytest.mark.unit
class TestDetectionConfigOverrides:
    """Verify DetectionConfig accepts custom override values."""

    def test_custom_sigma_threshold(self) -> None:
        """AC-3.5.1: Per-service sensitivity via lower sigma threshold."""
        config = DetectionConfig(latency_sigma_threshold=2.0)
        assert config.latency_sigma_threshold == 2.0

    def test_custom_suppression_window(self) -> None:
        """Custom suppression window overrides default 30s."""
        config = DetectionConfig(suppression_window_seconds=60)
        assert config.suppression_window_seconds == 60

    def test_cold_start_suppression_window(self) -> None:
        """Phase 1.5: Cold start suppression window defaults to 15s."""
        config = DetectionConfig()
        assert config.cold_start_suppression_window_seconds == 15

    def test_custom_cold_start_window(self) -> None:
        """Custom cold start suppression window override."""
        config = DetectionConfig(cold_start_suppression_window_seconds=30)
        assert config.cold_start_suppression_window_seconds == 30

    def test_multi_dim_latency_percent_default(self) -> None:
        """AC-3.2.3: Multi-dimensional correlation defaults."""
        config = DetectionConfig()
        assert config.multi_dim_latency_percent == 50.0

    def test_multi_dim_error_percent_default(self) -> None:
        """AC-3.2.3: Multi-dimensional error correlation defaults."""
        config = DetectionConfig()
        assert config.multi_dim_error_percent == 80.0
