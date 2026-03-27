"""
Application Bootstrap — wire adapters to domain via plugin registry.

This is the ONLY place where adapter implementations are imported and
connected to the domain layer. It lives in the adapters layer, not
in domain or config, per hexagonal architecture (§1.1).

This module is called at application startup (e.g., from main.py).
"""

from __future__ import annotations

import structlog

from sre_agent.config.plugin import ProviderPlugin, ProviderFactory
from sre_agent.config.settings import AgentConfig, LockBackendType
from sre_agent.adapters.coordination.in_memory_lock_manager import InMemoryDistributedLockManager
from sre_agent.ports.lock_manager import DistributedLockManagerPort
from sre_agent.domain.detection.provider_registry import ProviderRegistry
from sre_agent.ports.telemetry import TelemetryProvider

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Built-in provider factories (adapter layer — OK to import adapters here)
# ---------------------------------------------------------------------------

def _otel_factory(config: AgentConfig) -> TelemetryProvider:
    """Factory for the OTel provider (Prometheus + Jaeger + Loki)."""
    from sre_agent.adapters.telemetry.otel.provider import OTelProvider
    return OTelProvider(config.otel)


def _newrelic_factory(config: AgentConfig) -> TelemetryProvider:
    """Factory for the New Relic provider.

    Note: API key must be resolved from secrets manager before calling this.
    For now, uses a placeholder — real secrets integration in cloud-portability.
    """
    from sre_agent.adapters.telemetry.newrelic.provider import NewRelicProvider
    # In production, api_key comes from secrets manager (AWS SM, Azure KV, Vault)
    api_key = ""  # Placeholder — resolved at runtime
    return NewRelicProvider(config.newrelic, api_key=api_key)


def _create_pixie_adapter(config: AgentConfig):
    """Factory for the Pixie eBPF adapter (optional — kernel telemetry).

    Returns an eBPFQuery implementation. This is separate from the
    TelemetryProvider since eBPF is supplementary to the primary
    metrics/traces/logs provider.
    """
    from sre_agent.adapters.telemetry.ebpf.pixie_adapter import PixieAdapter
    return PixieAdapter(
        api_url=getattr(config, "pixie_api_url", "https://work.withpixie.ai"),
        cluster_id=getattr(config, "pixie_cluster_id", ""),
        api_key=getattr(config, "pixie_api_key", ""),
    )


def register_builtin_providers() -> None:
    """Register the built-in OTel and New Relic provider factories."""
    ProviderPlugin.register("otel", _otel_factory)
    ProviderPlugin.register("newrelic", _newrelic_factory)


async def bootstrap_provider(
    config: AgentConfig,
    registry: ProviderRegistry,
) -> TelemetryProvider:
    """Bootstrap the telemetry provider from configuration.

    1. Register built-in providers
    2. Create the configured provider via plugin system
    3. Register and activate it in the provider registry

    Returns:
        The activated TelemetryProvider instance.
    """
    register_builtin_providers()

    provider_name = config.telemetry_provider.value
    logger.info("bootstrapping_provider", provider=provider_name)

    provider = ProviderPlugin.create_provider(provider_name, config)
    registry.register(provider)
    await registry.activate(provider_name)

    logger.info(
        "provider_bootstrapped",
        provider=provider_name,
        available=ProviderPlugin.available_providers(),
    )
    return provider


# ---------------------------------------------------------------------------
# Phase 1.5 — Cloud operator bootstrap
# ---------------------------------------------------------------------------

def bootstrap_cloud_operators(config: AgentConfig):
    """Bootstrap cloud remediation operators based on available SDKs.

    Returns a CloudOperatorRegistry with registered operators for any
    cloud SDKs that are importable.
    """
    from sre_agent.domain.detection.cloud_operator_registry import CloudOperatorRegistry

    registry = CloudOperatorRegistry()

    # Kubernetes operator (requires kubernetes client)
    try:
        from kubernetes import client as _k8s_client  # noqa: F401

        from sre_agent.adapters.cloud.kubernetes.operator import KubernetesOperator

        registry.register(KubernetesOperator())
        logger.info("kubernetes_operator_bootstrapped")
    except ImportError:
        logger.debug("kubernetes_operator_skipped", reason="kubernetes client not installed")

    # AWS operators (requires boto3)
    try:
        import boto3  # noqa: F401

        from sre_agent.adapters.cloud.aws.ecs_operator import ECSOperator
        from sre_agent.adapters.cloud.aws.ec2_asg_operator import EC2ASGOperator
        from sre_agent.adapters.cloud.aws.lambda_operator import LambdaOperator

        region = getattr(config, "aws_region", "us-east-1")
        registry.register(ECSOperator(boto3.client("ecs", region_name=region)))
        registry.register(EC2ASGOperator(boto3.client("autoscaling", region_name=region)))
        registry.register(LambdaOperator(boto3.client("lambda", region_name=region)))
        logger.info("aws_operators_bootstrapped", region=region)
    except ImportError:
        logger.debug("aws_operators_skipped", reason="boto3 not installed")

    # Azure operators (requires azure-mgmt-web)
    try:
        from azure.mgmt.web import WebSiteManagementClient  # noqa: F401
        from azure.identity import DefaultAzureCredential  # noqa: F401

        from sre_agent.adapters.cloud.azure.app_service_operator import AppServiceOperator
        from sre_agent.adapters.cloud.azure.functions_operator import FunctionsOperator

        sub_id = getattr(config, "azure_subscription_id", "")
        credential = DefaultAzureCredential()
        web_client = WebSiteManagementClient(credential, sub_id)
        registry.register(AppServiceOperator(web_client))
        registry.register(FunctionsOperator(web_client))
        logger.info("azure_operators_bootstrapped", subscription=sub_id)
    except ImportError:
        logger.debug("azure_operators_skipped", reason="azure-mgmt-web not installed")

    return registry


def bootstrap_lock_manager(config: AgentConfig) -> DistributedLockManagerPort:
    """Bootstrap lock manager backend based on configuration."""
    backend = config.lock.backend

    if backend == LockBackendType.REDIS:
        try:
            from sre_agent.adapters.coordination.redis_lock_manager import (
                RedisDistributedLockManager,
                RedisLockConfig,
            )

            lock_manager = RedisDistributedLockManager(
                config=RedisLockConfig(
                    url=config.lock.redis_url,
                    key_prefix=config.lock.key_prefix,
                )
            )
            logger.info("lock_manager_bootstrapped", backend="redis")
            return lock_manager
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "lock_manager_backend_failed",
                backend="redis",
                error=str(exc),
                fallback="in_memory",
            )

    if backend == LockBackendType.ETCD:
        try:
            from sre_agent.adapters.coordination.etcd_lock_manager import (
                EtcdDistributedLockManager,
                EtcdLockConfig,
            )

            lock_manager = EtcdDistributedLockManager(
                config=EtcdLockConfig(
                    host=config.lock.etcd_host,
                    port=config.lock.etcd_port,
                    key_prefix=config.lock.key_prefix,
                )
            )
            logger.info("lock_manager_bootstrapped", backend="etcd")
            return lock_manager
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "lock_manager_backend_failed",
                backend="etcd",
                error=str(exc),
                fallback="in_memory",
            )

    logger.info("lock_manager_bootstrapped", backend="in_memory")
    return InMemoryDistributedLockManager()
