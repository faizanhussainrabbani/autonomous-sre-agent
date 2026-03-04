"""
Tests for config/settings.py — configuration loading and validation.

Covers: config/settings.py — raising coverage from 63% to ~90%.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import yaml

from sre_agent.config.settings import (
    AgentConfig,
    AWSConfig,
    AzureConfig,
    CloudProviderType,
    FeatureFlags,
    NewRelicConfig,
    OTelConfig,
    PerformanceConfig,
    TelemetryProviderType,
)


# ---------------------------------------------------------------------------
# Tests: Default configuration
# ---------------------------------------------------------------------------

def test_default_config():
    config = AgentConfig()
    assert config.telemetry_provider == TelemetryProviderType.OTEL
    assert config.cloud_provider == CloudProviderType.NONE
    assert config.log_level == "INFO"
    assert config.environment == "development"


# ---------------------------------------------------------------------------
# Tests: from_dict
# ---------------------------------------------------------------------------

def test_from_dict_full():
    data = {
        "telemetry_provider": "otel",
        "cloud_provider": "aws",
        "otel": {"prometheus_url": "http://prom:9090", "jaeger_url": "http://jaeger:16686"},
        "newrelic": {"account_id": "12345", "region": "EU"},
        "aws": {"region": "eu-west-1", "eks_cluster_name": "prod"},
        "azure": {"subscription_id": "sub-1", "resource_group": "rg"},
        "detection": {"latency_sigma_threshold": 4.0},
        "performance": {"alert_latency_seconds": 30},
        "features": {"ebpf_enabled": False},
        "log_level": "DEBUG",
        "environment": "production",
    }
    config = AgentConfig.from_dict(data)
    assert config.telemetry_provider == TelemetryProviderType.OTEL
    assert config.cloud_provider == CloudProviderType.AWS
    assert config.otel.prometheus_url == "http://prom:9090"
    assert config.newrelic.account_id == "12345"
    assert config.aws.region == "eu-west-1"
    assert config.azure.subscription_id == "sub-1"
    assert config.detection.latency_sigma_threshold == 4.0
    assert config.performance.alert_latency_seconds == 30
    assert config.features.ebpf_enabled is False
    assert config.log_level == "DEBUG"
    assert config.environment == "production"


def test_from_dict_empty():
    config = AgentConfig.from_dict({})
    assert config.telemetry_provider == TelemetryProviderType.OTEL
    assert config.log_level == "INFO"


# ---------------------------------------------------------------------------
# Tests: from_yaml
# ---------------------------------------------------------------------------

def test_from_yaml():
    data = {"telemetry_provider": "newrelic", "log_level": "ERROR"}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(data, f)
        f.flush()
        config = AgentConfig.from_yaml(f.name)
    assert config.telemetry_provider == TelemetryProviderType.NEWRELIC
    assert config.log_level == "ERROR"


def test_from_yaml_empty_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("")
        f.flush()
        config = AgentConfig.from_yaml(f.name)
    assert config.telemetry_provider == TelemetryProviderType.OTEL


# ---------------------------------------------------------------------------
# Tests: Validation
# ---------------------------------------------------------------------------

def test_validate_otel_valid():
    config = AgentConfig(telemetry_provider=TelemetryProviderType.OTEL)
    errors = config.validate()
    assert len(errors) == 0


def test_validate_otel_missing_prometheus():
    config = AgentConfig(
        telemetry_provider=TelemetryProviderType.OTEL,
        otel=OTelConfig(prometheus_url=""),
    )
    errors = config.validate()
    assert any("prometheus_url" in e for e in errors)


def test_validate_newrelic_missing_account():
    config = AgentConfig(
        telemetry_provider=TelemetryProviderType.NEWRELIC,
        newrelic=NewRelicConfig(account_id=""),
    )
    errors = config.validate()
    assert any("account_id" in e for e in errors)


def test_validate_aws_missing_fields():
    config = AgentConfig(
        cloud_provider=CloudProviderType.AWS,
        aws=AWSConfig(region="us-east-1", eks_cluster_name=""),
    )
    errors = config.validate()
    assert any("eks_cluster_name" in e for e in errors)


def test_validate_azure_missing_fields():
    config = AgentConfig(
        cloud_provider=CloudProviderType.AZURE,
        azure=AzureConfig(subscription_id="", resource_group="", aks_cluster_name=""),
    )
    errors = config.validate()
    assert any("subscription_id" in e for e in errors)
    assert any("resource_group" in e for e in errors)
    assert any("aks_cluster_name" in e for e in errors)


def test_validate_azure_valid():
    config = AgentConfig(
        cloud_provider=CloudProviderType.AZURE,
        azure=AzureConfig(subscription_id="sub", resource_group="rg", aks_cluster_name="aks"),
    )
    errors = config.validate()
    assert len(errors) == 0
