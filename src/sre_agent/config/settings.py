"""
Application Configuration — Loads and validates agent configuration.

All configuration is externalized (12-Factor: Factor III) and validated
at startup before the agent accepts any incidents.

Validates: AC-1.5.1 (provider selection via config), AC-14.4 (cloud config)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# Load .env file if present.
# override=True ensures .env values always win over inherited shell variables,
# so the key in .env is guaranteed to be the one used — not a stale shell export.
load_dotenv(override=True)


class TelemetryProviderType(Enum):
    """Supported telemetry providers."""
    OTEL = "otel"
    NEWRELIC = "newrelic"


class CloudProviderType(Enum):
    """Supported cloud providers."""
    AWS = "aws"
    AZURE = "azure"
    NONE = "none"  # Self-managed / no cloud provider


@dataclass
class OTelConfig:
    """Configuration for the OTel/Prometheus/Jaeger/Loki adapter."""
    prometheus_url: str = "http://prometheus:9090"
    jaeger_url: str = "http://jaeger:16686"
    loki_url: str = "http://loki:3100"
    otel_collector_url: str = "http://otel-collector:4317"


@dataclass
class NewRelicConfig:
    """Configuration for the New Relic NerdGraph adapter."""
    account_id: str = ""
    api_key_secret_name: str = "newrelic-api-key"  # Retrieved from secrets manager
    region: str = "US"  # US or EU
    nerdgraph_url: str = "https://api.newrelic.com/graphql"


@dataclass
class CloudWatchConfig:
    """CloudWatch telemetry collection configuration."""
    region: str = "us-east-1"
    metric_poll_interval_seconds: int = 60
    log_fetch_window_minutes: int = 30
    log_filter_pattern: str = "ERROR"
    metric_streams_enabled: bool = False
    endpoint_url: str | None = None  # For LocalStack override


@dataclass
class EnrichmentConfig:
    """Bridge enrichment feature toggles."""
    fetch_metrics: bool = True
    fetch_logs: bool = True
    fetch_traces: bool = False  # Enable when XRayTraceAdapter is built
    fetch_resource_metadata: bool = True


@dataclass
class AWSHealthConfig:
    """AWS Health API polling configuration."""
    enabled: bool = False
    poll_interval_seconds: int = 300
    regions: list[str] | None = None


@dataclass
class AWSConfig:
    """AWS-specific configuration."""
    region: str = "us-east-1"
    eks_cluster_name: str = ""
    s3_bucket: str = ""
    secrets_manager_prefix: str = "/sre-agent/"
    iam_role_arn: str | None = None


@dataclass
class AzureConfig:
    """Azure-specific configuration."""
    subscription_id: str = ""
    resource_group: str = ""
    aks_cluster_name: str = ""
    blob_container: str = ""
    keyvault_name: str = ""
    managed_identity_client_id: str | None = None


# DetectionConfig is domain-owned (§1.1 — domain never imports config)
# Re-exported here so the config layer can populate it from YAML.
from sre_agent.domain.models.detection_config import DetectionConfig  # noqa: F401, E402


@dataclass
class PerformanceConfig:
    """Performance SLO targets."""
    alert_latency_seconds: int = 60
    error_alert_latency_seconds: int = 30
    proactive_alert_latency_seconds: int = 120
    rag_query_timeout_seconds: int = 30
    max_concurrent_rag_queries: int = 10
    max_concurrent_remediations: int = 3


@dataclass
class FeatureFlags:
    """Feature flags for capability toggling.

    See Engineering Standards §5.4 — capabilities start disabled.
    """
    ebpf_enabled: bool = True
    multi_dimensional_correlation: bool = True
    deployment_aware_detection: bool = True
    proactive_scaling: bool = False        # Phase 4
    architectural_recommendations: bool = False  # Phase 4
    new_relic_adapter: bool = False
    otel_adapter: bool = True
    cloudwatch_adapter: bool = False
    bridge_enrichment: bool = False
    background_polling: bool = False
    eventbridge_integration: bool = False
    aws_health_polling: bool = False
    xray_adapter: bool = False


@dataclass
class AgentConfig:
    """Root configuration for the SRE agent."""

    # Provider selection
    telemetry_provider: TelemetryProviderType = TelemetryProviderType.OTEL
    cloud_provider: CloudProviderType = CloudProviderType.NONE

    # Provider-specific configs
    otel: OTelConfig = field(default_factory=OTelConfig)
    newrelic: NewRelicConfig = field(default_factory=NewRelicConfig)
    aws: AWSConfig = field(default_factory=AWSConfig)
    azure: AzureConfig = field(default_factory=AzureConfig)
    cloudwatch: CloudWatchConfig = field(default_factory=CloudWatchConfig)
    enrichment: EnrichmentConfig = field(default_factory=EnrichmentConfig)
    aws_health: AWSHealthConfig = field(default_factory=AWSHealthConfig)

    # Detection & performance
    detection: DetectionConfig = field(default_factory=DetectionConfig)
    performance: PerformanceConfig = field(default_factory=PerformanceConfig)

    # Feature flags
    features: FeatureFlags = field(default_factory=FeatureFlags)

    # General
    log_level: str = "INFO"
    environment: str = "development"

    @classmethod
    def from_yaml(cls, path: str | Path) -> "AgentConfig":
        """Load configuration from a YAML file.

        Args:
            path: Path to the YAML configuration file.

        Returns:
            Populated AgentConfig instance.
        """
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
        return cls._from_dict(raw)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentConfig":
        """Load configuration from a dictionary."""
        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> "AgentConfig":
        """Internal helper to construct config from dict."""
        config = cls()

        if "telemetry_provider" in data:
            config.telemetry_provider = TelemetryProviderType(data["telemetry_provider"])
        if "cloud_provider" in data:
            config.cloud_provider = CloudProviderType(data["cloud_provider"])

        if "otel" in data:
            config.otel = OTelConfig(**data["otel"])
        if "newrelic" in data:
            config.newrelic = NewRelicConfig(**data["newrelic"])
        if "aws" in data:
            config.aws = AWSConfig(**data["aws"])
        if "azure" in data:
            config.azure = AzureConfig(**data["azure"])
        if "cloudwatch" in data:
            config.cloudwatch = CloudWatchConfig(**data["cloudwatch"])
        if "enrichment" in data:
            config.enrichment = EnrichmentConfig(**data["enrichment"])
        if "aws_health" in data:
            raw_health = dict(data["aws_health"])
            # Convert regions from YAML list to Python list if needed
            if "regions" in raw_health and raw_health["regions"] is None:
                raw_health["regions"] = None
            config.aws_health = AWSHealthConfig(**raw_health)
        if "detection" in data:
            config.detection = DetectionConfig(**data["detection"])
        if "performance" in data:
            config.performance = PerformanceConfig(**data["performance"])
        if "features" in data:
            config.features = FeatureFlags(**data["features"])

        config.log_level = data.get("log_level", config.log_level)
        config.environment = data.get("environment", config.environment)

        return config

    def validate(self) -> list[str]:
        """Validate configuration completeness.

        Returns:
            List of validation error messages. Empty list = valid.
        """
        errors: list[str] = []

        # Validate telemetry provider config
        if self.telemetry_provider == TelemetryProviderType.OTEL:
            if not self.otel.prometheus_url:
                errors.append("OTel: prometheus_url is required")
        elif self.telemetry_provider == TelemetryProviderType.NEWRELIC:
            if not self.newrelic.account_id:
                errors.append("New Relic: account_id is required")

        # Validate cloud provider config
        if self.cloud_provider == CloudProviderType.AWS:
            if not self.aws.region:
                errors.append("AWS: region is required")
            if self.features.cloudwatch_adapter and not self.cloudwatch.region:
                errors.append("CloudWatch: region is required when cloudwatch_adapter is enabled")
        elif self.cloud_provider == CloudProviderType.AZURE:
            if not self.azure.subscription_id:
                errors.append("Azure: subscription_id is required")
            if not self.azure.resource_group:
                errors.append("Azure: resource_group is required")
            if not self.azure.aks_cluster_name:
                errors.append("Azure: aks_cluster_name is required")

        return errors
